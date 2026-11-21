"""Durable task queue and state for the autonomous BA loop.

State is a single JSON file protected by an advisory file lock and replaced
atomically. It is intentionally independent of Django/PostgreSQL so the
control plane can run while the project stack is down.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

READY = "READY"
RUNNING = "RUNNING"
QA = "QA"
REVIEW = "REVIEW"
COMPLETED = "COMPLETED"
BLOCKED = "BLOCKED"
FAILED = "FAILED"
STATUSES = {READY, RUNNING, QA, REVIEW, COMPLETED, BLOCKED, FAILED}
PRIORITY_RANK = {"Blocker": 0, "Critical": 1, "Major": 2, "Minor": 3, "Improvement": 4}


class StateError(RuntimeError):
    """Persisted queue is unreadable; never silently replace it with an empty one."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _fingerprint(title: str, acceptance: list[str]) -> str:
    raw = json.dumps([title, acceptance], ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()[:24]


@dataclass
class Task:
    id: str
    title: str
    priority: str
    acceptance: list[str]
    dependencies: list[str] = field(default_factory=list)
    status: str = READY
    attempts: int = 0
    max_attempts: int = 2
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    run_id: str | None = None
    session_id: str | None = None
    model: str | None = None
    worktree: str | None = None
    base_commit: str | None = None
    candidate_commit: str | None = None
    evidence: list[str] = field(default_factory=list)
    blocked_reason: str | None = None
    last_error: str | None = None
    fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.fingerprint:
            self.fingerprint = _fingerprint(self.title, self.acceptance)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Task:
        known = set(cls.__dataclass_fields__)
        return cls(**{key: value[key] for key in value if key in known})

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "priority": self.priority,
            "acceptance": self.acceptance,
            "dependencies": self.dependencies,
            "status": self.status,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "model": self.model,
            "worktree": self.worktree,
            "base_commit": self.base_commit,
            "candidate_commit": self.candidate_commit,
            "evidence": self.evidence,
            "blocked_reason": self.blocked_reason,
            "last_error": self.last_error,
            "fingerprint": self.fingerprint,
        }


class StateStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / "state.json"
        self.lock_path = root / "state.lock"
        root.mkdir(parents=True, exist_ok=True)

    def _default(self) -> dict[str, Any]:
        return {"version": 1, "current": None, "tasks": {}, "runs": []}

    @contextmanager
    def locked(self) -> Iterator[dict[str, Any]]:
        with self.lock_path.open("a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                state = self._read()
                yield state
                self._write(state)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._default()
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StateError(f"cannot read {self.path}: {exc}") from exc
        if not isinstance(value, dict) or not isinstance(value.get("tasks"), dict):
            raise StateError(f"invalid queue state shape in {self.path}")
        return value

    def _write(self, state: dict[str, Any]) -> None:
        payload = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        fd, temp_name = tempfile.mkstemp(dir=self.root, prefix=".state.", text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            Path(temp_name).replace(self.path)
        finally:
            Path(temp_name).unlink(missing_ok=True)

    def enqueue(self, tasks: list[Task]) -> list[Task]:
        added: list[Task] = []
        with self.locked() as state:
            existing_ids = set(state["tasks"])
            completed_fingerprints = {
                item.get("fingerprint")
                for item in state["tasks"].values()
                if item.get("status") == COMPLETED
            }
            for task in tasks:
                if task.id in existing_ids or task.fingerprint in completed_fingerprints:
                    continue
                state["tasks"][task.id] = task.to_dict()
                existing_ids.add(task.id)
                added.append(task)
        return added

    def get(self, task_id: str) -> Task | None:
        with self.locked() as state:
            value = state["tasks"].get(task_id)
            return Task.from_dict(value) if value else None

    def list_tasks(self, status: str | None = None) -> list[Task]:
        with self.locked() as state:
            tasks = [Task.from_dict(value) for value in state["tasks"].values()]
        return [task for task in tasks if status is None or task.status == status]

    def claim_next(self) -> Task | None:
        with self.locked() as state:
            completed = {
                task_id
                for task_id, value in state["tasks"].items()
                if value.get("status") == COMPLETED
            }
            ready = []
            for value in state["tasks"].values():
                if value.get("status") != READY:
                    continue
                if any(dep not in completed for dep in value.get("dependencies", [])):
                    continue
                ready.append(Task.from_dict(value))
            if not ready:
                return None
            ready.sort(
                key=lambda task: (PRIORITY_RANK.get(task.priority, 99), task.created_at, task.id)
            )
            task = ready[0]
            task.status = RUNNING
            task.attempts += 1
            task.run_id = str(uuid.uuid4())
            task.updated_at = _now()
            state["tasks"][task.id] = task.to_dict()
            state["current"] = task.id
            state["runs"].append(
                {
                    "run_id": task.run_id,
                    "task_id": task.id,
                    "started_at": _now(),
                    "status": "started",
                }
            )
            return task

    def transition(
        self,
        task_id: str,
        status: str,
        *,
        session_id: str | None = None,
        model: str | None = None,
        evidence: str | None = None,
        error: str | None = None,
        blocked_reason: str | None = None,
    ) -> Task | None:
        if status not in STATUSES:
            raise ValueError(f"unknown status: {status}")
        with self.locked() as state:
            value = state["tasks"].get(task_id)
            if value is None:
                return None
            task = Task.from_dict(value)
            task.status = status
            task.updated_at = _now()
            if session_id:
                task.session_id = session_id
            if model:
                task.model = model
            if evidence:
                task.evidence.append(evidence)
            if error:
                task.last_error = error
            if blocked_reason:
                task.blocked_reason = blocked_reason
            state["tasks"][task_id] = task.to_dict()
            if status in {COMPLETED, BLOCKED, FAILED}:
                state["current"] = None
            for run in reversed(state["runs"]):
                if run.get("task_id") == task_id and run.get("run_id") == task.run_id:
                    run["status"] = status.lower()
                    run["finished_at"] = _now()
                    break
            return task

    def set_worktree(
        self, task_id: str, worktree: str | None, base_commit: str | None
    ) -> Task | None:
        with self.locked() as state:
            value = state["tasks"].get(task_id)
            if value is None:
                return None
            task = Task.from_dict(value)
            task.worktree = worktree
            task.base_commit = base_commit
            task.candidate_commit = None
            task.updated_at = _now()
            state["tasks"][task_id] = task.to_dict()
            return task

    def set_candidate(self, task_id: str, candidate_commit: str | None) -> Task | None:
        with self.locked() as state:
            value = state["tasks"].get(task_id)
            if value is None:
                return None
            task = Task.from_dict(value)
            task.candidate_commit = candidate_commit
            task.updated_at = _now()
            state["tasks"][task_id] = task.to_dict()
            return task

    def retry(self, task_id: str, reason: str) -> Task | None:
        with self.locked() as state:
            value = state["tasks"].get(task_id)
            if value is None:
                return None
            task = Task.from_dict(value)
            task.last_error = reason
            task.updated_at = _now()
            if task.attempts >= task.max_attempts:
                task.status = BLOCKED
                task.blocked_reason = "RETRY_LIMIT"
            else:
                task.status = READY
            state["current"] = None
            state["tasks"][task_id] = task.to_dict()
            return task

    def recover_running(self) -> list[Task]:
        """Recover any phase that can be left behind by a killed orchestrator."""
        recovered: list[Task] = []
        in_progress = {RUNNING, QA, REVIEW}
        with self.locked() as state:
            for task_id, value in state["tasks"].items():
                if value.get("status") not in in_progress:
                    continue
                task = Task.from_dict(value)
                if task.attempts >= task.max_attempts:
                    task.status = BLOCKED
                    task.blocked_reason = "RECOVERED_AFTER_STOP"
                else:
                    task.status = READY
                    task.last_error = "recovered after interrupted run"
                task.updated_at = _now()
                state["tasks"][task_id] = task.to_dict()
                recovered.append(task)
            state["current"] = None
            return recovered

    def snapshot(self) -> dict[str, Any]:
        with self.locked() as state:
            return state
