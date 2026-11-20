from __future__ import annotations

import io
import json
import stat
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from devcontrol.bot import App
from devcontrol.claude import ClaudeSession, StartResult
from devcontrol.config import Config
from devcontrol.store import RuntimePaths, StateStore
from devcontrol.telegram import sanitize_text


class FakeTelegram:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str, dict[str, Any] | None]] = []
        self.callback_answers: list[tuple[str, str | None]] = []

    def send_long_message(
        self,
        chat_id: int,
        text: str,
        *,
        reply_markup: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.sent.append((chat_id, text, reply_markup))
        return []

    def answer_callback_query(self, callback_id: str, text: str | None = None) -> None:
        self.callback_answers.append((callback_id, text))

    def get_me(self) -> dict[str, Any]:
        return {"username": "test_bot"}

    def get_updates(self, offset: int, timeout: int = 25) -> list[dict[str, Any]]:
        return []

    @property
    def last_text(self) -> str:
        return self.sent[-1][1] if self.sent else ""


class FakeController:
    def __init__(self) -> None:
        self.sessions: list[ClaudeSession] = []
        self.start_calls: list[tuple[str, str | None]] = []
        self.stop_calls: list[str] = []
        self.logs_text = "log line"

    def list_sessions(self) -> list[ClaudeSession]:
        return list(self.sessions)

    def start(self, prompt: str, *, resume_id: str | None = None) -> StartResult:
        self.start_calls.append((prompt, resume_id))
        self.sessions = [
            ClaudeSession(
                pid=1,
                cwd="",
                kind="background",
                session_id="11111111-1111-1111-1111-111111111111",
                name="BA autonomous",
                status="busy",
                started_at=1,
                raw_id="abc123",
                state="working",
            )
        ]
        return StartResult(
            True,
            "started",
            session={
                "session_id": "11111111-1111-1111-1111-111111111111",
                "name": "BA autonomous",
                "reference": "abc123",
                "status": "busy",
            },
        )

    def stop(self, reference: str) -> tuple[bool, str]:
        self.stop_calls.append(reference)
        return True, "stopped"

    def logs(self, reference: str, *, max_chars: int = 3500) -> str:
        return self.logs_text[-max_chars:]


def _config(tmp_path: Path) -> Config:
    project = tmp_path / "project"
    (project / "docs" / "status").mkdir(parents=True)
    (project / "docs" / "foundation").mkdir(parents=True)
    (project / "devcontrol" / "prompts").mkdir(parents=True)
    (project / "devcontrol" / "prompts" / "autonomous.md").write_text(
        "AUTONOMOUS PROMPT\n", encoding="utf-8"
    )
    (project / "docs" / "status" / "BACKLOG.md").write_text(
        "| ID | Title | Priority | Status | Notes |\n"
        "|---|---|---|---|---|\n"
        "| BA-1 | First | Critical | READY | note |\n"
        "| BA-2 | Second | Major | BLOCKED | note |\n",
        encoding="utf-8",
    )
    (project / "docs" / "foundation" / "BA-1_REPORT.md").write_text(
        "REPORT BODY\n", encoding="utf-8"
    )
    return Config(
        token="123456:abcdefghijklmnopqrstuvwxyzABCDE",
        owner_id=111,
        project_dir=project,
        runtime_dir=project / "var" / "devcontrol",
        creds_path=project / "creds" / "telegram.env",
        session_name="BA autonomous",
        monitor_interval=1,
        allow_autonomous=True,
    )


def _app(tmp_path: Path) -> tuple[App, FakeTelegram, FakeController]:
    config = _config(tmp_path)
    client = FakeTelegram()
    controller = FakeController()
    app = App(config, client=client, controller=controller)  # type: ignore[arg-type]
    return app, client, controller


def _message(text: str, user_id: int = 111) -> dict[str, Any]:
    return {
        "message": {
            "from": {"id": user_id},
            "chat": {"id": user_id},
            "text": text,
        }
    }


def _callback(data: str, callback_id: str = "cb-1", user_id: int = 111) -> dict[str, Any]:
    return {
        "callback_query": {
            "id": callback_id,
            "from": {"id": user_id},
            "message": {"chat": {"id": user_id}},
            "data": data,
        }
    }


def test_unauthorized_user_is_ignored(tmp_path: Path) -> None:
    app, client, controller = _app(tmp_path)

    app.handle_update(_message("/status", user_id=222))

    assert client.sent == []
    assert controller.start_calls == []


def test_start_and_status(tmp_path: Path) -> None:
    app, client, _controller = _app(tmp_path)

    app.handle_update(_message("/start"))
    assert "BA Dev Control" in client.last_text

    app.handle_update(_message("/status"))
    assert "Статус проекта" in client.last_text


def test_autonomous_is_opt_in_by_default(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config = Config(
        token=config.token,
        owner_id=config.owner_id,
        project_dir=config.project_dir,
        runtime_dir=config.runtime_dir,
        creds_path=config.creds_path,
        session_name=config.session_name,
        monitor_interval=1,
    )
    client = FakeTelegram()
    controller = FakeController()
    app = App(config, client=client, controller=controller)  # type: ignore[arg-type]

    app.handle_update(_message("/continue"))

    assert controller.start_calls == []
    assert "security gate" in client.last_text


def test_continue_refuses_second_session(tmp_path: Path) -> None:
    app, client, controller = _app(tmp_path)
    controller.sessions = [
        ClaudeSession(
            pid=1,
            cwd=str(app.config.project_dir),
            kind="interactive",
            session_id="other",
            name="other",
            status="busy",
            started_at=None,
            raw_id=None,
        )
    ]

    app.handle_update(_message("/continue"))

    assert controller.start_calls == []
    assert "активная сессия" in client.last_text


def test_continue_starts_and_consumes_inbox(tmp_path: Path) -> None:
    app, client, controller = _app(tmp_path)
    app.store.enqueue_inbox("owner note")

    app.handle_update(_message("/continue"))

    assert len(controller.start_calls) == 1
    prompt, resume_id = controller.start_calls[0]
    assert "AUTONOMOUS PROMPT" in prompt
    assert "owner note" in prompt
    assert resume_id is None
    state = app.store.load_state()
    assert state["status"] == "RUNNING"
    assert state["session_id"] == "11111111-1111-1111-1111-111111111111"
    assert app.store.consume_inbox() == []
    assert (
        "запущена" in client.last_text.lower()
        or "запущена" in "".join(text for _, text, _ in client.sent).lower()
    )


def test_continue_is_idempotent(tmp_path: Path) -> None:
    app, _client, controller = _app(tmp_path)

    app.handle_update(_message("/continue"))
    app.handle_update(_message("/continue"))

    assert len(controller.start_calls) == 1


def test_stale_stop_confirmation_is_rejected(tmp_path: Path) -> None:
    app, client, controller = _app(tmp_path)
    app.store.update_state(session_id="sess-1", session_active=True)
    controller.sessions = [
        ClaudeSession(
            pid=1,
            cwd=str(app.config.project_dir),
            kind="background",
            session_id="sess-1",
            name="BA autonomous",
            status="busy",
            started_at=1,
            raw_id="abc123",
            state="working",
        )
    ]

    stale = int(time.time()) - 10_000
    app.handle_update(_callback(f"stop_confirm:{stale}", callback_id="cb-stale"))

    assert controller.stop_calls == []
    assert "устарело" in client.last_text.lower()


def test_unauthorized_callback_is_rejected(tmp_path: Path) -> None:
    app, client, controller = _app(tmp_path)

    app.handle_update(_callback("status", callback_id="cb-other", user_id=222))

    assert client.sent == []
    assert controller.start_calls == []
    assert client.callback_answers[-1][1] == "Доступ запрещён"


def test_pause_blocks_continue_and_resume_starts(tmp_path: Path) -> None:
    app, client, controller = _app(tmp_path)

    app.handle_update(_message("/pause"))
    app.handle_update(_message("/continue"))
    assert controller.start_calls == []
    assert "паузе" in client.last_text.lower()

    app.handle_update(_message("/resume"))
    assert len(controller.start_calls) == 1
    assert not app.store.paused()


def test_stop_requires_confirmation_and_is_idempotent(tmp_path: Path) -> None:
    app, client, controller = _app(tmp_path)
    app.store.update_state(session_id="sess-1", session_active=True)
    controller.sessions = [
        ClaudeSession(
            pid=1,
            cwd=str(app.config.project_dir),
            kind="background",
            session_id="sess-1",
            name="BA autonomous",
            status="busy",
            started_at=None,
            raw_id="abc123",
        )
    ]

    app.handle_update(_message("/stop"))
    assert "Остановить" in client.last_text
    assert controller.stop_calls == []

    callback = _callback(f"stop_confirm:{int(time.time())}", callback_id="cb-stop")
    app.handle_update(callback)
    app.handle_update(callback)

    assert controller.stop_calls == ["abc123"]
    assert app.store.load_state()["status"] == "IDLE"


def test_ask_queues_message_and_asks_for_continue(tmp_path: Path) -> None:
    app, client, _controller = _app(tmp_path)

    app.handle_update(_message("/ask hello agent"))

    assert "сохранено" in client.last_text.lower()
    assert app.store.consume_inbox()[0]["text"] == "hello agent"


def test_monitor_notifies_new_events_once(tmp_path: Path) -> None:
    app, client, _controller = _app(tmp_path)
    app.store.append_event("task_completed", task="BA-1", title="First")

    app.monitor_once()
    app.monitor_once()

    notifications = [text for _, text, _ in client.sent if "Задача завершена" in text]
    assert len(notifications) == 1
    assert "BA-1" in notifications[0]


def test_progress_and_next_parse_backlog(tmp_path: Path) -> None:
    app, client, _controller = _app(tmp_path)

    app.handle_update(_message("/progress"))
    assert "READY: 1" in client.last_text
    assert "BLOCKED: 1" in client.last_text

    app.handle_update(_message("/next"))
    assert "BA-1" in client.last_text


def test_report_and_logs(tmp_path: Path) -> None:
    app, client, controller = _app(tmp_path)
    app.store.update_state(session_id="sess-1")
    controller.sessions = [
        ClaudeSession(
            pid=1,
            cwd=str(app.config.project_dir),
            kind="background",
            session_id="sess-1",
            name="BA autonomous",
            status="busy",
            started_at=None,
            raw_id="abc123",
        )
    ]

    app.handle_update(_message("/report"))
    assert "REPORT BODY" in client.last_text

    app.handle_update(_message("/logs"))
    assert "log line" in client.last_text


def test_store_is_atomic_and_private(tmp_path: Path) -> None:
    paths = RuntimePaths(tmp_path / "runtime")
    store = StateStore(paths)
    store.update_state(status="RUNNING", current_task="BA-1")
    assert store.load_state()["current_task"] == "BA-1"
    mode = stat.S_IMODE(paths.state.stat().st_mode)
    assert mode == 0o600

    store.enqueue_inbox("one")
    store.enqueue_inbox("two")
    assert [item["text"] for item in store.consume_inbox()] == ["one", "two"]
    assert store.consume_inbox() == []

    assert store.mark_update(5) is True
    assert store.mark_update(5) is False
    assert store.mark_callback("cb") is True
    assert store.mark_callback("cb") is False


def test_event_emitter_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import devcontrol.status_cli as cli

    monkeypatch.setattr(cli, "PATHS", RuntimePaths(tmp_path / "runtime"))
    assert cli.main(["event", "task_started", "--task", "BA-1"]) == 0
    store = StateStore(cli.PATHS)
    assert store.load_state()["current_task"] == "BA-1"
    events, _ = store.events_since(0)
    assert events[-1]["event"] == "task_started"


def test_sanitize_text_redacts_token() -> None:
    token = "123456:abcdefghijklmnopqrstuvwxyzABCDE"
    assert token not in sanitize_text(f"token={token}", token)
    assert "\x1b" not in sanitize_text("a\x1bb")
    assert "[31m" not in sanitize_text("\x1b[31mred\x1b[0m")


def test_sanitize_text_redacts_secret_values() -> None:
    text = (
        "DJANGO_SECRET_KEY=supersecret\n"
        "TELEGRAM_BOT_TOKEN=123456:abcdefghijklmnopqrstuvwxyzABCDE\n"
        "key=sk-1234567890abcdef\n"
        "postgres://user:hunter2@db:5432/ba"
    )
    clean = sanitize_text(text)
    assert "supersecret" not in clean
    assert "hunter2" not in clean
    assert "123456:abcdefghijklmnopqrstuvwxyzABCDE" not in clean
    assert "sk-1234567890abcdef" not in clean
    assert "<redacted>" in clean


def test_logs_redact_secrets(tmp_path: Path) -> None:
    app, client, controller = _app(tmp_path)
    app.store.update_state(session_id="sess-1")
    controller.logs_text = "DJANGO_SECRET_KEY=supersecret\nnormal line"
    controller.sessions = [
        ClaudeSession(
            pid=1,
            cwd=str(app.config.project_dir),
            kind="background",
            session_id="sess-1",
            name="BA autonomous",
            status="busy",
            started_at=1,
            raw_id="abc123",
            state="working",
        )
    ]

    app.handle_update(_message("/logs"))

    assert "normal line" in client.last_text
    assert "supersecret" not in client.last_text


def test_partial_inbox_consume_and_delivered_dedupe(tmp_path: Path) -> None:
    paths = RuntimePaths(tmp_path / "runtime")
    store = StateStore(paths)
    first = store.enqueue_inbox("one")
    store.enqueue_inbox("two")

    assert [item["text"] for item in store.consume_inbox({first["id"]})] == ["one"]
    assert [item["text"] for item in store.consume_inbox()] == ["two"]
    assert store.consume_inbox() == []


def test_corrupt_state_recovers(tmp_path: Path) -> None:
    paths = RuntimePaths(tmp_path / "runtime")
    paths.ensure()
    paths.state.write_text("{not-json", encoding="utf-8")
    store = StateStore(paths)

    assert store.load_state()["status"] == "IDLE"
    store.update_state(status="RUNNING")
    assert store.load_state()["status"] == "RUNNING"


def test_parse_start_reference_and_chunking() -> None:
    from devcontrol.claude import ClaudeSession, parse_start_reference
    from devcontrol.telegram import split_text

    raw = (
        "Starting background service...\n"
        "backgrounded · f4c68b9e · ba-bg-probe\n"
        "  claude stop f4c68b9e      stop this session\n"
    )
    assert parse_start_reference(raw) == "f4c68b9e"
    assert all(len(chunk) <= 4000 for chunk in split_text("x" * 9000))

    active = ClaudeSession(1, "/p", "background", "s", "n", "busy", 1, "id", "working")
    done = ClaudeSession(1, "/p", "background", "s", "n", "idle", 1, "id", "done")
    assert active.active is True
    assert done.active is False


def test_hooks_record_events_and_deny_permission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from devcontrol.hooks import on_permission, on_session_end, on_stop

    paths = RuntimePaths(tmp_path / "runtime")
    for module in (on_stop, on_permission, on_session_end):
        monkeypatch.setattr(module, "PATHS", paths)

    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(json.dumps({"session_id": "s", "last_assistant_message": "done"})),
    )
    assert on_stop.main() == 0

    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})),
    )
    assert on_permission.main() == 0
    assert '"behavior": "deny"' in capsys.readouterr().out

    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"reason": "other"})))
    assert on_session_end.main() == 0

    events, _ = StateStore(paths).events_since(0)
    assert [event["event"] for event in events] == [
        "turn_done",
        "permission_request",
        "session_end",
    ]
    assert StateStore(paths).load_state()["last_message"] == "done"
