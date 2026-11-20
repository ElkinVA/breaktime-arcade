# ruff: noqa: E402
"""BA Dev Control — Telegram control plane for autonomous Breaktime Arcade work.

The service is intentionally separate from the Django application. It uses
long polling, authorises exactly one Telegram user id, and drives Claude Code
only through its documented background-session commands.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import logging
import os
import re
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from devcontrol.claude import (  # noqa: E402
    ClaudeController,
    ClaudeError,
    StartResult,
    parse_start_reference,
)
from devcontrol.config import Config, ConfigError
from devcontrol.store import RuntimePaths, StateStore, read_jsonl, utc_now
from devcontrol.telegram import (
    TelegramClient,
    TelegramError,
    inline_keyboard,
    sanitize_text,
)

logger = logging.getLogger("devcontrol")

STALE_HEARTBEAT_SECONDS = 10 * 60
PAUSED_STATUS = "PAUSED"
RUNNING_STATUS = "RUNNING"

MAIN_KEYBOARD = inline_keyboard(
    [
        [("Статус", "status"), ("Текущая задача", "task")],
        [("Прогресс", "progress"), ("Следующая", "next")],
        [("Продолжить", "continue"), ("Пауза", "pause")],
        [("Отчёт", "report"), ("Задать вопрос", "ask")],
        [("Логи", "logs"), ("Помощь", "help")],
    ]
)

STOP_TTL_SECONDS = 300


def stop_keyboard() -> dict[str, Any]:
    return inline_keyboard(
        [
            [
                ("Остановить безопасно", f"stop_confirm:{int(time.time())}"),
                ("Отмена", "stop_cancel"),
            ],
        ]
    )


HELP_TEXT = """BA Dev Control — удалённое управление разработкой.

