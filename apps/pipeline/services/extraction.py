"""Web-side client for the isolated ZIP extraction worker (BA-ZIP-WORKER-001).

The Django web process never extracts untrusted archives. It writes the source
ZIP into a private job directory on the shared ``zip_uploads`` volume, enqueues
the job on the ``zip`` queue, then polls the shared ``zip_artifacts`` volume for
the worker's terminal marker. Only after the marker and per-file hashes are
verified does the importer copy the result into its own staging tree.

There is intentionally no in-process fallback: if enqueueing or polling fails,
the package is rejected with a stable ``X_*`` code.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from django.conf import settings

from apps.pipeline.services.artifacts import ArtifactError, copy_tree
from apps.pipeline.services.worker import (
    AUDIT_FILE,
    COMPLETED_FILE,
    RESULT_DIR,
    STATUS_FILE,
    normalize_job_id,
)
from apps.pipeline.tasks import enqueue_extraction
from apps.pipeline.validation.codes import (
    X_ARTIFACT_MISMATCH,
    X_ARTIFACT_READ,
    X_UPLOAD_IO,
    X_WORKER_TIMEOUT,
    X_WORKER_UNAVAILABLE,
)

SOURCE_FILE = "source.zip"
CANCEL_FILE = "CANCEL"
_TERMINAL_STATUSES = {"completed", "reused"}


class WorkerClientError(Exception):
    """Stable failure raised by the web-side worker client."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.diagnostics = dict(diagnostics or {})


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    job_id: str
    status: str
    package_hash: str
    result_root: Path
    total_bytes: int = 0
    file_count: int = 0
    attempts: int = 0
    task_id: str = ""
    completed: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _roots(uploads_root: Path | None, artifacts_root: Path | None) -> tuple[Path, Path]:
    uploads = Path(uploads_root or settings.ZIP_UPLOADS_ROOT)
    artifacts = Path(artifacts_root or settings.ZIP_ARTIFACTS_ROOT)
    return uploads, artifacts


def _ensure_private_dir(path: Path) -> None:
    """Ensure the shared uploads root exists; never widen or reset its mode.

    The root may be group-writable in an orchestrated deployment, so chmod is
    intentionally left to the volume provisioner. Each per-job directory is
    created private below.
    """
    try:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError:
        raise WorkerClientError(X_UPLOAD_IO, "Не удалось подготовить каталог загрузки") from None
    if path.is_symlink() or not path.is_dir():
        raise WorkerClientError(X_UPLOAD_IO, "Каталог загрузки небезопасен")


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except OSError, ValueError:
        return False
    return True


def upload_dir(job_id: str, uploads_root: Path | None = None) -> tuple[Path, Path]:
    """Return the canonical ``(job_dir, source)`` paths for a job."""
    uploads = Path(uploads_root or settings.ZIP_UPLOADS_ROOT)
    canonical = normalize_job_id(job_id)
    job_dir = uploads / canonical
    return job_dir, job_dir / SOURCE_FILE


def write_source(job_id: str, data: bytes, uploads_root: Path | None = None) -> Path:
    """Write the untrusted ZIP into a private, worker-readable job directory.

    The source is created with ``O_EXCL | O_NOFOLLOW`` and persisted before the
    queue message is sent; the worker validates the same path through ``/proc``.
    """
    uploads, _ = _roots(uploads_root, None)
    _ensure_private_dir(uploads)
    job_dir, source = upload_dir(job_id, uploads)
    try:
        job_dir.mkdir(mode=0o700)
    except FileExistsError:
        if job_dir.is_symlink() or not job_dir.is_dir():
            raise WorkerClientError(X_UPLOAD_IO, "Каталог задания небезопасен") from None
    except OSError:
        raise WorkerClientError(X_UPLOAD_IO, "Не удалось создать каталог задания") from None
    if job_dir.is_symlink() or not job_dir.is_dir():
        raise WorkerClientError(X_UPLOAD_IO, "Каталог задания небезопасен")
    try:
        job_dir.chmod(0o700)
    except OSError:
        raise WorkerClientError(X_UPLOAD_IO, "Не удалось выставить права каталога") from None

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(source, flags, 0o600)
    except OSError:
        raise WorkerClientError(X_UPLOAD_IO, "Не удалось записать исходный ZIP") from None
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        raise WorkerClientError(X_UPLOAD_IO, "Не удалось записать исходный ZIP") from None
    try:
        source.chmod(0o600)
    except OSError:
        raise WorkerClientError(X_UPLOAD_IO, "Не удалось выставить права исходного ZIP") from None
    _fsync_dir(job_dir)
    return source


