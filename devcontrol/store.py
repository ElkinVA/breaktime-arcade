"""Durable local state, events and inbox for BA Dev Control.

All writes are atomic and 0600; the runtime directory is 0700. A file lock
serialises the bot process and ``status_cli.py`` (the agent-side emitter), so
no event or inbox message is lost when both run concurrently.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import threading
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROCESSED_LIMIT = 200


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def atomic_write_json(path: Path, payload: dict[str, Any], *, mode: int = 0o600) -> None:
    _ensure_dir(path.parent)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(temp, flags, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(path)
        path.chmod(mode)
    finally:
        with contextlib.suppress(OSError):
            temp.unlink(missing_ok=True)


def append_jsonl(path: Path, payload: dict[str, Any], *, mode: int = 0o600) -> None:
    _ensure_dir(path.parent)
    line = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, mode)
    try:
        _write_all(fd, line)
    finally:
        os.close(fd)


def read_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except OSError, ValueError:
        return dict(default or {})
    return value if isinstance(value, dict) else dict(default or {})


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    messages: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            messages.append(value)
    return messages


@contextlib.contextmanager
def file_lock(path: Path) -> Iterator[None]:
    _ensure_dir(path.parent)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


@dataclass(frozen=True)
class RuntimePaths:
    root: Path

    @property
    def state(self) -> Path:
        return self.root / "state.json"

    @property
    def events(self) -> Path:
        return self.root / "events.jsonl"

    @property
    def inbox(self) -> Path:
        return self.root / "inbox.jsonl"

    @property
    def inbox_delivered(self) -> Path:
        return self.root / "inbox.delivered.jsonl"

    @property
    def pause(self) -> Path:
        return self.root / "PAUSE"

    @property
    def pending_owner(self) -> Path:
        return self.root / "pending_owner.json"

    @property
    def lock(self) -> Path:
        return self.root / "state.lock"

    @property
    def controller_lock(self) -> Path:
        return self.root / "controller.lock"

    def ensure(self) -> None:
        _ensure_dir(self.root)


def default_state() -> dict[str, Any]:
    return {
        "version": 1,
        "status": "IDLE",
        "current_task": None,
        "current_title": None,
        "session_id": None,
        "session_name": None,
        "session_active": False,
        "started_at": None,
        "last_event": None,
        "last_event_at": None,
        "heartbeat_at": None,
        "pause_requested": False,
        "pending_owner": None,
        "events_offset": 0,
        "last_update_id": 0,
        "processed_updates": [],
        "processed_callbacks": [],
        "last_notified_event": None,
        "consecutive_errors": 0,
        "last_error": None,
    }


class StateStore:
    """Thread- and process-safe runtime store."""

    def __init__(self, paths: RuntimePaths) -> None:
        self.paths = paths
        self._thread_lock = threading.RLock()
        paths.ensure()

    def load_state(self) -> dict[str, Any]:
        state = default_state()
        state.update(read_json(self.paths.state))
        return state

    def save_state(self, state: dict[str, Any]) -> None:
        with self._thread_lock, file_lock(self.paths.lock):
            atomic_write_json(self.paths.state, state)

    def update_state(self, **fields: Any) -> dict[str, Any]:
        with self._thread_lock:
            state = self.load_state()
            state.update(fields)
            self.save_state(state)
            return state

    def append_event(self, event: str, **fields: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": uuid.uuid4().hex,
            "ts": utc_now(),
            "event": event,
            **fields,
        }
        with self._thread_lock, file_lock(self.paths.lock):
            append_jsonl(self.paths.events, payload)
        return payload

    def events_since(self, offset: int) -> tuple[list[dict[str, Any]], int]:
        with self._thread_lock:
            events = read_jsonl(self.paths.events)
        start = offset if 0 <= offset <= len(events) else 0
        return events[start:], len(events)

    def enqueue_inbox(self, text: str, *, source: str = "owner") -> dict[str, Any]:
        payload = {
            "id": uuid.uuid4().hex,
            "ts": utc_now(),
            "source": source,
            "text": text,
        }
        with self._thread_lock, file_lock(self.paths.lock):
            append_jsonl(self.paths.inbox, payload)
        return payload

    def consume_inbox(self, ids: set[str] | None = None) -> list[dict[str, Any]]:
        """Archive messages once; partial ids leave newer messages in place."""
        with self._thread_lock, file_lock(self.paths.lock):
            messages = read_jsonl(self.paths.inbox)
            if not messages:
                return []
            delivered_ids = {
                str(message.get("id"))
                for message in read_jsonl(self.paths.inbox_delivered)
                if message.get("id")
            }
            if ids is None:
                selected = [
                    message for message in messages if str(message.get("id")) not in delivered_ids
                ]
                remove = {str(message.get("id")) for message in messages if message.get("id")}
            else:
                selected = [
                    message
                    for message in messages
                    if str(message.get("id")) in ids and str(message.get("id")) not in delivered_ids
                ]
                remove = set(ids)
            for message in selected:
                append_jsonl(self.paths.inbox_delivered, message)
            remaining = [message for message in messages if str(message.get("id")) not in remove]
            temp = self.paths.inbox.with_name(f".{self.paths.inbox.name}.{uuid.uuid4().hex}.tmp")
            temp.write_text(
                "".join(
                    json.dumps(message, ensure_ascii=False, sort_keys=True) + "\n"
                    for message in remaining
                ),
                encoding="utf-8",
            )
            temp.chmod(0o600)
            temp.replace(self.paths.inbox)
        return selected

    def paused(self) -> bool:
        return self.paths.pause.exists()

    def set_pause(self, paused: bool) -> dict[str, Any]:
        if paused:
            self.paths.pause.write_text(utc_now() + "\n", encoding="utf-8")
            self.paths.pause.chmod(0o600)
        else:
            with contextlib.suppress(FileNotFoundError):
                self.paths.pause.unlink()
        return self.update_state(pause_requested=paused)

    def write_pending_owner(self, payload: dict[str, Any]) -> dict[str, Any]:
        record = {"id": uuid.uuid4().hex, "ts": utc_now(), **payload}
        with self._thread_lock, file_lock(self.paths.lock):
            atomic_write_json(self.paths.pending_owner, record)
        self.update_state(pending_owner=record)
        return record

    def read_pending_owner(self) -> dict[str, Any]:
        return read_json(self.paths.pending_owner)

    def clear_pending_owner(self) -> None:
        with contextlib.suppress(FileNotFoundError):
            self.paths.pending_owner.unlink()
        self.update_state(pending_owner=None)

    def mark_update(self, update_id: int) -> bool:
        with self._thread_lock, file_lock(self.paths.lock):
            state = self.load_state()
            if update_id and update_id <= int(state.get("last_update_id") or 0):
                return False
            processed = list(state.get("processed_updates") or [])
            processed.append(update_id)
            state["processed_updates"] = processed[-PROCESSED_LIMIT:]
            state["last_update_id"] = max(update_id, int(state.get("last_update_id") or 0))
            atomic_write_json(self.paths.state, state)
            return True

    def mark_callback(self, key: str) -> bool:
        with self._thread_lock, file_lock(self.paths.lock):
            state = self.load_state()
            processed = list(state.get("processed_callbacks") or [])
            if key in processed:
                return False
            processed.append(key)
            state["processed_callbacks"] = processed[-PROCESSED_LIMIT:]
            atomic_write_json(self.paths.state, state)
            return True
