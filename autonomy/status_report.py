"""Derived AI Headquarters status for the owner and the ``autonomy status`` CLI.

The source of truth stays ``state.json`` / ``events.jsonl`` / ``invocations.jsonl``.
This module only derives a human-readable loop state; it never changes the queue.
"""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import subprocess
import tempfile
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from devcontrol.telegram import sanitize_text

from autonomy.gate import KIND_MILESTONE, load_gate

RUNNING = "RUNNING"
WAITING_FOR_NEXT_RUN = "WAITING_FOR_NEXT_RUN"
PAUSED_FOR_OWNER = "PAUSED_FOR_OWNER"
MILESTONE_COMPLETED = "MILESTONE_COMPLETED"
BLOCKED = "BLOCKED"
STOPPED = "STOPPED"
STOPPED_ERROR = "STOPPED_ERROR"

SERVICE_UNIT = "ba-autonomy-orchestrator.service"
TIMER_UNIT = "ba-autonomy-orchestrator.timer"
JOURNAL_UNIT = "ba-autonomy-orchestrator"


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _read_jsonl_tail(path: Path, limit: int = 200) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError, ValueError:
                    continue
                if isinstance(value, dict):
                    rows.append(value)
    except OSError:
        return []
    return rows[-limit:]


def _event_time(event: dict[str, Any]) -> str | None:
    for key in ("ts", "at", "created_at", "started_at", "finished_at"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _run_lock_live(root: Path) -> tuple[bool, str | None]:
    path = Path(root) / "run.lock"
    if not path.exists():
        return False, None
    try:
        with path.open("a+") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                lock.seek(0)
                raw = lock.read().strip()
                pid = int(raw) if raw.isdigit() else None
                if pid is None:
                    return False, "run lock is held but PID is unknown"
                if not Path(f"/proc/{pid}").exists():
                    return False, f"run lock held by vanished pid {pid}"
                try:
                    stat_fields = Path(f"/proc/{pid}/stat").read_text().split()
                    if len(stat_fields) > 2 and stat_fields[2] == "Z":
                        return False, f"run lock held by zombie pid {pid}"
                    command = Path(f"/proc/{pid}/cmdline").read_bytes()
                except OSError:
                    return False, f"run lock pid {pid} is not observable"
                if b"autonomy.orchestrator" not in command:
                    return False, f"run lock pid {pid} is not the orchestrator"
                return True, None
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            return False, None
    except OSError as exc:
        return False, f"run lock probe failed: {type(exc).__name__}"


def _systemctl_show(unit: str, properties: list[str]) -> dict[str, str]:
    executable = shutil.which("systemctl")
    if executable is None:
        return {}
    command = [executable, "--user", "show", unit, "--no-pager"]
    command.extend(f"--property={name}" for name in properties)
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        command,
        text=True,
        capture_output=True,
        check=False,
        timeout=5,
    )
    if completed.returncode != 0:
        return {}
    values: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def _systemctl_timer_line(timer: str) -> str | None:
    executable = shutil.which("systemctl")
    if executable is None:
        return None
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [executable, "--user", "list-timers", "--all", "--no-pager"],
        text=True,
        capture_output=True,
        check=False,
        timeout=5,
    )
    if completed.returncode != 0:
        return None
    for line in completed.stdout.splitlines():
        if timer in line:
            return " ".join(line.split())
    return None


def probe_systemd() -> dict[str, Any]:
    """Best-effort systemd snapshot; never raises and never blocks a run."""
    try:
        service = _systemctl_show(
            SERVICE_UNIT,
            ["ActiveState", "SubState", "UnitFileState", "ExecMainPID"],
        )
        timer = _systemctl_show(
            TIMER_UNIT,
            ["ActiveState", "UnitFileState", "NextElapseUSecRealtime"],
        )
        timer_line = _systemctl_timer_line(TIMER_UNIT)
        return {
            "available": bool(service or timer),
            "service": {
                "unit": SERVICE_UNIT,
                "active_state": service.get("ActiveState", "unknown"),
                "sub_state": service.get("SubState", "unknown"),
                "unit_file_state": service.get("UnitFileState", "unknown"),
                "main_pid": service.get("ExecMainPID", "0"),
            },
            "timer": {
                "unit": TIMER_UNIT,
                "active_state": timer.get("ActiveState", "unknown"),
                "unit_file_state": timer.get("UnitFileState", "unknown"),
                "next_elapse": timer.get("NextElapseUSecRealtime") or timer_line,
            },
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "error": type(exc).__name__}


def _last_invocation(root: Path, task_id: str | None) -> dict[str, Any] | None:
    if not task_id:
        return None
    rows = _read_jsonl_tail(root / "invocations.jsonl")
    for row in reversed(rows):
        if row.get("task_id") == task_id and row.get("status") is None:
            return dict(row)
    for row in reversed(rows):
        if row.get("task_id") == task_id:
            return dict(row)
    return None


