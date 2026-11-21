"""Fake-transport coverage for autonomous Telegram notifications."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest
from autonomy.budget import WALL_CLOCK, Budget
from autonomy.notifier import (
    FATAL_ERROR,
    RUN_BUDGET_STOP,
    TASK_BLOCKED,
    TASK_COMPLETED,
    TASK_REJECTED,
    NotificationEvent,
    NotificationResult,
    Notifier,
    NotifierSettings,
)
from autonomy.orchestrator import Orchestrator
from autonomy.runner import RunResult
from autonomy.state import StateStore, Task
from devcontrol.telegram import TelegramError

TOKEN = "12345678:abcdefghijklmnopqrstuvwxyzABCDE"


class FakeTransport:
    """Transport double: returns queued outcomes or raises queued exceptions."""

    def __init__(self, outcomes: list[Any] | None = None) -> None:
        self.outcomes = list(outcomes or [])
        self.calls: list[tuple[int, str]] = []

    def send_message(self, chat_id: int, text: str) -> object:
        self.calls.append((chat_id, text))
        if not self.outcomes:
            return {"ok": True}
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _settings(**overrides: Any) -> NotifierSettings:
    values: dict[str, Any] = {"token": TOKEN, "chat_id": 111}
    values.update(overrides)
    return NotifierSettings(**values)


def _event(kind: str = TASK_COMPLETED, **overrides: Any) -> NotificationEvent:
    values: dict[str, Any] = {
        "task": "AUTONOMY-NOTIFY-1",
        "title": "Notify",
        "status": "completed",
        "usage": {"total_tokens": 12, "cost_usd": 0.5},
    }
    values.update(overrides)
    return NotificationEvent(kind, **values)


def test_notifier_sends_structured_event_without_leaking_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    transport = FakeTransport()
    notifier = Notifier(_settings(), transport=transport, sleep=lambda _delay: None)

    with caplog.at_level(logging.INFO, logger="autonomy.notifier"):
        result = notifier.notify(_event())

    assert result.status == "sent"
    assert result.attempts == 1
    assert transport.calls[0][0] == 111
    text = transport.calls[0][1]
    assert "task_completed" in text
    assert "AUTONOMY-NOTIFY-1" in text
    assert "токены=12" in text
    assert "стоимость=$0.5" in text
    assert TOKEN not in text
    assert "notification sent" in caplog.text
    assert TOKEN not in caplog.text


def test_notifier_retries_retryable_error_then_succeeds() -> None:
    sleeps: list[float] = []
    transport = FakeTransport([TelegramError("flood control", retry_after=7, status_code=429)])
    notifier = Notifier(
        _settings(max_attempts=2),
        transport=transport,
        sleep=sleeps.append,
    )

    result = notifier.notify(_event())

    assert result.status == "sent"
    assert result.attempts == 2
    assert len(transport.calls) == 2
    assert sleeps == [7.0]


def test_notifier_skips_when_token_missing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    notifier = Notifier.from_env(env={}, creds_path=tmp_path / "absent.env")
    transport = FakeTransport()
    notifier._transport = transport

    with caplog.at_level(logging.INFO, logger="autonomy.notifier"):
        result = notifier.notify(_event())

    assert result.status == "skipped"
    assert result.attempts == 0
    assert result.reason == "missing bot token"
    assert transport.calls == []
    assert "notification skipped" in caplog.text
    assert TOKEN not in caplog.text


def test_notifier_skips_network_failure_without_raising(
    caplog: pytest.LogCaptureFixture,
) -> None:
    transport = FakeTransport(
        [
            TelegramError("network error: unreachable"),
            TelegramError("network error: unreachable"),
        ]
    )
    notifier = Notifier(
        _settings(max_attempts=2),
        transport=transport,
        sleep=lambda _delay: None,
    )

    with caplog.at_level(logging.INFO, logger="autonomy.notifier"):
        result = notifier.notify(_event())

    assert result.status == "skipped"
    assert result.attempts == 2
    assert "network error" in (result.reason or "")
    assert "notification retry" in caplog.text
    assert "notification skipped" in caplog.text
    assert TOKEN not in caplog.text


def test_notifier_does_not_retry_auth_error_and_redacts_secret(
    caplog: pytest.LogCaptureFixture,
) -> None:
    transport = FakeTransport([TelegramError(f"Unauthorized {TOKEN}", status_code=401)])
    sleeps: list[float] = []
    notifier = Notifier(
        _settings(max_attempts=3),
        transport=transport,
        sleep=sleeps.append,
    )

    with caplog.at_level(logging.INFO, logger="autonomy.notifier"):
        result = notifier.notify(_event())

    assert result.status == "skipped"
    assert result.attempts == 1
    assert sleeps == []
    assert TOKEN not in caplog.text
    assert "<redacted>" in caplog.text


def test_settings_load_owner_config_without_exposing_secret(tmp_path: Path) -> None:
    creds = tmp_path / "telegram.env"
    creds.write_text(
        f"TELEGRAM_BOT_TOKEN={TOKEN}\nTELEGRAM_CHAT_ID=222\n",
        encoding="utf-8",
    )
    creds.chmod(0o600)

    settings = NotifierSettings.from_env(env={}, creds_path=creds)

    assert settings.enabled
    assert settings.chat_id == 222
    assert TOKEN not in repr(settings)


class RecordingNotifier(Notifier):
    def __init__(self) -> None:
        super().__init__(NotifierSettings())
        self.events: list[NotificationEvent] = []

    def notify(self, event: NotificationEvent) -> NotificationResult:
        self.events.append(event)
        return NotificationResult("sent", 1)


class StubRunner:
    def __init__(
        self,
        *,
        verdict: str = "accept",
        tokens: int = 0,
        cost: float = 0.0,
    ) -> None:
        self.verdict = verdict
        self.tokens = tokens
        self.cost = cost

    def _result(self, role: str, model: str, result: str = "{}") -> RunResult:
        return RunResult(
            role=role,
            model=model,
            agent=role,
            returncode=0,
            session_id=f"session-{role}",
            model_usage={
                model: {
                    "inputTokens": self.tokens,
                    "outputTokens": 0,
                    "cacheReadInputTokens": 0,
                    "cacheCreationInputTokens": 0,
                    "costUSD": self.cost,
                }
            },
            result=result,
            evidence_path=f"/tmp/{role}.json",
            duration_seconds=0.1,
            total_cost_usd=self.cost,
        )

    def architect(self, prompt: str) -> RunResult:
        del prompt
        return self._result("architect", "deepseek-v4-pro", '{"tasks": []}')

    def developer(self, prompt: str) -> RunResult:
        del prompt
        return self._result(
            "developer",
            "deepseek-flash[1m]",
            '{"status":"done","files":["tests/unit/test_autonomy_notify.py"],'
            '"self_check":{"spec_reviewed":true,"scope_reviewed":true,'
            '"tests_run":["targeted"],"localization_reviewed":true,"known_limits":[]}}',
        )

    def qa(self, prompt: str) -> RunResult:
        del prompt
        return self._result("qa", "deepseek-flash", '{"status":"pass"}')

    def reviewer(self, prompt: str) -> RunResult:
        del prompt
        import json

        return self._result(
            "reviewer",
            "deepseek-v4-pro",
            json.dumps({"verdict": self.verdict, "findings": ["finding"]}),
        )


def _orchestrator(
    tmp_path: Path,
    runner: StubRunner,
    notifier: Notifier,
    *,
    budget: Budget | None = None,
) -> tuple[Orchestrator, StateStore]:
    store = StateStore(tmp_path)
    store.enqueue(
        [Task(id="AUTONOMY-NOTIFY-OK", title="Notify", priority="Major", acceptance=["a"])]
    )
    orchestrator = Orchestrator(
        runner,
        store,
        commit=False,
        worktrees=False,
        budget=budget,
        notifier=notifier,
    )
    return orchestrator, store


def test_orchestrator_notifies_task_completion(tmp_path: Path) -> None:
    notifier = RecordingNotifier()
    orchestrator, store = _orchestrator(tmp_path, StubRunner(), notifier)

    report = orchestrator.run_once(propose=False)

    assert report["status"] == "completed"
    assert store.get("AUTONOMY-NOTIFY-OK").status == "COMPLETED"
    assert [event.kind for event in notifier.events] == [TASK_COMPLETED]
    assert notifier.events[0].task == "AUTONOMY-NOTIFY-OK"


def test_orchestrator_notifies_rejection_then_blocked(tmp_path: Path) -> None:
    notifier = RecordingNotifier()
    orchestrator, _store = _orchestrator(tmp_path, StubRunner(verdict="reject"), notifier)

    first = orchestrator.run_once(propose=False)
    second = orchestrator.run_once(propose=False)

    assert first["status"] == "retry"
    assert second["status"] == "blocked"
    assert [event.kind for event in notifier.events] == [TASK_REJECTED, TASK_BLOCKED]
    assert notifier.events[0].task == "AUTONOMY-NOTIFY-OK"
    assert notifier.events[1].reason


def test_orchestrator_notifies_budget_stop(tmp_path: Path) -> None:
    notifier = RecordingNotifier()
    budget = Budget(max_tasks=2, max_run_seconds=0.0)
    orchestrator, _store = _orchestrator(
        tmp_path,
        StubRunner(tokens=5),
        notifier,
        budget=budget,
    )

    report = orchestrator.run_once(propose=False)

    assert report["status"] == "stopped"
    assert report["budget_reason"] == WALL_CLOCK
    assert [event.kind for event in notifier.events] == [RUN_BUDGET_STOP]
    assert notifier.events[0].reason == WALL_CLOCK
    assert notifier.events[0].usage is not None


def test_orchestrator_notifies_fatal_error_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    notifier = RecordingNotifier()
    runner = StubRunner()
    store = StateStore(tmp_path)
    store.enqueue([Task(id="AUTONOMY-NOTIFY-F", title="Fatal", priority="Major", acceptance=["a"])])
    orchestrator = Orchestrator(
        runner,
        store,
        commit=False,
        worktrees=False,
        notifier=notifier,
    )

    error = RuntimeError("queue is corrupt")

    def boom() -> Task | None:
        raise error

    monkeypatch.setattr(store, "claim_next", boom)

    with pytest.raises(RuntimeError, match="queue is corrupt"):
        orchestrator.run_once(propose=False)
    orchestrator.notify_fatal(error)

    assert [event.kind for event in notifier.events] == [FATAL_ERROR]
    assert notifier.events[0].reason == "RuntimeError"
    assert "queue is corrupt" in (notifier.events[0].detail or "")


def test_notification_failure_does_not_break_task(tmp_path: Path) -> None:
    transport = FakeTransport([TelegramError("network error: unreachable")])
    notifier = Notifier(
        _settings(max_attempts=1),
        transport=transport,
        sleep=lambda _delay: None,
    )
    orchestrator, _store = _orchestrator(tmp_path, StubRunner(), notifier)

    report = orchestrator.run_once(propose=False)

    assert report["status"] == "completed"
    assert len(transport.calls) == 1
