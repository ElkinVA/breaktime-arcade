"""Best-effort Telegram notifications for the autonomous orchestrator.

Notifications are an observability channel, never a control dependency: a
missing token, an unreachable Telegram API or a malformed response is reported
as ``skipped``/``retry`` in the log and must never change the run outcome.

The token and chat id are owner configuration. They are loaded from the
process environment or from ``creds/telegram.env`` (mode 0600, outside Git).
The token is never rendered, logged or included in a notification body.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from devcontrol.config import TOKEN_RE, ConfigError, _parse_env_file
from devcontrol.telegram import TelegramClient, TelegramError, sanitize_text

logger = logging.getLogger("autonomy.notifier")

DEFAULT_CREDS_PATH = Path(__file__).resolve().parents[1] / "creds" / "telegram.env"
DEFAULT_BASE_URL = "https://api.telegram.org"
DEFAULT_TIMEOUT = 15
DEFAULT_MAX_ATTEMPTS = 2
DEFAULT_RETRY_DELAY = 1.0
MAX_RETRY_DELAY = 30.0

# Stable machine-readable event kinds understood by the owner.
TASK_COMPLETED = "task_completed"
TASK_REJECTED = "task_rejected"
TASK_BLOCKED = "task_blocked"
RUN_BUDGET_STOP = "run_budget_stop"
RUN_STOPPED = "run_stopped"
FATAL_ERROR = "fatal_error"

_KIND_PREFIX = {
    TASK_COMPLETED: "✅ Задача завершена",
    TASK_REJECTED: "❌ Ревью отклонило",
    TASK_BLOCKED: "⛔ Задача заблокирована",
    RUN_BUDGET_STOP: "⏹ Остановка по бюджету",
    RUN_STOPPED: "⏹ Запуск остановлен",
    FATAL_ERROR: "🚨 Фатальная ошибка оркестратора",
}


@dataclass(frozen=True)
class NotificationEvent:
    """Structured task/run event sent to the owner."""

    kind: str
    task: str | None = None
    title: str | None = None
    status: str | None = None
    reason: str | None = None
    detail: str | None = None
    usage: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"kind": self.kind}
        for key in ("task", "title", "status", "reason", "detail", "usage"):
            value = getattr(self, key)
            if value:
                payload[key] = value
        return payload


def render_event(event: NotificationEvent) -> str:
    """Render a stable, plain-text message (no parse_mode, no HTML/Markdown)."""
    lines = [f"{_KIND_PREFIX.get(event.kind, event.kind)} [{event.kind}]"]
    if event.task:
        lines.append(f"Задача: {event.task}")
    if event.title:
        lines.append(f"Название: {event.title}")
    if event.status:
        lines.append(f"Статус: {event.status}")
    if event.reason:
        lines.append(f"Причина: {event.reason}")
    if event.detail:
        lines.append(f"Детали: {event.detail[:1200]}")
    if event.usage:
        parts: list[str] = []
        tokens = event.usage.get("total_tokens")
        cost = event.usage.get("cost_usd")
        if isinstance(tokens, int) and not isinstance(tokens, bool):
            parts.append(f"токены={tokens}")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool):
            parts.append(f"стоимость=${cost}")
        if parts:
            lines.append("Использование: " + ", ".join(parts))
    return "\n".join(lines)


@dataclass(frozen=True)
class NotifierSettings:
    """Owner-configured Telegram transport settings."""

    token: str = field(default="", repr=False)
    chat_id: int = 0
    base_url: str = DEFAULT_BASE_URL
    timeout: int = DEFAULT_TIMEOUT
    proxy: str | None = None
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    retry_delay: float = DEFAULT_RETRY_DELAY

    @property
    def skip_reason(self) -> str | None:
        if not self.token:
            return "missing bot token"
        if self.chat_id == 0:
            return "missing chat id"
        return None

    @property
    def enabled(self) -> bool:
        return self.skip_reason is None

    @classmethod
    def from_env(
        cls,
        *,
        env: Mapping[str, str] | None = None,
        creds_path: Path | None = None,
    ) -> NotifierSettings:
        """Load owner configuration; never raises and never logs values."""
        source = dict(os.environ if env is None else env)
        values: dict[str, str] = {}
        creds = Path(creds_path) if creds_path is not None else DEFAULT_CREDS_PATH
        try:
            values = dict(_parse_env_file(creds))
        except ConfigError, OSError, UnicodeError:
            # An unsafe/missing/undecodable creds file only disables notifications.
            values = {}

        def pick(key: str) -> str:
            return (source.get(key) or values.get(key) or "").strip()

        token = pick("TELEGRAM_BOT_TOKEN")
        if token and not TOKEN_RE.match(token):
            token = ""
        raw_chat = pick("TELEGRAM_CHAT_ID") or pick("TELEGRAM_OWNER_ID")
        try:
            chat_id = int(raw_chat)
        except TypeError, ValueError:
            chat_id = 0
        return cls(
            token=token,
            chat_id=chat_id,
            proxy=pick("TELEGRAM_PROXY") or None,
        )


class Transport(Protocol):
    """Minimal transport surface used by :class:`Notifier`."""

    def send_message(self, chat_id: int, text: str) -> object: ...


class TelegramTransport:
    """Production transport backed by the shared, sanitising Telegram client."""

    def __init__(self, settings: NotifierSettings) -> None:
        self._client = TelegramClient(
            settings.token,
            base_url=settings.base_url,
            timeout=settings.timeout,
            proxy=settings.proxy,
        )

    def send_message(self, chat_id: int, text: str) -> object:
        return self._client.send_message(chat_id, text)


@dataclass(frozen=True)
class NotificationResult:
    """Outcome of one notification attempt series."""

    status: Literal["sent", "skipped"]
    attempts: int = 0
    reason: str | None = None


def _retryable(error: TelegramError) -> bool:
    # ``status_code`` is None for network/timeout/non-JSON failures.
    if error.status_code is None:
        return True
    return error.status_code == 429 or error.status_code >= 500


class Notifier:
    """Send structured owner notifications without ever failing the caller."""

    def __init__(
        self,
        settings: NotifierSettings | None = None,
        *,
        transport: Transport | None = None,
        log: logging.Logger | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings or NotifierSettings()
        self._log = log or logger
        self._sleep = sleep
        self._transport = transport
        self._skip_reason = self.settings.skip_reason
        if self._transport is None and self._skip_reason is None:
            try:
                self._transport = TelegramTransport(self.settings)
            except Exception as exc:  # noqa: BLE001 - construction is best-effort
                self._transport = None
                self._skip_reason = f"transport unavailable: {type(exc).__name__}"

    @classmethod
    def from_env(
        cls,
        *,
        env: Mapping[str, str] | None = None,
        creds_path: Path | None = None,
        transport: Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> Notifier:
        settings = NotifierSettings.from_env(env=env, creds_path=creds_path)
        return cls(settings, transport=transport, sleep=sleep)

    @classmethod
    def disabled(cls) -> Notifier:
        return cls(NotifierSettings())

    def _safe(self, value: object) -> str:
        return sanitize_text(str(value), self.settings.token)

    def _skip(
        self,
        kind: str,
        reason: str,
        attempts: int,
        *,
        task: str | None = None,
    ) -> NotificationResult:
        clean = self._safe(reason) or "unknown reason"
        self._log.info(
            "notification skipped: kind=%s task=%s attempts=%d reason=%s",
            kind,
            task or "-",
            attempts,
            clean,
        )
        return NotificationResult("skipped", attempts, clean)

    def _retry_delay(self, error: TelegramError, attempt: int) -> float:
        if isinstance(error.retry_after, int) and error.retry_after >= 0:
            delay = float(error.retry_after)
        else:
            delay = self.settings.retry_delay * (2 ** (attempt - 1))
        return min(max(delay, 0.0), MAX_RETRY_DELAY)

    def notify(self, event: NotificationEvent) -> NotificationResult:
        """Send one event; all failures are logged as skipped/retry, never raised."""
        if self._skip_reason is not None or self._transport is None:
            return self._skip(
                event.kind,
                self._skip_reason or "not configured",
                0,
                task=event.task,
            )
        text = render_event(event)
        if not text.strip():
            return self._skip(event.kind, "empty message", 0, task=event.task)
        attempts = 0
        last_reason = "unknown error"
        max_attempts = max(1, int(self.settings.max_attempts))
        for attempt in range(1, max_attempts + 1):
            attempts = attempt
            try:
                self._transport.send_message(self.settings.chat_id, text)
            except TelegramError as exc:
                last_reason = self._safe(exc) or type(exc).__name__
                if not _retryable(exc) or attempt >= max_attempts:
                    return self._skip(event.kind, last_reason, attempt, task=event.task)
                delay = self._retry_delay(exc, attempt)
                self._log.info(
                    "notification retry: kind=%s task=%s attempts=%d delay=%.1fs reason=%s",
                    event.kind,
                    event.task or "-",
                    attempt,
                    delay,
                    last_reason,
                )
                self._sleep(delay)
            except Exception as exc:  # noqa: BLE001 - a transport bug must not break a run
                return self._skip(
                    event.kind,
                    f"{type(exc).__name__}: {exc}",
                    attempt,
                    task=event.task,
                )
            else:
                self._log.info(
                    "notification sent: kind=%s task=%s attempts=%d",
                    event.kind,
                    event.task or "-",
                    attempt,
                )
                return NotificationResult("sent", attempt)
        return self._skip(event.kind, last_reason, attempts, task=event.task)
