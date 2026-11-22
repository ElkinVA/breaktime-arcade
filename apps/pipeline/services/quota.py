"""System-wide ZIP storage quota (R-033/R-043, ARCADE-P4-STORAGE-001).

The per-archive limits in :mod:`apps.pipeline.validation.codes` cap one ZIP.
This module caps the *combined* size of the shared ZIP roots (transient
uploads, worker artifacts and the private original-package store) so that
concurrent uploads/imports cannot exhaust the volume.

Admission is serialized through an ``fcntl`` lock in a small shared state
directory (mounted read-write in both ``web`` and ``zip-worker``) and is
recorded as a short-lived reservation.  Reservations expire after
``ZIP_QUOTA_RESERVATION_TTL_SECONDS`` so a crashed web process cannot pin
quota forever (cleanup rerun/restart is idempotent).

The module never deletes anything: quota rejection is non-destructive and is
reported with a stable ``X_STORAGE_*`` code.  Published runtimes are not part
of the quota roots and are never touched here.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import stat
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings

from apps.pipeline.validation.codes import (
    X_STORAGE_FREE_SPACE,
    X_STORAGE_QUOTA,
    X_STORAGE_QUOTA_STATE,
)

LOCK_FILE = "quota.lock"
RESERVATIONS_FILE = "reservations.json"


class StorageQuotaError(Exception):
    """Stable, non-destructive quota rejection."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        usage: int = 0,
        requested: int = 0,
        limit: int = 0,
        free: int = 0,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.usage = usage
        self.requested = requested
        self.limit = limit
        self.free = free

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "usage_bytes": self.usage,
            "requested_bytes": self.requested,
            "limit_bytes": self.limit,
            "free_bytes": self.free,
        }


@dataclass(frozen=True, slots=True)
class Reservation:
    """A byte reservation that must be released after the write."""

    token: str
    bytes: int
    state_root: Path


def quota_state_root() -> Path:
    """Return the shared quota state directory.

    Compose sets ``ZIP_QUOTA_STATE_ROOT`` to a dedicated volume mounted in both
    web and zip-worker.  Tests/dev fall back to a private directory inside the
    uploads root (never treated as a job directory by cleanup).
    """
    configured = getattr(settings, "ZIP_QUOTA_STATE_ROOT", None)
    if configured:
        return Path(configured)
    return Path(settings.ZIP_UPLOADS_ROOT) / ".quota"


def storage_usage(roots: tuple[Path, ...] | list[Path]) -> int:
    """Sum regular-file bytes under ``roots`` without following symlinks."""
    total = 0
    for root in roots:
        base = Path(root)
        if base.is_symlink() or not base.is_dir():
            continue
        for current, _dirs, files in os.walk(base, followlinks=False):
            for name in files:
                path = Path(current) / name
                if path.is_symlink():
                    continue
                try:
                    info = path.stat()
                except OSError:
                    continue
                if not stat.S_ISREG(info.st_mode):
                    continue
                total += info.st_size
    return total


def _free_bytes(root: Path) -> int | None:
    """Free bytes on the filesystem that holds ``root`` (or its ancestor)."""
    path = Path(root)
    while not path.exists() and path != path.parent:
        path = path.parent
    try:
        info = os.statvfs(path)
    except OSError:
        return None
    return int(info.f_bavail) * int(info.f_frsize)