def cancel_job(job_id: str, uploads_root: Path | None = None) -> bool:
    """Ask the worker to stop a running job (best-effort cooperative cancel)."""
    job_dir, _ = upload_dir(job_id, uploads_root)
    if job_dir.is_symlink() or not job_dir.is_dir():
        return False
    marker = job_dir / CANCEL_FILE
    flags = os.O_WRONLY | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(marker, flags, 0o600)
        os.close(fd)
    except OSError:
        return False
    return True


def remove_source(job_id: str, uploads_root: Path | None = None) -> None:
    """Delete the transient upload after a successful import (best-effort)."""
    job_dir, _ = upload_dir(job_id, uploads_root)
    if job_dir.is_symlink():
        return
    shutil.rmtree(job_dir, ignore_errors=True)


def _fsync_dir(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        fd = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _read_json(path: Path) -> dict[str, Any] | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except OSError, ValueError:
        return None
    return value if isinstance(value, dict) else None


def _int_value(value: object) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def _str_value(value: object) -> str:
    return value if isinstance(value, str) else ""


def _job_dir(job_id: str, artifacts_root: Path) -> Path:
    canonical = normalize_job_id(job_id)
    return artifacts_root / canonical


def _result_root(job_dir: Path, artifacts_root: Path) -> Path | None:
    result = job_dir / RESULT_DIR
    if result.is_symlink() or not result.is_dir():
        return None
    if not _is_within(result, artifacts_root):
        return None
    return result


def _from_completed(
    job_id: str,
    package_hash: str,
    completed: dict[str, Any],
    result_root: Path,
) -> ExtractionResult:
    recorded = _str_value(completed.get("package_hash"))
    if recorded != package_hash:
        raise WorkerClientError(
            X_ARTIFACT_MISMATCH,
            "Хеш распакованного пакета не совпадает с исходным ZIP",
            diagnostics={"job_id": job_id},
        )
    files = completed.get("files")
    return ExtractionResult(
        job_id=job_id,
        status="completed",
        package_hash=recorded,
        result_root=result_root,
        total_bytes=_int_value(completed.get("total_bytes")),
        file_count=len(files) if isinstance(files, list) else 0,
        attempts=_int_value(completed.get("attempts")),
        completed=completed,
        diagnostics={"marker": COMPLETED_FILE},
    )


def _from_status(job_id: str, status: dict[str, Any]) -> WorkerClientError | None:
    state = _str_value(status.get("status"))
    if state in _TERMINAL_STATUSES or state == "busy":
        return None
    code = _str_value(status.get("error_code")) or X_WORKER_UNAVAILABLE
    messages = {
        "timeout": "Изолированный worker не завершил распаковку вовремя",
        "cancelled": "Распаковка отменена",
        "quarantined": "Пакет помещён в карантин после повторных сбоев",
        "failed": "Изолированный worker завершился с ошибкой",
        "rejected": "Изолированный worker отклонил пакет",
    }
    message = messages.get(state, "Изолированный worker не смог распаковать пакет")
    return WorkerClientError(
        code,
        message,
        diagnostics={"job_id": job_id, "worker_status": state},
    )


def _terminal_audit(job_dir: Path) -> WorkerClientError | None:
    """Fallback for workers killed before writing STATUS.json."""
    path = job_dir / AUDIT_FILE
    if path.is_symlink() or not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        name = _str_value(event.get("event"))
        if name == "cancelled":
            return WorkerClientError("X_CANCELLED", "Распаковка отменена")
        if name in {"rejected", "quarantine", "error", "timeout"}:
            code = _str_value(event.get("error_code")) or X_WORKER_UNAVAILABLE
            return WorkerClientError(code, "Изолированный worker отклонил пакет")
    return None


def _poll_once(
    job_id: str,
    package_hash: str,
    artifacts_root: Path,
) -> ExtractionResult | None:
    job_dir = _job_dir(job_id, artifacts_root)
    if job_dir.is_symlink() or not job_dir.is_dir():
        return None
    if not _is_within(job_dir, artifacts_root):
        raise WorkerClientError(X_ARTIFACT_READ, "Каталог результата вне хранилища")

    error: WorkerClientError | None = None
    status = _read_json(job_dir / STATUS_FILE)
    if status is not None:
        error = _from_status(job_id, status)
        if error is not None:
            raise error

    completed = _read_json(job_dir / COMPLETED_FILE)
    result_root = _result_root(job_dir, artifacts_root)
    if completed is not None and result_root is not None:
        return _from_completed(job_id, package_hash, completed, result_root)

    if status is not None and _str_value(status.get("status")) in _TERMINAL_STATUSES:
        # Status claims success but the immutable result marker is missing or
        # unsafe. Do not fall back to trusting the tree.
        raise WorkerClientError(
            X_ARTIFACT_MISMATCH,
            "Worker сообщил об успехе без корректного результата",
            diagnostics={"job_id": job_id},
        )

    audit_error = _terminal_audit(job_dir)
    if audit_error is not None:
        raise audit_error
    return None


def wait_for_result(
    job_id: str,
    package_hash: str,
    *,
    artifacts_root: Path | None = None,
    timeout: float,
    poll_interval: float = 0.5,
) -> ExtractionResult:
    """Poll the shared artifacts volume until a verified terminal state."""
    _, artifacts = _roots(None, artifacts_root)
    deadline = time.monotonic() + max(0.0, timeout)
    interval = max(0.01, poll_interval)
    while True:
        result = _poll_once(job_id, package_hash, artifacts)
        if result is not None:
            return result
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise WorkerClientError(
                X_WORKER_TIMEOUT,
                "Изолированный worker не завершил распаковку вовремя",
                diagnostics={"job_id": job_id},
            )
        time.sleep(min(interval, remaining))


def extract_package(
    *,
    job_id: str,
    data: bytes,
    package_hash: str,
    uploads_root: Path | None = None,
    artifacts_root: Path | None = None,
    wait_seconds: float | None = None,
    poll_interval: float | None = None,
) -> ExtractionResult:
    """Submit one extraction and wait for its verified result."""
    write_source(job_id, data, uploads_root)
    try:
        task_id = str(enqueue_extraction(job_id) or "")
    except WorkerClientError:
        raise
    except Exception as exc:
        # No fallback: a package that could not be queued is rejected.
        raise WorkerClientError(
            X_WORKER_UNAVAILABLE,
            "Очередь изолированного worker недоступна",
            diagnostics={"job_id": job_id, "exception": type(exc).__name__},
        ) from None

    timeout = (
        float(settings.ZIP_IMPORT_WAIT_SECONDS) if wait_seconds is None else float(wait_seconds)
    )
    interval = (
        float(settings.ZIP_IMPORT_POLL_INTERVAL_SECONDS)
        if poll_interval is None
        else float(poll_interval)
    )
    try:
        result = wait_for_result(
            job_id,
            package_hash,
            artifacts_root=artifacts_root,
            timeout=timeout,
            poll_interval=interval,
        )
    except WorkerClientError as exc:
        exc.diagnostics.setdefault("task_id", task_id)
        raise
    return replace(result, task_id=task_id)


def _safe_relative(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise WorkerClientError(X_ARTIFACT_MISMATCH, "Некорректный путь в результате worker")
    if "\\" in value or value.startswith("/") or (len(value) > 1 and value[1] == ":"):
        raise WorkerClientError(X_ARTIFACT_MISMATCH, "Небезопасный путь в результате worker")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise WorkerClientError(X_ARTIFACT_MISMATCH, "Небезопасный путь в результате worker")
    return value


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(64 * 1024):
                digest.update(chunk)
    except OSError:
        raise WorkerClientError(X_ARTIFACT_READ, "Не удалось прочитать результат worker") from None
    return digest.hexdigest()


def materialize_result(result: ExtractionResult, destination: Path) -> Path:
    """Copy the worker result into a private staging tree and verify hashes."""
    files = result.completed.get("files")
    if not isinstance(files, list):
        raise WorkerClientError(X_ARTIFACT_MISMATCH, "Worker не передал список файлов")
    try:
        destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    except OSError:
        raise WorkerClientError(X_ARTIFACT_MISMATCH, "Каталог распаковки уже существует") from None
    try:
        copy_tree(result.result_root, destination)
    except ArtifactError as exc:
        raise WorkerClientError(exc.code, exc.message) from None

    expected: set[str] = set()
    for item in files:
        if not isinstance(item, dict):
            raise WorkerClientError(X_ARTIFACT_MISMATCH, "Некорректная запись результата worker")
        relative = _safe_relative(item.get("path"))
        expected.add(relative)
        target = destination.joinpath(*relative.split("/"))
        if target.is_symlink() or not target.is_file():
            raise WorkerClientError(X_ARTIFACT_MISMATCH, "Файл результата отсутствует")
        size = item.get("size")
        if not isinstance(size, int) or target.stat().st_size != size:
            raise WorkerClientError(X_ARTIFACT_MISMATCH, "Размер файла результата не совпадает")
        digest = item.get("sha256")
        if not isinstance(digest, str) or _file_sha256(target) != digest:
            raise WorkerClientError(X_ARTIFACT_MISMATCH, "Хеш файла результата не совпадает")

    actual = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    if actual != expected:
        raise WorkerClientError(X_ARTIFACT_MISMATCH, "Состав результата worker не совпадает")
    return destination


__all__ = [
    "CANCEL_FILE",
    "ExtractionResult",
    "SOURCE_FILE",
    "WorkerClientError",
    "cancel_job",
    "extract_package",
    "materialize_result",
    "remove_source",
    "upload_dir",
    "wait_for_result",
    "write_source",
]
