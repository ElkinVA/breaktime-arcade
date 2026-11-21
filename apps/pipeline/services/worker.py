"""Isolated ZIP extraction job lifecycle (BA-ZIP-WORKER-001).

The worker is deliberately DB-free: it reads a source ZIP from the read-only
``zip_uploads`` volume, writes results to ``zip_artifacts`` and emits structured
audit records. All path handling is confined to UUID job directories; the
source file is opened with ``O_NOFOLLOW`` and re-checked through ``/proc``.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import logging
import os
import re
import shutil
import stat
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings

from apps.pipeline.services.unpack import X_CANCELLED, X_TIMEOUT, ExtractionError, extract_zip
from apps.pipeline.validation.codes import MAX_ZIP_BYTES

logger = logging.getLogger("apps.pipeline.worker")

X_JOB_ID = "X_JOB_ID"
X_JOB_BUSY = "X_JOB_BUSY"
X_SOURCE_UNSAFE = "X_SOURCE_UNSAFE"
X_SOURCE_TOO_LARGE = "X_SOURCE_TOO_LARGE"
X_DISK_RESERVE = "X_DISK_RESERVE"
X_JOB_CONFLICT = "X_JOB_CONFLICT"
X_JOB_TOO_LARGE = "X_JOB_TOO_LARGE"
X_QUARANTINED = "X_QUARANTINED"
X_INTERNAL = "X_INTERNAL"

MAX_ATTEMPTS = 2
AUDIT_FILE = "audit.jsonl"
COMPLETED_FILE = "COMPLETED.json"
ATTEMPTS_FILE = "ATTEMPTS"
LOCK_FILE = ".lock"
RESULT_DIR = "result"
_CANCEL_FILE = "CANCEL"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class WorkerError(Exception):
    """Stable worker failure with a machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class JobPaths:
    uploads_root: Path
    artifacts_root: Path
    job_id: str

    @property
    def source(self) -> Path:
        return self.uploads_root / self.job_id / "source.zip"

    @property
    def cancel(self) -> Path:
        return self.uploads_root / self.job_id / _CANCEL_FILE

    @property
    def job_dir(self) -> Path:
        return self.artifacts_root / self.job_id

    @property
    def result(self) -> Path:
        return self.job_dir / RESULT_DIR

    @property
    def completed(self) -> Path:
        return self.job_dir / COMPLETED_FILE

    @property
    def attempts(self) -> Path:
        return self.job_dir / ATTEMPTS_FILE

    @property
    def lock(self) -> Path:
        return self.job_dir / LOCK_FILE

    @property
    def audit(self) -> Path:
        return self.job_dir / AUDIT_FILE


@dataclass(frozen=True, slots=True)
class JobOutcome:
    job_id: str
    status: str
    package_hash: str | None = None
    total_bytes: int = 0
    file_count: int = 0
    error_code: str | None = None
    attempts: int = 0


def _roots(uploads_root: Path | None, artifacts_root: Path | None) -> tuple[Path, Path]:
    uploads = Path(uploads_root or settings.ZIP_UPLOADS_ROOT)
    artifacts = Path(artifacts_root or settings.ZIP_ARTIFACTS_ROOT)
    return uploads, artifacts


def normalize_job_id(job_id: str) -> str:
    if not isinstance(job_id, str):
        raise WorkerError(X_JOB_ID, "Некорректный job_id")
    try:
        parsed = uuid.UUID(job_id)
    except AttributeError, TypeError, ValueError:
        raise WorkerError(X_JOB_ID, "Некорректный job_id") from None
    canonical = str(parsed)
    if job_id.lower() != canonical:
        raise WorkerError(X_JOB_ID, "Некорректный job_id")
    return canonical


def job_paths(
    job_id: str,
    *,
    uploads_root: Path | None = None,
    artifacts_root: Path | None = None,
) -> JobPaths:
    uploads, artifacts = _roots(uploads_root, artifacts_root)
    return JobPaths(uploads_root=uploads, artifacts_root=artifacts, job_id=normalize_job_id(job_id))


