"""Owner-action gate: a durable pause that is separate from the emergency STOP.

The gate is a JSON file under ``.autonomy``.  It is checked before any task is
claimed or any model is invoked.  A malformed gate is treated as active
(fail-closed): the orchestrator must never run models on an unreadable gate.
"""

from __future__ import annotations

import fcntl
import json
import os
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GATE_FILE_NAME = "OWNER_ACTION_REQUIRED"
GATE_LOCK_NAME = "OWNER_ACTION_REQUIRED.lock"
KIND_OWNER_ACTION = "owner_action"
KIND_MILESTONE = "milestone"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def gate_path(root: Path) -> Path:
    return Path(root) / GATE_FILE_NAME


def _lock_path(root: Path) -> Path:
    return Path(root) / GATE_LOCK_NAME


@contextmanager
def _gate_lock(root: Path) -> Iterator[None]:
    lock_path = _lock_path(root)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


@dataclass(frozen=True)
class OwnerGate:
    reason: str
    kind: str = KIND_OWNER_ACTION
    milestone: str | None = None
    created_at: str = ""
    requested_action: str | None = None
    recommendation: str | None = None
    notified_at: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> OwnerGate:
        kind = str(value.get("kind") or KIND_OWNER_ACTION)
        if kind not in {KIND_OWNER_ACTION, KIND_MILESTONE}:
            kind = KIND_OWNER_ACTION
        return cls(
            reason=str(value.get("reason") or "owner action required"),
            kind=kind,
            milestone=str(value["milestone"]) if value.get("milestone") else None,
            created_at=str(value.get("created_at") or _now()),
            requested_action=(
                str(value["requested_action"]) if value.get("requested_action") else None
            ),
            recommendation=(str(value["recommendation"]) if value.get("recommendation") else None),
            notified_at=str(value["notified_at"]) if value.get("notified_at") else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "kind": self.kind,
            "milestone": self.milestone,
            "created_at": self.created_at,
            "requested_action": self.requested_action,
            "recommendation": self.recommendation,
            "notified_at": self.notified_at,
        }


class OwnerActionRequired(RuntimeError):
    """Raised when a model-triggering operation is attempted under a gate."""

    def __init__(self, report: dict[str, Any]) -> None:
        super().__init__(str(report.get("reason", "OWNER_ACTION_REQUIRED")))
        self.report = report


def load_gate(root: Path) -> OwnerGate | None:
    path = gate_path(root)
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return None
    except OSError as exc:
        return OwnerGate(
            reason=f"gate path is unreadable: {type(exc).__name__}",
            kind=KIND_OWNER_ACTION,
            created_at=_now(),
            requested_action="inspect .autonomy/OWNER_ACTION_REQUIRED",
        )
    if not stat.S_ISREG(mode):
        return OwnerGate(
            reason="gate path is not a regular file",
            kind=KIND_OWNER_ACTION,
            created_at=_now(),
            requested_action="inspect .autonomy/OWNER_ACTION_REQUIRED",
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("gate is not a JSON object")
        return OwnerGate.from_dict(value)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return OwnerGate(
            reason=f"gate file unreadable: {type(exc).__name__}",
            kind=KIND_OWNER_ACTION,
            created_at=_now(),
            requested_action="inspect or remove .autonomy/OWNER_ACTION_REQUIRED",
        )


def _write_gate(root: Path, gate: OwnerGate) -> None:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(gate.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd, temp_name = tempfile.mkstemp(dir=root, prefix=".owner-gate.", text=True)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        Path(temp_name).replace(gate_path(root))
    finally:
        Path(temp_name).unlink(missing_ok=True)


def set_gate(
    root: Path,
    *,
    reason: str,
    kind: str = KIND_OWNER_ACTION,
    milestone: str | None = None,
    requested_action: str | None = None,
    recommendation: str | None = None,
) -> OwnerGate:
    gate = OwnerGate(
        reason=reason or "owner action required",
        kind=kind if kind in {KIND_OWNER_ACTION, KIND_MILESTONE} else KIND_OWNER_ACTION,
        milestone=milestone,
        created_at=_now(),
        requested_action=requested_action,
        recommendation=recommendation,
    )
    with _gate_lock(Path(root)):
        _write_gate(Path(root), gate)
    return gate


def clear_gate(root: Path) -> bool:
    path = gate_path(root)
    with _gate_lock(Path(root)):
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False
        except OSError:
            return False


def mark_notified(root: Path) -> bool:
    """Atomically flip notified_at once; returns True only for the first caller."""
    path = gate_path(root)
    with _gate_lock(Path(root)):
        gate = load_gate(root)
        if gate is None or gate.notified_at is not None:
            return False
        updated = OwnerGate(
            reason=gate.reason,
            kind=gate.kind,
            milestone=gate.milestone,
            created_at=gate.created_at,
            requested_action=gate.requested_action,
            recommendation=gate.recommendation,
            notified_at=_now(),
        )
        _write_gate(Path(root), updated)
        return path.exists()


def paused_report(gate: OwnerGate) -> dict[str, Any]:
    status = "paused"
    reason = "OWNER_ACTION_REQUIRED"
    if gate.kind == KIND_MILESTONE:
        reason = "MILESTONE_COMPLETED"
    return {
        "status": status,
        "reason": reason,
        "gate": gate.to_dict(),
        "completed": [],
    }
