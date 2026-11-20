"""Minimal Telegram Bot API client (stdlib only, long polling).

The client never logs or re-raises the bot token. Messages are sent as plain
text (no parse_mode), so HTML/Markdown injection from logs or the agent cannot
alter the message structure.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

TOKEN_SHAPE = re.compile(r"\d{5,}:[A-Za-z0-9_-]{20,}")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[@-_]")
_SECRET_KEY = re.compile(
    r"(?i)([A-Z0-9_]*(?:PASSWORD|PASSWD|SECRET|TOKEN|API_KEY|AUTH_TOKEN|PRIVATE_KEY"
    r"|DATABASE_URL|REDIS_URL|DSN)[A-Z0-9_]*)\s*[:=]\s*(\S+)"
)
_URL_CRED = re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://[^:/\s]+:)([^@\s]+)(@)")
_SECRET_VALUES = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        re.DOTALL,
    ),
)


class TelegramError(Exception):
    """Telegram API/network error with a sanitised description."""

    def __init__(self, message: str, *, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def redact_secrets(text: str) -> str:
    text = _URL_CRED.sub(r"\1<redacted>\3", text)
    text = _SECRET_KEY.sub(r"\1=<redacted>", text)
    for pattern in _SECRET_VALUES:
        text = pattern.sub("<redacted>", text)
    return text


def sanitize_text(text: str, token: str | None = None) -> str:
    if token:
        text = text.replace(token, "<redacted>")
    text = TOKEN_SHAPE.sub("<redacted>", text)
    text = redact_secrets(text)
    text = _ANSI.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return _CONTROL.sub("", text)


def split_text(text: str, limit: int = 4000) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.splitlines(keepends=True):
        if size + len(line) > limit and current:
            chunks.append("".join(current))
            current = []
            size = 0
        while len(line) > limit:
            chunks.append(line[:limit])
            line = line[limit:]
        current.append(line)
        size += len(line)
    if current:
        chunks.append("".join(current))
    return chunks


class TelegramClient:
    def __init__(
        self,
        token: str,
        *,
        base_url: str = "https://api.telegram.org",
        timeout: int = 30,
    ) -> None:
        if urlparse(base_url).scheme != "https":
            raise ValueError("Telegram base_url must use https")
        self._token = token
        self._base = f"{base_url.rstrip('/')}/bot{token}"
        self._timeout = timeout

    def _sanitize(self, text: str) -> str:
        return sanitize_text(text, self._token)

    def _call(
        self,
        method: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: int | None = None,
    ) -> Any:
        data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(  # noqa: S310
            f"{self._base}/{method}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            # URL built from a validated https base; no user-controlled scheme.
            with urllib.request.urlopen(  # noqa: S310
                request, timeout=timeout or self._timeout
            ) as response:
                body = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
        except urllib.error.URLError as exc:
            raise TelegramError(self._sanitize(f"network error: {exc.reason}")) from None
        except TimeoutError:
            raise TelegramError("telegram request timed out") from None
        try:
            parsed = json.loads(body)
        except ValueError:
            raise TelegramError("telegram returned non-JSON response") from None
        if not isinstance(parsed, dict) or not parsed.get("ok"):
            description = parsed.get("description") if isinstance(parsed, dict) else None
            parameters = parsed.get("parameters") if isinstance(parsed, dict) else None
            retry_after = None
            if isinstance(parameters, dict) and isinstance(parameters.get("retry_after"), int):
                retry_after = parameters["retry_after"]
            raise TelegramError(
                self._sanitize(str(description or "telegram API error")),
                retry_after=retry_after,
            )
        return parsed.get("result")

    def get_me(self) -> dict[str, Any]:
        result = self._call("getMe", timeout=15)
        return result if isinstance(result, dict) else {}

    def get_updates(self, offset: int, timeout: int = 25) -> list[dict[str, Any]]:
        result = self._call(
            "getUpdates",
            {
                "offset": offset,
                "timeout": timeout,
                "allowed_updates": ["message", "callback_query"],
            },
            timeout=timeout + 15,
        )
        return result if isinstance(result, list) else []

    def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": self._sanitize(text)[:4096],
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        result = self._call("sendMessage", payload)
        return result if isinstance(result, dict) else {}

    def send_long_message(
        self,
        chat_id: int,
        text: str,
        *,
        reply_markup: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        chunks = split_text(self._sanitize(text))
        if not chunks:
            chunks = ["(пусто)"]
        sent: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks):
            markup = reply_markup if index == len(chunks) - 1 else None
            sent.append(self.send_message(chat_id, chunk, reply_markup=markup))
        return sent

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        *,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": self._sanitize(text)[:4096],
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        result = self._call("editMessageText", payload)
        return result if isinstance(result, dict) else {}

    def answer_callback_query(self, callback_id: str, text: str | None = None) -> None:
        payload: dict[str, Any] = {"callback_query_id": callback_id}
        if text:
            payload["text"] = self._sanitize(text)[:200]
        self._call("answerCallbackQuery", payload, timeout=10)


def inline_keyboard(rows: list[list[tuple[str, str]]]) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": text, "callback_data": data} for text, data in row] for row in rows
        ]
    }
