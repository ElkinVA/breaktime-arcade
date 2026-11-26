from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from autonomy.gate import (
    OwnerActionRequired,
    clear_gate,
    gate_path,
    load_gate,
    set_gate,
)
from autonomy.notifier import NotificationEvent, NotificationResult
from autonomy.orchestrator import Orchestrator
from autonomy.runner import RunResult
from autonomy.state import READY, StateStore, Task


class SkippedNotifier:
    def notify(self, event: NotificationEvent) -> NotificationResult:
        return NotificationResult("skipped", reason="not configured")


class RecordingNotifier:
    def __init__(self) -> None:
        self.events: list[NotificationEvent] = []

    def notify(self, event: NotificationEvent) -> NotificationResult:
        self.events.append(event)
        return NotificationResult("sent", attempts=1)


class RecordingWindows:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, title: str, message: str) -> object:
        self.calls.append((title, message))
        return None


class ForbiddenRunner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def _fail(self, role: str) -> Any:
        self.calls.append(role)
        raise AssertionError(f"{role} must not be called under an owner gate")

    def architect(self, *args: Any, **kwargs: Any) -> Any:
        return self._fail("architect")

    def developer(self, *args: Any, **kwargs: Any) -> Any:
        return self._fail("developer")

    def qa(self, *args: Any, **kwargs: Any) -> Any:
        return self._fail("qa")

    def reviewer(self, *args: Any, **kwargs: Any) -> Any:
        return self._fail("reviewer")


def _orchestrator(
    tmp_path: Path,
) -> tuple[Orchestrator, StateStore, ForbiddenRunner, RecordingNotifier, RecordingWindows]:
    store = StateStore(tmp_path)
    runner = ForbiddenRunner()
    notifier = RecordingNotifier()
    windows = RecordingWindows()
    orchestrator = Orchestrator(
        runner,  # type: ignore[arg-type]
        store,
        commit=False,
        worktrees=False,
        notifier=notifier,  # type: ignore[arg-type]
        windows_notifier=windows,
    )
    return orchestrator, store, runner, notifier, windows


def test_gate_blocks_tasks_and_notifies_once(tmp_path: Path) -> None:
    orchestrator, store, runner, notifier, windows = _orchestrator(tmp_path)
    store.enqueue([Task(id="GATED-001", title="Gated", priority="Minor", acceptance=["x"])])
    set_gate(tmp_path, reason="owner review", requested_action="approve the plan")

    first = orchestrator.run_once(propose=False)
    second = orchestrator.run_once(propose=False)

    assert first["status"] == "paused"
    assert first["reason"] == "OWNER_ACTION_REQUIRED"
    assert first["gate"]["reason"] == "owner review"
    assert second["status"] == "paused"
    assert runner.calls == []
    stored = store.get("GATED-001")
    assert stored is not None
    assert stored.status == READY
    assert len(notifier.events) == 1
    assert notifier.events[0].kind == "owner_action_required"
    assert len(windows.calls) == 1
    assert load_gate(tmp_path).notified_at is not None  # type: ignore[union-attr]
    assert gate_path(tmp_path).stat().st_mode & 0o777 == 0o600


def test_propose_refuses_while_gated(tmp_path: Path) -> None:
    orchestrator, _store, runner, _notifier, _windows = _orchestrator(tmp_path)
    set_gate(tmp_path, reason="owner review")

    with pytest.raises(OwnerActionRequired):
        orchestrator.propose()

    assert runner.calls == []


def test_malformed_gate_is_fail_closed(tmp_path: Path) -> None:
    orchestrator, _store, runner, notifier, _windows = _orchestrator(tmp_path)
    gate_path(tmp_path).write_text("{not json", encoding="utf-8")

    report = orchestrator.run_once(propose=False)

    assert report["status"] == "paused"
    assert "unreadable" in report["gate"]["reason"]
    assert runner.calls == []
    assert notifier.events


def test_non_regular_gate_is_fail_closed(tmp_path: Path) -> None:
    orchestrator, _store, runner, _notifier, _windows = _orchestrator(tmp_path)
    gate_path(tmp_path).mkdir()

    report = orchestrator.run_once(propose=False)

    assert report["status"] == "paused"
    assert "not a regular file" in report["gate"]["reason"]
    assert runner.calls == []


def test_dangling_symlink_gate_is_fail_closed(tmp_path: Path) -> None:
    orchestrator, _store, runner, _notifier, _windows = _orchestrator(tmp_path)
    gate_path(tmp_path).symlink_to(tmp_path / "missing-gate-target")

    report = orchestrator.run_once(propose=False)

    assert report["status"] == "paused"
    assert "not a regular file" in report["gate"]["reason"]
    assert runner.calls == []


def test_gate_notification_retries_until_a_channel_succeeds(tmp_path: Path) -> None:
    set_gate(tmp_path, reason="owner review")
    store = StateStore(tmp_path)
    runner = ForbiddenRunner()
    skipped = Orchestrator(
        runner,  # type: ignore[arg-type]
        store,
        commit=False,
        worktrees=False,
        notifier=SkippedNotifier(),  # type: ignore[arg-type]
        windows_notifier=lambda *_: None,
    )
    skipped.run_once(propose=False)
    assert load_gate(tmp_path).notified_at is None  # type: ignore[union-attr]

    delivered = Orchestrator(
        runner,  # type: ignore[arg-type]
        store,
        commit=False,
        worktrees=False,
        notifier=RecordingNotifier(),  # type: ignore[arg-type]
        windows_notifier=lambda *_: None,
    )
    delivered.run_once(propose=False)
    assert load_gate(tmp_path).notified_at is not None  # type: ignore[union-attr]