def _ensure_dir(path: Path, mode: int = 0o700) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True, mode=mode)
    except OSError:
        raise WorkerError(X_SOURCE_UNSAFE, "Не удалось подготовить каталог") from None
    if path.is_symlink() or not path.is_dir():
        raise WorkerError(X_SOURCE_UNSAFE, "Каталог небезопасен")
    try:
        path.chmod(mode)
    except OSError:
        raise WorkerError(X_SOURCE_UNSAFE, "Не удалось выставить права") from None


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except OSError, ValueError:
        return False
    return True


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _read_source(paths: JobPaths, max_zip_bytes: int) -> tuple[bytes, str]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    # O_NONBLOCK prevents a FIFO planted by web from blocking the worker.
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        fd = os.open(paths.source, flags)
    except OSError:
        raise WorkerError(X_SOURCE_UNSAFE, "Источник недоступен или является symlink") from None
    data = b""
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise WorkerError(X_SOURCE_UNSAFE, "Источник не является обычным файлом")
        if info.st_size > max_zip_bytes:
            raise WorkerError(X_SOURCE_TOO_LARGE, "Входной ZIP превышает лимит")
        try:
            real = Path(f"/proc/self/fd/{fd}").readlink()
        except OSError:
            raise WorkerError(X_SOURCE_UNSAFE, "Не удалось проверить путь источника") from None
        if str(real).endswith(" (deleted)"):
            raise WorkerError(X_SOURCE_UNSAFE, "Источник удалён во время проверки")
        if not _is_within(real, paths.uploads_root):
            raise WorkerError(X_SOURCE_UNSAFE, "Источник вне каталога загрузок")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            data = handle.read(max_zip_bytes + 1)
    finally:
        os.close(fd)
    if len(data) > max_zip_bytes:
        raise WorkerError(X_SOURCE_TOO_LARGE, "Входной ZIP превышает лимит")
    return data, hashlib.sha256(data).hexdigest()