/status — состояние проекта и сессии
/report — последний отчёт
/progress — прогресс и счётчики задач
/next — следующая READY-задача
/tasks — активные и следующие задачи
/continue — продолжить автономную разработку
/pause — приостановить запуск новых задач
/resume — снять паузу/продолжить
/stop — безопасно остановить сессию (с подтверждением)
/logs — последние сообщения сессии
/ask <текст> — передать сообщение агенту
/whoami — ваш Telegram ID
/help — эта справка
"""


class App:
    def __init__(
        self,
        config: Config,
        *,
        store: StateStore | None = None,
        client: TelegramClient | None = None,
        controller: ClaudeController | None = None,
    ) -> None:
        self.config = config
        self.paths = RuntimePaths(config.runtime_dir)
        self.store = store or StateStore(self.paths)
        self.client = client or TelegramClient(config.token, timeout=config.poll_timeout + 15)
        self.controller = controller or ClaudeController(
            project_dir=config.project_dir,
            claude_bin=config.claude_bin,
            session_name=config.session_name,
            settings_path=config.settings_path,
        )
        self._stop = threading.Event()
        self._lock_fd: int | None = None
        self._monitor: threading.Thread | None = None
        self._last_stale_notice = 0.0
        self._session_lock = threading.Lock()

    # --- lifecycle -----------------------------------------------------
    def acquire_singleton(self) -> bool:
        self.paths.ensure()
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(self.paths.controller_lock, flags, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return False
        self._lock_fd = fd
        return True

    def release_singleton(self) -> None:
        if self._lock_fd is None:
            return
        with contextlib.suppress(OSError):
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
        os.close(self._lock_fd)
        self._lock_fd = None

    def run(self) -> int:
        if not self.acquire_singleton():
            logger.error("another BA Dev Control instance is running")
            return 2
        try:
            me = self.client.get_me()
            username = me.get("username") if isinstance(me, dict) else None
            logger.info("telegram bot authenticated as @%s", username or "unknown")
            self.store.update_state(bot_username=username, bot_started_at=utc_now())
            self._monitor = threading.Thread(target=self.monitor_loop, name="monitor", daemon=True)
            self._monitor.start()
            self.poll_loop()
        except TelegramError as exc:
            logger.error("telegram authentication failed: %s", exc)
            return 2
        finally:
            self.release_singleton()
        return 0

    def poll_loop(self) -> None:
        offset = int(self.store.load_state().get("last_update_id") or 0) + 1
        backoff = 5
        while not self._stop.is_set():
            try:
                updates = self.client.get_updates(offset, timeout=self.config.poll_timeout)
                backoff = 5
                for update in updates:
                    update_id = update.get("update_id")
                    if isinstance(update_id, int):
                        offset = max(offset, update_id + 1)
                        if not self.store.mark_update(update_id):
                            continue
                    self.handle_update(update)
            except TelegramError as exc:
                wait = exc.retry_after or backoff
                logger.warning("telegram poll failed: %s; retrying in %ss", exc, wait)
                self._stop.wait(wait)
                backoff = min(backoff * 2, 60)
            except Exception:
                logger.exception("poll loop error")
                self._stop.wait(10)

    def stop(self, *_args: object) -> None:
        self._stop.set()

    # --- update handling ------------------------------------------------
    def handle_update(self, update: dict[str, Any]) -> None:
        message = update.get("message")
        callback = update.get("callback_query")
        if isinstance(message, dict):
            self.handle_message(message)
        elif isinstance(callback, dict):
            self.handle_callback(callback)

    def _authorized(self, user: Any) -> bool:
        if not isinstance(user, dict):
            return False
        return user.get("id") == self.config.owner_id

    def handle_message(self, message: dict[str, Any]) -> None:
        user = message.get("from")
        if not self._authorized(user):
            logger.warning("denied message from unauthorized user id=%s", (user or {}).get("id"))
            return
        text = message.get("text")
        chat_id = message.get("chat", {}).get("id")
        if not isinstance(text, str) or not isinstance(chat_id, int):
            return
        text = text.strip()
        if not text:
            return
        if text.startswith("/"):
            command, _, args = text.partition(" ")
            command = command.split("@", 1)[0]
            self.store.update_state(pending_ask_at=None)
            self.dispatch_command(chat_id, command, args.strip())
            return
        state = self.store.load_state()
        pending = state.get("pending_ask_at")
        if pending:
            self.enqueue_ask(chat_id, text)
            self.store.update_state(pending_ask_at=None)
            return
        self.send(chat_id, "Команда не распознана. /help — справка.", MAIN_KEYBOARD)

    def handle_callback(self, callback: dict[str, Any]) -> None:
        user = callback.get("from")
        callback_id = callback.get("id")
        data = callback.get("data")
        message = callback.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        if not self._authorized(user):
            logger.warning("denied callback from unauthorized user id=%s", (user or {}).get("id"))
            if isinstance(callback_id, str):
                with contextlib.suppress(TelegramError):
                    self.client.answer_callback_query(callback_id, "Доступ запрещён")
            return
        if not isinstance(data, str) or not isinstance(chat_id, int):
            return
        if isinstance(callback_id, str) and not self.store.mark_callback(str(callback_id)):
            return
        if isinstance(callback_id, str):
            with contextlib.suppress(TelegramError):
                self.client.answer_callback_query(callback_id)
        self.dispatch_callback(chat_id, data)

    def dispatch_command(self, chat_id: int, command: str, args: str) -> None:
        handlers = {
            "/start": self.cmd_start,
            "/help": self.cmd_start,
            "/status": self.cmd_status,
            "/report": self.cmd_report,
            "/progress": self.cmd_progress,
            "/next": self.cmd_next,
            "/tasks": self.cmd_tasks,
            "/continue": self.cmd_continue,
            "/pause": self.cmd_pause,
            "/resume": self.cmd_resume,
            "/stop": self.cmd_stop,
            "/logs": self.cmd_logs,
            "/ask": self.cmd_ask,
            "/whoami": self.cmd_whoami,
        }
        handler = handlers.get(command)
        if handler is None:
            self.send(chat_id, f"Неизвестная команда: {command}. /help — справка.")
            return
        handler(chat_id, args)

    def dispatch_callback(self, chat_id: int, data: str) -> None:
        if data.startswith("stop_confirm:"):
            try:
                issued = int(data.split(":", 1)[1])
            except ValueError:
                self.send(chat_id, "Некорректное подтверждение.", MAIN_KEYBOARD)
                return
            if time.time() - issued > STOP_TTL_SECONDS:
                self.send(
                    chat_id,
                    "Подтверждение устарело. Запросите /stop снова.",
                    MAIN_KEYBOARD,
                )
                return
            self.cmd_stop_confirm(chat_id, "")
            return
        actions = {
            "status": self.cmd_status,
            "task": self.cmd_task,
            "progress": self.cmd_progress,
            "next": self.cmd_next,
            "tasks": self.cmd_tasks,
            "continue": self.cmd_continue,
            "pause": self.cmd_pause,
            "resume": self.cmd_resume,
            "report": self.cmd_report,
            "ask": self.cmd_ask,
            "logs": self.cmd_logs,
            "help": self.cmd_start,
            "stop": self.cmd_stop,
            "stop_cancel": self.cmd_stop_cancel,
        }
        handler = actions.get(data)
        if handler is None:
            self.send(chat_id, "Действие устарело. /help — справка.", MAIN_KEYBOARD)
            return
        handler(chat_id, "")

    # --- commands -------------------------------------------------------
    def cmd_start(self, chat_id: int, _args: str) -> None:
        state = self.store.load_state()
        self.send(
            chat_id,
            "BA Dev Control\n"
            f"Проект: {self.config.project_dir}\n"
            f"Статус: {state.get('status', 'IDLE')}\n\n{HELP_TEXT}",
            MAIN_KEYBOARD,
        )

    def cmd_status(self, chat_id: int, _args: str) -> None:
        self.send(chat_id, self.status_text(), MAIN_KEYBOARD)

    def cmd_task(self, chat_id: int, _args: str) -> None:
        state = self.store.load_state()
        task = state.get("current_task") or "нет активной задачи"
        title = state.get("current_title") or ""
        self.send(chat_id, f"Текущая задача:\n{task}\n{title}".strip(), MAIN_KEYBOARD)

    def cmd_progress(self, chat_id: int, _args: str) -> None:
        rows = self._backlog_rows()
        counts: dict[str, int] = {}
        for row in rows:
            status = row["status"].upper()
            counts[status] = counts.get(status, 0) + 1
        state = self.store.load_state()
        lines = ["Прогресс (BACKLOG):"]
        for status, count in sorted(counts.items()):
            lines.append(f"• {status}: {count}")
        lines.append(f"\nТекущая: {state.get('current_task') or '—'}")
        nxt = self._next_ready(rows)
        lines.append(f"Следующая READY: {nxt['id'] if nxt else 'нет'}")
        self.send(chat_id, "\n".join(lines), MAIN_KEYBOARD)

    def cmd_next(self, chat_id: int, _args: str) -> None:
        nxt = self._next_ready(self._backlog_rows())
        if not nxt:
            self.send(chat_id, "READY-задач нет.", MAIN_KEYBOARD)
            return
        self.send(
            chat_id,
            f"Следующая READY:\n{nxt['id']}\n{nxt['title']}\n{nxt['notes']}",
            MAIN_KEYBOARD,
        )

    def cmd_tasks(self, chat_id: int, _args: str) -> None:
        rows = self._backlog_rows()
        interesting = [
            row
            for row in rows
            if any(
                marker in row["status"].upper() for marker in ("READY", "BLOCKED", "IN PROGRESS")
            )
        ]
        state = self.store.load_state()
        lines = [f"Текущая: {state.get('current_task') or '—'}"]
        for row in interesting[:15]:
            lines.append(f"• {row['id']}: {row['status']}")
        self.send(chat_id, "\n".join(lines), MAIN_KEYBOARD)

    def cmd_report(self, chat_id: int, _args: str) -> None:
        path = self._latest_report()
        if path is None:
            self.send(chat_id, "Отчёты не найдены.", MAIN_KEYBOARD)
            return
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            self.send(chat_id, f"Не удалось прочитать отчёт: {exc}", MAIN_KEYBOARD)
            return
        self.send(
            chat_id, f"Отчёт: {path.name}\n\n{text[: self.config.max_log_chars]}", MAIN_KEYBOARD
        )

    def cmd_continue(self, chat_id: int, _args: str) -> None:
        if self.store.paused():
            self.send(
                chat_id,
                "Разработка на паузе. Снимите паузу через /resume.",
                inline_keyboard([[("Resume", "resume"), ("Статус", "status")]]),
            )
            return
        self.start_autonomous(chat_id)

    def cmd_pause(self, chat_id: int, _args: str) -> None:
        self.store.set_pause(True)
        self.store.update_state(status=PAUSED_STATUS)
        self.notify(
            "⏸ Пауза: новые задачи не запускаются. Текущая задача завершится на ближайшей границе."
        )
        self.send(chat_id, "Пауза включена.", MAIN_KEYBOARD)

    def cmd_resume(self, chat_id: int, _args: str) -> None:
        self.store.set_pause(False)
        if self._active_session():
            self.store.update_state(status=RUNNING_STATUS, session_active=True)
            self.send(chat_id, "Пауза снята; сессия уже работает.", MAIN_KEYBOARD)
            return
        self.start_autonomous(chat_id, resume=True)

    def cmd_stop(self, chat_id: int, _args: str) -> None:
        self.send(
            chat_id,
            "Остановить текущую фоновую сессию? Разговор сохранится, его можно продолжить.",
            stop_keyboard(),
        )

    def cmd_stop_confirm(self, chat_id: int, _args: str) -> None:
        with self._session_lock:
            state = self.store.load_state()
            session = self._any_our_session()
            reference = (
                (session or {}).get("reference")
                or state.get("session_ref")
                or state.get("session_id")
                or ""
            )
            if not reference:
                self.send(chat_id, "Активной сессии нет.", MAIN_KEYBOARD)
                return
            try:
                ok, detail = self.controller.stop(str(reference))
            except ClaudeError as exc:
                self.send(chat_id, f"Ошибка остановки: {exc}", MAIN_KEYBOARD)
                return
            if ok:
                self.store.update_state(status="IDLE", session_active=False, starting_at=None)
                self.store.append_event("session_stop", detail="owner requested stop")
                self.send(chat_id, "Остановлено. Продолжить: /resume.", MAIN_KEYBOARD)
            else:
                self.send(chat_id, f"Не удалось остановить: {detail}", MAIN_KEYBOARD)

    def cmd_stop_cancel(self, chat_id: int, _args: str) -> None:
        self.send(chat_id, "Остановка отменена.", MAIN_KEYBOARD)

    def cmd_logs(self, chat_id: int, _args: str) -> None:
        state = self.store.load_state()
        session = self._any_our_session()
        reference = (
            (session or {}).get("reference")
            or state.get("session_ref")
            or state.get("session_id")
            or ""
        )
        if not reference:
            self.send(chat_id, "Активной сессии нет.", MAIN_KEYBOARD)
            return
        try:
            text = self.controller.logs(str(reference), max_chars=self.config.max_log_chars)
        except ClaudeError as exc:
            self.send(chat_id, f"Ошибка чтения логов: {exc}", MAIN_KEYBOARD)
            return
        self.send(chat_id, f"Логи {reference}:\n\n{clean_cli_log(text)}", MAIN_KEYBOARD)

    def cmd_ask(self, chat_id: int, args: str) -> None:
        if args:
            self.enqueue_ask(chat_id, args)
            return
        self.store.update_state(pending_ask_at=utc_now())
        self.send(
            chat_id,
            "Отправьте сообщение для агента следующим текстом (не команду).",
            MAIN_KEYBOARD,
        )

    def cmd_whoami(self, chat_id: int, _args: str) -> None:
        self.send(
            chat_id, f"Ваш Telegram ID: {self.config.owner_id}\nЧат: {chat_id}", MAIN_KEYBOARD
        )

    # --- autonomous session --------------------------------------------
    @staticmethod
    def _session_data(item: Any) -> dict[str, Any]:
        return {
            "pid": item.pid,
            "cwd": item.cwd,
            "kind": item.kind,
            "session_id": item.session_id,
            "name": item.name,
            "status": item.status,
            "state": item.state,
            "waiting_for": item.waiting_for,
            "started_at": item.started_at,
            "reference": item.reference,
            "active": item.active,
        }

    def _our_session(self, *, active_only: bool) -> dict[str, Any] | None:
        try:
            sessions = self.controller.list_sessions()
        except ClaudeError as exc:
            logger.warning("cannot list sessions: %s", exc)
            return None
        state = self.store.load_state()
        ours = [
            item
            for item in sessions
            if item.name == self.config.session_name or item.session_id == state.get("session_id")
        ]
        if active_only:
            ours = [item for item in ours if item.active]
        if not ours:
            return None
        item = max(ours, key=lambda value: value.started_at or 0)
        return self._session_data(item)

    def _active_session(self) -> dict[str, Any] | None:
        return self._our_session(active_only=True)

    def _any_our_session(self) -> dict[str, Any] | None:
        return self._our_session(active_only=False)

    def start_autonomous(self, chat_id: int, *, resume: bool = False) -> None:
        with self._session_lock:
            self._start_autonomous_locked(chat_id, resume=resume)

    def _start_autonomous_locked(self, chat_id: int, *, resume: bool = False) -> None:
        if not self.config.allow_autonomous:
            self.send(
                chat_id,
                "Автономный запуск отключён (security gate). Владелец должен "
                "явно включить DEVCONTROL_ALLOW_AUTONOMOUS=1 после проверки "
                "модели угроз: Claude работает под вашим пользователем.",
                MAIN_KEYBOARD,
            )
            return
        if self.store.paused():
            self.send(chat_id, "Разработка на паузе.", MAIN_KEYBOARD)
            return
        state = self.store.load_state()
        try:
            sessions = self.controller.list_sessions()
        except ClaudeError as exc:
            self.send(chat_id, f"Claude CLI недоступен: {exc}", MAIN_KEYBOARD)
            return
        active = [item for item in sessions if item.active]
        if active:
            names = ", ".join(
                (item.name or item.session_id or str(item.pid) or "session") for item in active[:3]
            )
            self.send(
                chat_id,
                f"Уже есть активная сессия в проекте: {names}. Второй исполнитель не запускается.",
                MAIN_KEYBOARD,
            )
            return
        inbox_messages = read_jsonl(self.paths.inbox)
        resume_id = state.get("session_id") if resume else None
        prompt = self.build_prompt(inbox_messages, resume=bool(resume_id))
        self.store.update_state(status="STARTING", session_active=True, starting_at=utc_now())
        try:
            result: StartResult = self.controller.start(prompt, resume_id=resume_id)
        except ClaudeError as exc:
            self.store.update_state(status="IDLE", session_active=False, starting_at=None)
            self.send(chat_id, f"Не удалось запустить: {exc}", MAIN_KEYBOARD)
            return
        if not result.ok:
            self.store.update_state(status="IDLE", session_active=False, starting_at=None)
            self.send(chat_id, f"Не удалось запустить: {result.message}", MAIN_KEYBOARD)
            return
        session = result.session or {}
        session_ref = (
            session.get("reference")
            or parse_start_reference(result.raw)
            or state.get("session_ref")
            or ""
        )
        consumed = {str(message["id"]) for message in inbox_messages if message.get("id")}
        self.store.consume_inbox(consumed)
        self.store.update_state(
            status=RUNNING_STATUS,
            session_active=True,
            session_id=session.get("session_id") or state.get("session_id"),
            session_ref=session_ref or None,
            session_name=session.get("name") or self.config.session_name,
            session_started_at=utc_now(),
            starting_at=None,
            last_error=None,
            pause_requested=False,
        )
        self.store.append_event("session_started", detail=result.message)
        self.notify(f"▶️ Запущена автономная сессия.\n{result.message}")
        self.send(chat_id, "Автономная разработка запущена.", MAIN_KEYBOARD)

    def build_prompt(self, inbox_messages: list[dict[str, Any]], *, resume: bool) -> str:
        base = ""
        try:
            base = self.config.prompt_path.read_text(encoding="utf-8")
        except OSError:
            base = (
                "Continue autonomous Breaktime Arcade development. "
                "Read docs/handoff/NOW.md, PROJECT_STATUS.md, BACKLOG.md and "
                "OWNER_DECISIONS.md; pick the highest-priority unblocked task; "
                "use Pro for plan/review and Flash for implementation; test, "
                "update registers, commit and push after checks."
            )
        lines = [base.strip()]
        if inbox_messages:
            lines.append("\nСообщения владельца из Telegram:")
            for message in inbox_messages:
                text = str(message.get("text") or "").strip()
                if text:
                    lines.append(f"- {text[:2000]}")
        lines.append(
            "\nRuntime: emit events with "
            "`python3 devcontrol/status_cli.py event ...`; check "
            "`$DEVCONTROL_RUNTIME_DIR/PAUSE` (default ~/.local/state/ba-devcontrol) and "
            "`python3 devcontrol/status_cli.py inbox --consume` "
            "at every task boundary. Use `status_cli.py pending` for D-class owner decisions."
        )
        if resume:
            lines.append("Continue the existing session; do not restart completed work.")
        return "\n".join(lines)

    def enqueue_ask(self, chat_id: int, text: str) -> None:
        text = text.strip()
        if not text:
            return
        message = self.store.enqueue_inbox(text[:4000])
        if self._active_session():
            self.send(
                chat_id,
                "Сообщение поставлено в очередь; агент прочитает его на ближайшей границе задачи.",
                MAIN_KEYBOARD,
            )
        else:
            self.send(
                chat_id,
                "Сообщение сохранено. Запустите /continue, чтобы агент его получил.",
                MAIN_KEYBOARD,
            )
        self.store.append_event("owner_message", detail=message["id"])

    # --- monitoring / notifications ------------------------------------
    def monitor_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.monitor_once()
            except Exception:
                logger.exception("monitor error")
            self._stop.wait(self.config.monitor_interval)

    def monitor_once(self) -> None:
        state = self.store.load_state()
        now = time.time()
        if state.get("status") == "STARTING":
            try:
                age = now - _parse_ts(str(state.get("starting_at") or ""))
            except ValueError:
                age = 9999
            if age < 60:
                return
            self.store.update_state(status="IDLE", session_active=False, starting_at=None)
            state = self.store.load_state()
        session = None
        try:
            session = self._active_session()
        except ClaudeError:
            session = None
        if session:
            self.store.update_state(
                session_active=True,
                heartbeat_at=utc_now(),
                session_id=session.get("session_id") or state.get("session_id"),
                session_name=session.get("name") or state.get("session_name"),
            )
            if state.get("status") not in {PAUSED_STATUS, "BLOCKED", "REVIEW"}:
                self.store.update_state(status=RUNNING_STATUS)
        elif state.get("session_active"):
            self.store.update_state(session_active=False)
            if state.get("status") == RUNNING_STATUS:
                self.store.update_state(status="IDLE")
            self.notify("ℹ️ Фоновая сессия завершилась или недоступна. /status, /logs, /resume.")
        events, offset = self.store.events_since(int(state.get("events_offset") or 0))
        for event in events:
            self.apply_event(event)
        if events:
            self.store.update_state(events_offset=offset)
        current = self.store.load_state()
        heartbeat = current.get("heartbeat_at")
        if current.get("status") == RUNNING_STATUS and heartbeat:
            try:
                age = now - _parse_ts(heartbeat)
            except ValueError:
                age = 0
            if (
                age > STALE_HEARTBEAT_SECONDS
                and now - self._last_stale_notice > STALE_HEARTBEAT_SECONDS
            ):
                self._last_stale_notice = now
                self.notify(
                    f"⚠️ Нет heartbeat {int(age // 60)} мин. "
                    "Это не доказательство зависания; проверьте /status и /logs."
                )

    def apply_event(self, event: dict[str, Any]) -> None:
        name = event.get("event")
        if not isinstance(name, str):
            return
        updates: dict[str, Any] = {
            "last_event": name,
            "last_event_at": event.get("ts"),
        }
        if event.get("task"):
            updates["current_task"] = event["task"]
        if event.get("title"):
            updates["current_title"] = event["title"]
        if name == "task_started":
            updates["status"] = RUNNING_STATUS
        elif name in {"task_completed", "session_stop"}:
            updates["status"] = "IDLE" if name == "session_stop" else RUNNING_STATUS
        elif name == "review_reject":
            updates["status"] = "REVIEW"
        elif name == "blocked":
            updates["status"] = "BLOCKED"
        elif name == "error":
            updates["status"] = "ERROR"
        elif name in {"owner_decision_required", "permission_request"}:
            updates["status"] = "BLOCKED"
        elif name == "session_end":
            updates["status"] = "IDLE"
            updates["session_active"] = False
        elif name == "turn_done":
            updates["last_message"] = event.get("detail")
        self.store.update_state(**updates)
        if name == "heartbeat":
            return
        text = self.event_text(event)
        if text:
            self.notify(text)
        if event.get("id"):
            self.store.update_state(last_notified_event=event["id"])

    def event_text(self, event: dict[str, Any]) -> str:
        name = event.get("event")
        task = event.get("task") or ""
        title = event.get("title") or ""
        detail = (event.get("detail") or "")[:800]
        prefix = {
            "task_started": "▶️ Задача начата",
            "task_completed": "✅ Задача завершена",
            "review_accept": "✅ Ревью принято",
            "review_reject": "❌ Ревью отклонило",
            "blocked": "⛔ Задача заблокирована",
            "tests_failed": "❌ Тесты упали",
            "owner_decision_required": "❓ Требуется решение владельца",
            "milestone": "🏁 Этап завершён",
            "security_critical": "🚨 Критическая проблема безопасности",
            "session_stop": "⏹ Сессия остановлена",
            "session_end": "⏹ Сессия завершена",
            "permission_request": "🔐 Запрос разрешения",
            "error": "⚠️ Ошибка",
            "commit": "📦 Коммит",
            "push": "🚀 Push",
        }.get(str(name), "")
        if not prefix:
            return ""
        lines = [prefix]
        if task:
            lines.append(task)
        if title:
            lines.append(title)
        if detail:
            lines.append(detail)
        return "\n".join(lines)

    # --- helpers --------------------------------------------------------
    def notify(self, text: str) -> None:
        try:
            self.client.send_long_message(self.config.owner_id, sanitize_text(text))
        except TelegramError as exc:
            logger.warning("notification failed: %s", exc)

    def send(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        try:
            self.client.send_long_message(chat_id, sanitize_text(text), reply_markup=reply_markup)
        except TelegramError as exc:
            logger.warning("send failed: %s", exc)

    def status_text(self) -> str:
        state = self.store.load_state()
        live = None
        try:
            live = self._active_session()
        except ClaudeError:
            live = None
        try:
            all_sessions = self.controller.list_sessions()
        except ClaudeError:
            all_sessions = []
        lines = [
            "Статус проекта",
            f"• Статус: {state.get('status', 'IDLE')}",
            f"• Задача: {state.get('current_task') or '—'}",
            f"• Сессия: {(live or {}).get('name') or state.get('session_name') or '—'}",
            f"• Активна: {'да' if live else 'нет'}",
            f"• Live: {(live or {}).get('state') or (live or {}).get('status') or '—'}",
            f"• Ждёт: {(live or {}).get('waiting_for') or '—'}",
            f"• Сессий в проекте: {len(all_sessions)}",
            f"• Пауза: {'да' if self.store.paused() else 'нет'}",
            f"• Автозапуск: {'вкл' if self.config.allow_autonomous else 'выкл (security gate)'}",
            f"• Heartbeat: {state.get('heartbeat_at') or '—'}",
            f"• Last event: {state.get('last_event') or '—'}",
        ]
        pending = self.store.read_pending_owner()
        if pending:
            lines.append(f"• Ждёт решения: {pending.get('task') or '—'}")
        return "\n".join(lines)

    def _backlog_rows(self) -> list[dict[str, str]]:
        path = self.config.project_dir / "docs" / "status" / "BACKLOG.md"
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        rows: list[dict[str, str]] = []
        for line in lines:
            if not line.strip().startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 5 or cells[0] in {"ID", "---"} or set(cells[0]) <= {"-", ":"}:
                continue
            rows.append(
                {
                    "id": cells[0],
                    "title": cells[1],
                    "status": cells[3],
                    "notes": cells[4],
                }
            )
        return rows

    def _next_ready(self, rows: list[dict[str, str]]) -> dict[str, str] | None:
        for row in rows:
            if "READY" in row["status"].upper():
                return row
        return None

    def _latest_report(self) -> Path | None:
        reports = sorted(
            (self.config.project_dir / "docs" / "foundation").glob("*_REPORT.md"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        return reports[0] if reports else None


_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[@-_]")
_TUI_NOISE = (
    "Hatching…",
    "Hatching...",
    "tokens · thinking",
    "Cogitated for",
    "esc to interrupt",
)


def clean_cli_log(text: str, *, max_lines: int = 40) -> str:
    """Turn the raw TUI snapshot from `claude logs` into short plain text."""
    text = _ANSI_RE.sub("", text)
    lines: list[str] = []
    for raw in text.replace("\r", "\n").splitlines():
        line = raw.strip()
        if not line:
            continue
        if any(noise in line for noise in _TUI_NOISE):
            continue
        lines.append(line)
    return "\n".join(lines[-max_lines:])


def _parse_ts(value: str) -> float:
    from datetime import datetime

    return datetime.fromisoformat(value).timestamp()


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BA Dev Control Telegram bot")
    parser.add_argument("--check", action="store_true", help="validate config and exit")
    parser.add_argument("--creds", type=Path, default=None)
    parser.add_argument("--project-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    _configure_logging()
    try:
        config = Config.load(
            creds_path=args.creds,
            project_dir=args.project_dir,
            require_secrets=not args.check,
        )
    except ConfigError as exc:
        logger.error("%s", exc)
        return 2
    if args.check:
        sys.stdout.write("config OK\n")
        return 0
    app = App(config)
    signal.signal(signal.SIGTERM, app.stop)
    signal.signal(signal.SIGINT, app.stop)
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