def test_stop_file_wins_over_gate(tmp_path: Path) -> None:
    orchestrator, _store, runner, _notifier, _windows = _orchestrator(tmp_path)
    set_gate(tmp_path, reason="owner review")
    (tmp_path / "STOP").write_text("stop", encoding="utf-8")

    report = orchestrator.run_once(propose=False)

    assert report["status"] == "stopped"
    assert report["reason"] == "STOP file"
    assert runner.calls == []


def test_milestone_gate_and_resume(tmp_path: Path) -> None:
    orchestrator, store, runner, notifier, windows = _orchestrator(tmp_path)
    gate = set_gate(
        tmp_path,
        reason="milestone 1 done",
        kind="milestone",
        milestone="M1",
        requested_action="review milestone",
    )

    report = orchestrator.run_once(propose=False)
    assert report["reason"] == "MILESTONE_COMPLETED"
    assert report["gate"]["kind"] == "milestone"
    assert notifier.events[0].kind == "milestone_completed"
    assert windows.calls

    assert clear_gate(tmp_path) is True
    assert load_gate(tmp_path) is None
    assert gate.milestone == "M1"


def test_gate_set_between_cleanup_and_claim_prevents_claim(
    tmp_path: Path, monkeypatch: Any
) -> None:
    orchestrator, store, runner, _notifier, _windows = _orchestrator(tmp_path)
    store.enqueue([Task(id="RACE-001", title="Race", priority="Minor", acceptance=["x"])])
    monkeypatch.setattr(
        orchestrator,
        "_cleanup_orphan_worktrees",
        lambda: set_gate(tmp_path, reason="set during cleanup"),
    )

    report = orchestrator.run_once(propose=False)

    assert report["status"] == "paused"
    assert runner.calls == []
    task = store.get("RACE-001")
    assert task is not None
    assert task.status == READY


def test_gate_set_after_developer_prevents_qa_and_releases_task(tmp_path: Path) -> None:
    class GateRunner:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def _result(self, role: str) -> RunResult:
            return RunResult(
                role=role,
                model="deepseek-flash[1m]",
                agent=role,
                returncode=0,
                session_id=f"session-{role}",
                model_usage={},
                result=(
                    '{"status":"done","files":["tests/unit/test_autonomy_gate.py"],'
                    '"self_check":{"spec_reviewed":true,"scope_reviewed":true,'
                    '"tests_run":[],"localization_reviewed":true,"known_limits":[]}}'
                ),
                evidence_path=f"/tmp/{role}.json",
                duration_seconds=0.1,
            )

        def developer(self, *args: Any, **kwargs: Any) -> RunResult:
            self.calls.append("developer")
            set_gate(tmp_path, reason="set by developer")
            return self._result("developer")

        def qa(self, *args: Any, **kwargs: Any) -> RunResult:
            self.calls.append("qa")
            return self._result("qa")

        def reviewer(self, *args: Any, **kwargs: Any) -> RunResult:
            self.calls.append("reviewer")
            return self._result("reviewer")

    store = StateStore(tmp_path)
    store.enqueue([Task(id="RACE-QA", title="Race QA", priority="Minor", acceptance=["x"])])
    runner = GateRunner()
    orchestrator = Orchestrator(
        runner,  # type: ignore[arg-type]
        store,
        commit=False,
        worktrees=False,
        notifier=RecordingNotifier(),  # type: ignore[arg-type]
        windows_notifier=lambda *_: None,
    )

    report = orchestrator.run_once(propose=False)

    assert report["status"] == "paused"
    assert runner.calls == ["developer"]
    task = store.get("RACE-QA")
    assert task is not None
    assert task.status == READY


def test_gate_file_is_json_and_contains_no_runner_calls(tmp_path: Path) -> None:
    set_gate(
        tmp_path,
        reason="owner action",
        requested_action="do the thing",
        recommendation="recommended",
    )
    value = json.loads(gate_path(tmp_path).read_text(encoding="utf-8"))
    assert value["kind"] == "owner_action"
    assert value["requested_action"] == "do the thing"
    assert value["notified_at"] is None


def test_cli_pause_checkpoint_and_resume(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    from autonomy import orchestrator

    monkeypatch.setattr(orchestrator, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(orchestrator, "send_toast", lambda *args: None)
    monkeypatch.setattr(
        orchestrator.Notifier,
        "from_env",
        lambda *args, **kwargs: RecordingNotifier(),
    )

    assert orchestrator.main(["pause", "--reason", "owner review"]) == 0
    paused = json.loads(capsys.readouterr().out)
    assert paused["status"] == "PAUSED_FOR_OWNER"
    assert load_gate(tmp_path) is not None

    assert orchestrator.main(["resume"]) == 0
    resumed = json.loads(capsys.readouterr().out)
    assert resumed["status"] != "PAUSED_FOR_OWNER"
    assert load_gate(tmp_path) is None

    assert orchestrator.main(["checkpoint", "--milestone", "M1"]) == 0
    milestone = json.loads(capsys.readouterr().out)
    assert milestone["status"] == "MILESTONE_COMPLETED"
    assert milestone["gate"]["milestone"] == "M1"