def _fsync_dir(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        fd = os.open(path, flags)
    except OSError:
        return
    try:
        with contextlib.suppress(OSError):
            os.fsync(fd)
    finally:
        os.close(fd)


def _write_text_atomic(path: Path, text: str, mode: int = 0o600) -> None:
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(temp, flags, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(path)
        _fsync_dir(path.parent)
    finally:
        with contextlib.suppress(OSError):
            temp.unlink(missing_ok=True)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    _write_text_atomic(path, json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except OSError, ValueError:
        return None
    return value if isinstance(value, dict) else None


def _read_attempts(paths: JobPaths) -> int:
    try:
        return max(0, int(paths.attempts.read_text(encoding="utf-8").strip()))
    except OSError, ValueError:
        return 0


def _write_attempts(paths: JobPaths, value: int) -> int:
    _write_text_atomic(paths.attempts, f"{value}\n")
    return value


def _increment_attempts(paths: JobPaths) -> int:
    return _write_attempts(paths, _read_attempts(paths) + 1)


def _audit(paths: JobPaths, event: str, **fields: Any) -> None:
    payload: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat(),
        "event": event,
        "job_id": paths.job_id,
        **fields,
    }
    logger.info(
        "zip.%s",
        event,
        extra={"event": f"zip.{event}", "job_id": paths.job_id, **fields},
    )
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(paths.audit, flags, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_dir(paths.job_dir)
    except OSError:
        logger.warning(
            "zip.audit_write_failed",
            extra={"event": "zip.audit_write_failed", "job_id": paths.job_id},
        )


class _JobLock:
    def __init__(self, paths: JobPaths) -> None:
        self._paths = paths
        self._fd: int | None = None

    def acquire(self) -> bool:
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            self._fd = os.open(self._paths.lock, flags, 0o600)
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.release()
            return False
        except OSError:
            self.release()
            raise WorkerError(X_SOURCE_UNSAFE, "Не удалось захватить job-lock") from None
        return True

    def release(self) -> None:
        if self._fd is None:
            return
        with contextlib.suppress(OSError):
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        os.close(self._fd)
        self._fd = None


def _remove_tree(path: Path) -> None:
    if path.is_symlink():
        path.unlink(missing_ok=True)
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)


def _remove_partial(paths: JobPaths) -> None:
    _remove_tree(paths.result)
    try:
        entries = list(os.scandir(paths.job_dir))
    except OSError:
        return
    for entry in entries:
        if entry.name.startswith(".ba-extract-") and entry.is_dir(follow_symlinks=False):
            _remove_tree(Path(entry.path))


def _disk_reserve_ok(artifacts_root: Path, reserve_bytes: int) -> bool:
    try:
        info = os.statvfs(artifacts_root)
    except OSError:
        return False
    return info.f_bavail * info.f_frsize >= reserve_bytes


def _tree_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path, followlinks=False):
        for name in files:
            item = Path(root) / name
            if item.is_symlink():
                continue
            try:
                total += item.stat().st_size
            except OSError:
                continue
    return total


def run_extraction(
    job_id: str,
    *,
    uploads_root: Path | None = None,
    artifacts_root: Path | None = None,
    deadline_seconds: int | None = None,
    max_zip_bytes: int = MAX_ZIP_BYTES,
    reserve_bytes: int | None = None,
    job_max_bytes: int | None = None,
) -> JobOutcome:
    """Run one extraction job in the isolated worker."""
    paths = job_paths(
        job_id,
        uploads_root=uploads_root,
        artifacts_root=artifacts_root,
    )
    artifacts = paths.artifacts_root
    _ensure_dir(artifacts)
    _ensure_dir(paths.job_dir)

    lock = _JobLock(paths)
    if not lock.acquire():
        _audit(paths, "busy")
        return JobOutcome(job_id=paths.job_id, status="busy", error_code=X_JOB_BUSY)

    try:
        attempts = _read_attempts(paths)
        if attempts >= MAX_ATTEMPTS:
            _audit(paths, "quarantine", attempts=attempts, error_code=X_QUARANTINED)
            return JobOutcome(
                job_id=paths.job_id,
                status="quarantined",
                error_code=X_QUARANTINED,
                attempts=attempts,
            )

        _audit(paths, "received", attempts=attempts)
        try:
            data, package_hash = _read_source(paths, max_zip_bytes)
        except WorkerError as exc:
            attempts = _increment_attempts(paths)
            _audit(paths, "rejected", error_code=exc.code, attempts=attempts)
            return JobOutcome(
                job_id=paths.job_id,
                status="rejected",
                error_code=exc.code,
                attempts=attempts,
            )

        completed = _read_json(paths.completed)
        recorded_hash = completed.get("package_hash") if completed is not None else None
        if completed is not None and not _is_sha256(recorded_hash):
            # Partial/corrupt marker: redo instead of trusting it.
            with contextlib.suppress(OSError):
                paths.completed.unlink()
            completed = None
        if completed is not None:
            files = completed.get("files")
            file_count = len(files) if isinstance(files, list) else 0
            total_bytes = completed.get("total_bytes")
            if not isinstance(total_bytes, int):
                total_bytes = 0
            if (
                recorded_hash == package_hash
                and paths.result.is_dir()
                and not paths.result.is_symlink()
            ):
                _audit(paths, "reused", package_hash=package_hash, attempts=attempts)
                return JobOutcome(
                    job_id=paths.job_id,
                    status="reused",
                    package_hash=package_hash,
                    total_bytes=total_bytes,
                    file_count=file_count,
                    attempts=attempts,
                )
            if recorded_hash != package_hash:
                _audit(paths, "rejected", error_code=X_JOB_CONFLICT, attempts=attempts)
                return JobOutcome(
                    job_id=paths.job_id,
                    status="rejected",
                    package_hash=package_hash,
                    error_code=X_JOB_CONFLICT,
                    attempts=attempts,
                )
            _remove_partial(paths)

        _remove_partial(paths)
        reserve = settings.ZIP_DISK_RESERVE_BYTES if reserve_bytes is None else reserve_bytes
        if not _disk_reserve_ok(artifacts, reserve):
            attempts = _increment_attempts(paths)
            _audit(paths, "rejected", error_code=X_DISK_RESERVE, attempts=attempts)
            return JobOutcome(
                job_id=paths.job_id,
                status="rejected",
                package_hash=package_hash,
                error_code=X_DISK_RESERVE,
                attempts=attempts,
            )

        if paths.cancel.exists():
            _audit(paths, "cancelled", package_hash=package_hash, attempts=attempts)
            return JobOutcome(
                job_id=paths.job_id,
                status="cancelled",
                package_hash=package_hash,
                error_code=X_CANCELLED,
                attempts=attempts,
            )

        deadline_s = (
            settings.ZIP_JOB_DEADLINE_SECONDS if deadline_seconds is None else deadline_seconds
        )
        deadline = time.monotonic() + deadline_s
        # Persist the attempt before the long extraction so a hard kill/OOM
        # still advances ATTEMPTS and the redelivery loop can quarantine.
        attempts = _increment_attempts(paths)
        started = time.monotonic()
        _audit(
            paths,
            "extract",
            package_hash=package_hash,
            zip_bytes=len(data),
            attempts=attempts,
            limits={"max_zip_bytes": max_zip_bytes, "deadline_s": deadline_s},
        )
        try:
            result = extract_zip(
                data,
                paths.result,
                deadline=deadline,
                cancel_check=paths.cancel.exists,
            )
        except ExtractionError as exc:
            status = _status_for(exc.code)
            _audit(
                paths,
                status,
                package_hash=package_hash,
                error_code=exc.code,
                attempts=attempts,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            _remove_partial(paths)
            return JobOutcome(
                job_id=paths.job_id,
                status=status,
                package_hash=package_hash,
                error_code=exc.code,
                attempts=attempts,
            )
        except SoftTimeLimitExceeded:
            _audit(
                paths,
                "timeout",
                package_hash=package_hash,
                error_code=X_TIMEOUT,
                attempts=attempts,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            _remove_partial(paths)
            raise
        except Exception:
            _audit(
                paths,
                "error",
                package_hash=package_hash,
                error_code=X_INTERNAL,
                attempts=attempts,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            _remove_partial(paths)
            raise

        job_size = _tree_size(paths.result)
        max_job = settings.ZIP_JOB_MAX_BYTES if job_max_bytes is None else job_max_bytes
        if job_size > max_job:
            _remove_partial(paths)
            _audit(paths, "rejected", error_code=X_JOB_TOO_LARGE, attempts=attempts)
            return JobOutcome(
                job_id=paths.job_id,
                status="rejected",
                package_hash=package_hash,
                error_code=X_JOB_TOO_LARGE,
                attempts=attempts,
            )

        payload = {
            "package_hash": result.package_hash,
            "files": [
                {"path": item.path, "size": item.size, "sha256": item.sha256}
                for item in result.files
            ],
            "total_bytes": result.total_bytes,
            "completed_at": datetime.now(UTC).isoformat(),
            "attempts": attempts,
        }
        try:
            _write_json_atomic(paths.completed, payload)
        except OSError:
            _remove_partial(paths)
            _audit(paths, "rejected", error_code=X_INTERNAL, attempts=attempts)
            return JobOutcome(
                job_id=paths.job_id,
                status="rejected",
                package_hash=package_hash,
                error_code=X_INTERNAL,
                attempts=attempts,
            )

        _audit(
            paths,
            "complete",
            package_hash=result.package_hash,
            zip_bytes=len(data),
            extracted_bytes=result.total_bytes,
            file_count=len(result.files),
            attempts=attempts,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return JobOutcome(
            job_id=paths.job_id,
            status="completed",
            package_hash=result.package_hash,
            total_bytes=result.total_bytes,
            file_count=len(result.files),
            attempts=attempts,
        )
    finally:
        lock.release()


def _status_for(code: str) -> str:
    if code == X_TIMEOUT:
        return "timeout"
    if code == X_CANCELLED:
        return "cancelled"
    return "rejected"


def cleanup_expired_jobs(
    *,
    artifacts_root: Path | None = None,
    staging_ttl: int | None = None,
    completed_ttl: int | None = None,
    now: float | None = None,
) -> dict[str, int]:
    """Remove expired job directories; active locks are skipped."""
    _, artifacts = _roots(None, artifacts_root)
    if not artifacts.is_dir():
        return {"removed": 0, "skipped": 0}
    current = time.time() if now is None else now
    incomplete_cutoff = current - (
        settings.ZIP_STAGING_TTL_SECONDS if staging_ttl is None else staging_ttl
    )
    completed_cutoff = current - (
        settings.ZIP_COMPLETED_TTL_SECONDS if completed_ttl is None else completed_ttl
    )
    removed = 0
    skipped = 0
    try:
        entries = list(os.scandir(artifacts))
    except OSError:
        return {"removed": 0, "skipped": 0}
    for entry in entries:
        if not entry.is_dir(follow_symlinks=False):
            continue
        try:
            uuid.UUID(entry.name)
        except ValueError:
            continue
        job_dir = Path(entry.path)
        lock_path = job_dir / LOCK_FILE
        fd: int | None = None
        try:
            if lock_path.exists() and not lock_path.is_symlink():
                fd = os.open(lock_path, os.O_RDWR)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    os.close(fd)
                    fd = None
                    skipped += 1
                    continue
            completed_path = job_dir / COMPLETED_FILE
            if completed_path.is_symlink():
                continue
            if completed_path.is_file():
                cutoff = completed_cutoff
                mtime = completed_path.stat().st_mtime
            else:
                cutoff = incomplete_cutoff
                mtime = job_dir.stat().st_mtime
            if mtime < cutoff:
                _remove_tree(job_dir)
                removed += 1
        except OSError:
            continue
        finally:
            if fd is not None:
                os.close(fd)
    return {"removed": removed, "skipped": skipped}