def _task_stage(task: dict[str, Any] | None, invocation: dict[str, Any] | None) -> str | None:
    if task is None:
        return None
    status = task.get("status")
    if status in {"RUNNING", "QA", "REVIEW"}:
        return {
            "RUNNING": "developer",
            "QA": "qa",
            "REVIEW": "reviewer",
        }.get(status)
    if invocation:
        role = invocation.get("role")
        if isinstance(role, str):
            return role
    return None


def derive_status(
    store: Any,
    *,
    root: Path | None = None,
    systemd_probe: Callable[[], dict[str, Any]] | None = None,
    run_lock_probe: Callable[[Path], tuple[bool, str | None]] | None = None,
) -> dict[str, Any]:
    root = Path(root) if root is not None else Path(store.root)
    snapshot = store.snapshot()
    tasks = snapshot.get("tasks", {})
    runs = snapshot.get("runs", [])
    gate = load_gate(root)
    stop_file = root / "STOP"
    events = _read_jsonl_tail(root / "events.jsonl")
    meaningful = [event for event in events if event.get("event") != "metrics"]
    last_event = meaningful[-1] if meaningful else None
    current_id = snapshot.get("current")
    current_task = tasks.get(current_id) if current_id else None
    invocation = _last_invocation(root, current_id)
    running, lock_reason = (run_lock_probe or _run_lock_live)(root)
    systemd = (systemd_probe or probe_systemd)()
    ready_tasks = [
        key
        for key, value in tasks.items()
        if isinstance(value, dict) and value.get("status") in {"READY", "RUNNING", "QA", "REVIEW"}
    ]
    blocked_tasks = [
        key
        for key, value in tasks.items()
        if isinstance(value, dict) and value.get("status") == "BLOCKED"
    ]

    if running:
        status = RUNNING
        reason = None
    elif stop_file.exists():
        status = STOPPED
        reason = "STOP file"
    elif gate is not None:
        status = MILESTONE_COMPLETED if gate.kind == KIND_MILESTONE else PAUSED_FOR_OWNER
        reason = gate.reason
    elif not ready_tasks and blocked_tasks:
        status = BLOCKED
        reason = "blocked tasks: " + ", ".join(blocked_tasks)
    elif last_event and last_event.get("event") in {"fatal_error", "error"}:
        status = STOPPED_ERROR
        reason = str(last_event.get("reason") or last_event.get("error") or "last run failed")
    elif systemd.get("available") and not str(
        systemd.get("timer", {}).get("active_state", "")
    ).startswith("active"):
        status = BLOCKED
        reason = "heartbeat timer is inactive"
    else:
        status = WAITING_FOR_NEXT_RUN
        reason = lock_reason

    last_event_time = _event_time(last_event) if last_event else None
    if last_event_time is None and (root / "state.json").exists():
        last_event_time = datetime.fromtimestamp(
            (root / "state.json").stat().st_mtime, UTC
        ).isoformat()
    last_run_at = None
    if runs:
        candidate = runs[-1]
        if isinstance(candidate, dict):
            last_run_at = candidate.get("finished_at") or candidate.get("started_at")
    queue = Counter(
        str(value.get("status", "UNKNOWN")) for value in tasks.values() if isinstance(value, dict)
    )
    result = dict(snapshot)
    result.update(
        {
            "status": status,
            "reason": reason,
            "gate": gate.to_dict() if gate is not None else None,
            "current_task": current_task,
            "task_stage": _task_stage(current_task, invocation),
            "agent": (invocation or {}).get("role"),
            "model": (invocation or {}).get("model") or (current_task or {}).get("model"),
            "last_run_at": last_run_at,
            "last_heartbeat": last_event_time,
            "last_result": last_event,
            "stop_reason": "STOP file" if stop_file.exists() else None,
            "systemd": systemd,
            "queue": dict(queue),
            "logs": {
                "events": str(root / "events.jsonl"),
                "invocations": str(root / "invocations.jsonl"),
                "state": str(root / "state.json"),
                "journal": f"journalctl --user -u {JOURNAL_UNIT}",
            },
        }
    )
    return result


def write_last_report(store: Any, report: dict[str, Any]) -> Path:
    """Persist a sanitized owner-readable last-run report (mode 0600)."""
    root = Path(store.root)
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    path = reports / "last_run_report.json"
    payload = render_report(report)
    fd, temp_name = tempfile.mkstemp(dir=reports, prefix=".report.", text=True)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        Path(temp_name).replace(path)
    finally:
        Path(temp_name).unlink(missing_ok=True)
    return path


def render_report(report: dict[str, Any]) -> str:
    """Render status/report JSON with token-shaped values redacted."""
    return sanitize_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