def _dedupe_roots(roots: tuple[Path, ...] | list[Path]) -> tuple[Path, ...]:
    seen: set[str] = set()
    result: list[Path] = []
    for root in roots:
        key = str(Path(root).resolve())
        if key in seen:
            continue
        seen.add(key)
        result.append(Path(root))
    return tuple(result)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(temp, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(path)
    finally:
        with contextlib.suppress(OSError):
            temp.unlink(missing_ok=True)


class StorageQuota:
    """Byte reservation over the shared ZIP roots."""

    def __init__(
        self,
        roots: tuple[Path, ...] | list[Path],
        *,
        state_root: Path,
        max_bytes: int,
        min_free_bytes: int,
        reservation_ttl_seconds: int = 60 * 60,
    ) -> None:
        self.roots = _dedupe_roots(roots)
        self.state_root = Path(state_root)
        self.max_bytes = int(max_bytes)
        self.min_free_bytes = int(min_free_bytes)
        self.reservation_ttl_seconds = max(1, int(reservation_ttl_seconds))

    @classmethod
    def from_settings(
        cls,
        *,
        storage_root: Path | None = None,
        uploads_root: Path | None = None,
        artifacts_root: Path | None = None,
        state_root: Path | None = None,
    ) -> StorageQuota:
        uploads = Path(uploads_root or settings.ZIP_UPLOADS_ROOT)
        roots = [
            Path(storage_root or settings.ZIP_PIPELINE_STORAGE_ROOT),
            uploads,
            Path(artifacts_root or settings.ZIP_ARTIFACTS_ROOT),
        ]
        if state_root is not None:
            resolved_state = Path(state_root)
        elif settings.ZIP_QUOTA_STATE_ROOT:
            resolved_state = Path(settings.ZIP_QUOTA_STATE_ROOT)
        else:
            # Single-container/dev fallback follows the explicit uploads root.
            resolved_state = uploads / ".quota"
        return cls(
            roots,
            state_root=resolved_state,
            max_bytes=int(settings.ZIP_STORAGE_QUOTA_BYTES),
            min_free_bytes=int(settings.ZIP_STORAGE_MIN_FREE_BYTES),
            reservation_ttl_seconds=int(settings.ZIP_QUOTA_RESERVATION_TTL_SECONDS),
        )

    # --- filesystem state -------------------------------------------------
    def usage_bytes(self) -> int:
        return storage_usage(self.roots)

    def _ensure_state_root(self) -> None:
        try:
            self.state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        except OSError:
            raise StorageQuotaError(
                X_STORAGE_QUOTA_STATE,
                "Каталог состояния квоты ZIP недоступен",
            ) from None
        if self.state_root.is_symlink() or not self.state_root.is_dir():
            raise StorageQuotaError(
                X_STORAGE_QUOTA_STATE,
                "Каталог состояния квоты ZIP небезопасен",
            )

    @contextlib.contextmanager
    def _locked(self) -> Iterator[None]:
        self._ensure_state_root()
        lock_path = self.state_root / LOCK_FILE
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(lock_path, flags, 0o600)
        except OSError:
            raise StorageQuotaError(
                X_STORAGE_QUOTA_STATE,
                "Не удалось открыть lock квоты ZIP",
            ) from None
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            with contextlib.suppress(OSError):
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _reservations_path(self) -> Path:
        return self.state_root / RESERVATIONS_FILE

    def _load_reservations(self, now: float) -> dict[str, dict[str, Any]]:
        path = self._reservations_path()
        if path.is_symlink() or not path.is_file():
            return {}
        try:
            with path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except OSError, ValueError:
            return {}
        if not isinstance(raw, dict):
            return {}
        current: dict[str, dict[str, Any]] = {}
        for token, entry in raw.items():
            if not isinstance(token, str) or not isinstance(entry, dict):
                continue
            try:
                amount = int(entry.get("bytes", 0))
                created = float(entry.get("created_at", 0))
            except TypeError, ValueError:
                continue
            if amount <= 0 or now - created >= self.reservation_ttl_seconds:
                continue
            current[token] = {"bytes": amount, "created_at": created}
        return current

    # --- admission --------------------------------------------------------
    def reserve(self, amount: int, *, reason: str = "") -> Reservation:
        """Reserve ``amount`` bytes or raise :class:`StorageQuotaError`."""
        requested = max(0, int(amount))
        with self._locked():
            now = time.time()
            reservations = self._load_reservations(now)
            reserved = sum(int(item["bytes"]) for item in reservations.values())
            usage = self.usage_bytes()
            if usage + reserved + requested > self.max_bytes:
                raise StorageQuotaError(
                    X_STORAGE_QUOTA,
                    "Системная квота ZIP-хранилища исчерпана",
                    usage=usage + reserved,
                    requested=requested,
                    limit=self.max_bytes,
                )
            free_values = [
                value for value in (_free_bytes(root) for root in self.roots) if value is not None
            ]
            free = min(free_values) if free_values else 0
            if free_values and free - requested < self.min_free_bytes:
                raise StorageQuotaError(
                    X_STORAGE_FREE_SPACE,
                    "Недостаточно свободного места для ZIP-хранилища",
                    usage=usage + reserved,
                    requested=requested,
                    limit=self.max_bytes,
                    free=free,
                )
            token = uuid.uuid4().hex
            reservations[token] = {"bytes": requested, "created_at": now}
            try:
                _write_json_atomic(self._reservations_path(), reservations)
            except OSError:
                raise StorageQuotaError(
                    X_STORAGE_QUOTA_STATE,
                    "Не удалось сохранить резерв квоты ZIP",
                ) from None
            return Reservation(token=token, bytes=requested, state_root=self.state_root)

    def release(self, reservation: Reservation) -> None:
        """Drop a reservation; safe to call twice and after a restart."""
        if reservation.state_root != self.state_root:
            return
        try:
            with self._locked():
                now = time.time()
                reservations = self._load_reservations(now)
                if reservations.pop(reservation.token, None) is None:
                    return
                try:
                    _write_json_atomic(self._reservations_path(), reservations)
                except OSError:
                    # The reservation will expire at TTL; never fail the import
                    # because bookkeeping could not be rewritten.
                    return
        except StorageQuotaError:
            # State directory vanished/read-only after the write; TTL cleanup
            # in the next reservation handles the stale entry.
            return

    @contextlib.contextmanager
    def reservation(self, amount: int, *, reason: str = "") -> Iterator[Reservation]:
        reservation = self.reserve(amount, reason=reason)
        try:
            yield reservation
        finally:
            self.release(reservation)

    def assert_within_limit(self) -> None:
        """Post-write guard: actual usage must stay within the quota."""
        usage = self.usage_bytes()
        if usage > self.max_bytes:
            raise StorageQuotaError(
                X_STORAGE_QUOTA,
                "Системная квота ZIP-хранилища превышена",
                usage=usage,
                limit=self.max_bytes,
            )


__all__ = [
    "LOCK_FILE",
    "RESERVATIONS_FILE",
    "Reservation",
    "StorageQuota",
    "StorageQuotaError",
    "quota_state_root",
    "storage_usage",
]
