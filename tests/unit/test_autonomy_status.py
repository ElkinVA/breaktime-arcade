from __future__ import annotations

from pathlib import Path

from autonomy.gate import set_gate
from autonomy.state import BLOCKED, StateStore, Task
from autonomy.status_report import (
    BLOCKED as STATUS_BLOCKED,
)
from autonomy.status_report import (
    MILESTONE_COMPLETED,
    PAUSED_FOR_OWNER,
    RUNNING,
    STOPPED,
    STOPPED_ERROR,
    WAITING_FOR_NEXT_RUN,
    derive_status,
    write_last_report,
)

SYSTEMD = {"available": False}


def _store(tmp_path: Path) -> StateStore:
    store = StateStore(tmp_path)
    store.enqueue([Task(id="STATUS-001", title="Status", priority="Minor", acceptance=["status"])])
    return store


def test_waiting_and_snapshot_keys_are_preserved(tmp_path: Path) -> None:
    store = _store(tmp_path)
    report = derive_status(store, systemd_probe=lambda: SYSTEMD)
    for key in ("version", "current", "tasks", "runs", "usage", "metrics"):
        assert key in report
    assert report["status"] == WAITING_FOR_NEXT_RUN
    assert report["systemd"] == SYSTEMD


def test_inactive_timer_is_reported_as_blocked(tmp_path: Path) -> None:
    store = _store(tmp_path)
    systemd = {
        "available": True,
        "service": {"active_state": "failed"},
        "timer": {"active_state": "inactive"},
    }
    report = derive_status(store, systemd_probe=lambda: systemd)
    assert report["status"] == STATUS_BLOCKED
    assert report["reason"] == "heartbeat timer is inactive"


def test_gate_and_milestone_statuses(tmp_path: Path) -> None:
    store = _store(tmp_path)
    set_gate(tmp_path, reason="review")
    assert derive_status(store, systemd_probe=lambda: SYSTEMD)["status"] == PAUSED_FOR_OWNER

    set_gate(tmp_path, reason="milestone", kind="milestone", milestone="M1")
    assert derive_status(store, systemd_probe=lambda: SYSTEMD)["status"] == MILESTONE_COMPLETED


def test_stop_and_blocked_statuses(tmp_path: Path) -> None:
    store = _store(tmp_path)
    (tmp_path / "STOP").write_text("stop", encoding="utf-8")
    assert derive_status(store, systemd_probe=lambda: SYSTEMD)["status"] == STOPPED
    (tmp_path / "STOP").unlink()

    task = store.claim_next()
    assert task is not None
    store.transition(task.id, BLOCKED, blocked_reason="RETRY_LIMIT")
    assert derive_status(store, systemd_probe=lambda: SYSTEMD)["status"] == STATUS_BLOCKED


def test_stop_wins_over_gate_in_status(tmp_path: Path) -> None:
    store = _store(tmp_path)
    set_gate(tmp_path, reason="review")
    (tmp_path / "STOP").write_text("stop", encoding="utf-8")
    report = derive_status(store, systemd_probe=lambda: SYSTEMD)
    assert report["status"] == STOPPED
    assert report["gate"] is not None


def test_running_requires_a_live_probe(tmp_path: Path) -> None:
    store = _store(tmp_path)
    report = derive_status(
        store,
        systemd_probe=lambda: SYSTEMD,
        run_lock_probe=lambda _root: (True, None),
    )
    assert report["status"] == RUNNING


def test_last_fatal_event_maps_to_stopped_error(tmp_path: Path) -> None:
    store = _store(tmp_path)
    from autonomy.orchestrator import Orchestrator

    orchestrator = Orchestrator(
        object(),  # type: ignore[arg-type]
        store,
        commit=False,
        worktrees=False,
        windows_notifier=lambda *_: None,
    )
    orchestrator.notify_fatal(RuntimeError("boom"))
    report = derive_status(store, systemd_probe=lambda: SYSTEMD)
    assert report["status"] == STOPPED_ERROR
    assert report["last_result"]["event"] == "fatal_error"
    assert report["last_result"]["reason"] == "RuntimeError"


def test_last_report_is_written_atomically_with_0600(tmp_path: Path) -> None:
    store = _store(tmp_path)
    path = write_last_report(store, {"status": "paused", "reason": "owner"})
    assert path.exists()
    assert path.stat().st_mode & 0o777 == 0o600


def test_last_report_redacts_token_shaped_values(tmp_path: Path) -> None:
    store = _store(tmp_path)
    path = write_last_report(store, {"detail": "sk-" + "a" * 32})
    assert "sk-" + "a" * 32 not in path.read_text(encoding="utf-8")
