from __future__ import annotations

import hashlib
import io
import json
import os
import time
import uuid
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.conf import settings

from apps.pipeline.services import worker
from apps.pipeline.services.unpack import X_CANCELLED, X_TIMEOUT, ExtractionError
from apps.pipeline.services.worker import (
    X_DISK_RESERVE,
    X_JOB_BUSY,
    X_JOB_CONFLICT,
    X_JOB_ID,
    X_QUARANTINED,
    X_SOURCE_TOO_LARGE,
    X_SOURCE_UNSAFE,
    WorkerError,
    cleanup_expired_jobs,
    normalize_job_id,
    run_extraction,
)


def _zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _job_id() -> str:
    return str(uuid.uuid4())


def _put_source(uploads: Path, job_id: str, data: bytes) -> Path:
    directory = uploads / job_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "source.zip"
    path.write_bytes(data)
    return path


@pytest.fixture
def roots(tmp_path: Path) -> tuple[Path, Path]:
    uploads = tmp_path / "uploads"
    artifacts = tmp_path / "artifacts"
    uploads.mkdir()
    artifacts.mkdir()
    return uploads, artifacts


def _run(uploads: Path, artifacts: Path, job_id: str, **kwargs: object):
    options = {"deadline_seconds": 10, "reserve_bytes": 0, **kwargs}
    return run_extraction(
        job_id,
        uploads_root=uploads,
        artifacts_root=artifacts,
        **options,
    )


def test_extract_job_completes(roots: tuple[Path, Path]) -> None:
    uploads, artifacts = roots
    job_id = _job_id()
    _put_source(uploads, job_id, _zip({"index.html": b"hello", "js/game.js": b"x" * 10}))

    outcome = _run(uploads, artifacts, job_id)

    assert outcome.status == "completed"
    assert outcome.total_bytes == 15
    assert outcome.file_count == 2
    assert (artifacts / job_id / "COMPLETED.json").is_file()
    assert (artifacts / job_id / "result" / "index.html").read_bytes() == b"hello"
    events = [
        json.loads(line)["event"]
        for line in (artifacts / job_id / "audit.jsonl").read_text().splitlines()
    ]
    assert events == ["received", "extract", "complete"]
    assert not list((artifacts / job_id).glob(".ba-extract-*"))


def test_extraction_uses_validated_bytes_not_reopened_source(
    roots: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    uploads, artifacts = roots
    job_id = _job_id()
    original = _zip({"index.html": b"original"})
    _put_source(uploads, job_id, original)
    real_extract = worker.extract_zip

    def replace_then_extract(data: bytes, destination: Path, **kwargs: object):
        _put_source(uploads, job_id, _zip({"index.html": b"replaced"}))
        return real_extract(data, destination, **kwargs)

    monkeypatch.setattr(worker, "extract_zip", replace_then_extract)
    outcome = _run(uploads, artifacts, job_id)

    assert outcome.status == "completed"
    assert (artifacts / job_id / "result" / "index.html").read_bytes() == b"original"
    payload = json.loads((artifacts / job_id / "COMPLETED.json").read_text())
    assert payload["package_hash"] == hashlib.sha256(original).hexdigest()


def test_fifo_source_is_rejected_without_blocking(roots: tuple[Path, Path]) -> None:
    uploads, artifacts = roots
    job_id = _job_id()
    directory = uploads / job_id
    directory.mkdir()
    os.mkfifo(directory / "source.zip")

    outcome = _run(uploads, artifacts, job_id)

    assert outcome.status == "rejected"
    assert outcome.error_code == X_SOURCE_UNSAFE


def test_corrupt_completed_marker_triggers_redo(roots: tuple[Path, Path]) -> None:
    uploads, artifacts = roots
    job_id = _job_id()
    data = _zip({"index.html": b"hello"})
    _put_source(uploads, job_id, data)
    assert _run(uploads, artifacts, job_id).status == "completed"

    (artifacts / job_id / "COMPLETED.json").write_text(
        '{"package_hash": "not-a-hash"}\n', encoding="utf-8"
    )
    outcome = _run(uploads, artifacts, job_id)

    assert outcome.status == "completed"
    payload = json.loads((artifacts / job_id / "COMPLETED.json").read_text())
    assert payload["package_hash"] == hashlib.sha256(data).hexdigest()


def test_attempts_are_persisted_before_extraction(
    roots: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    uploads, artifacts = roots
    job_id = _job_id()
    _put_source(uploads, job_id, _zip({"index.html": b"hello"}))
    seen: dict[str, str] = {}

    def fail(data: bytes, destination: Path, **kwargs: object) -> None:
        seen["attempts"] = (artifacts / job_id / "ATTEMPTS").read_text().strip()
        raise ExtractionError("X_IO", "boom")

    monkeypatch.setattr(worker, "extract_zip", fail)
    outcome = _run(uploads, artifacts, job_id)

    assert seen["attempts"] == "1"
    assert outcome.attempts == 1


def test_completed_job_is_reused(roots: tuple[Path, Path]) -> None:
    uploads, artifacts = roots
    job_id = _job_id()
    _put_source(uploads, job_id, _zip({"index.html": b"hello"}))
    assert _run(uploads, artifacts, job_id).status == "completed"

    outcome = _run(uploads, artifacts, job_id)

    assert outcome.status == "reused"
    assert outcome.package_hash is not None


def test_different_source_for_completed_job_is_rejected(roots: tuple[Path, Path]) -> None:
    uploads, artifacts = roots
    job_id = _job_id()
    _put_source(uploads, job_id, _zip({"index.html": b"first"}))
    assert _run(uploads, artifacts, job_id).status == "completed"

    _put_source(uploads, job_id, _zip({"index.html": b"second"}))
    outcome = _run(uploads, artifacts, job_id)

    assert outcome.status == "rejected"
    assert outcome.error_code == X_JOB_CONFLICT
    assert (artifacts / job_id / "result" / "index.html").read_bytes() == b"first"


def test_source_symlink_is_rejected(roots: tuple[Path, Path], tmp_path: Path) -> None:
    uploads, artifacts = roots
    job_id = _job_id()
    real = tmp_path / "real.zip"
    real.write_bytes(_zip({"index.html": b"hello"}))
    directory = uploads / job_id
    directory.mkdir()
    (directory / "source.zip").symlink_to(real)

    outcome = _run(uploads, artifacts, job_id)

    assert outcome.status == "rejected"
    assert outcome.error_code == X_SOURCE_UNSAFE


def test_source_size_is_checked_before_preflight(roots: tuple[Path, Path]) -> None:
    uploads, artifacts = roots
    job_id = _job_id()
    _put_source(uploads, job_id, b"x" * 32)

    outcome = _run(uploads, artifacts, job_id, max_zip_bytes=16)

    assert outcome.status == "rejected"
    assert outcome.error_code == X_SOURCE_TOO_LARGE


def test_cancel_marker_prevents_extraction(roots: tuple[Path, Path]) -> None:
    uploads, artifacts = roots
    job_id = _job_id()
    _put_source(uploads, job_id, _zip({"index.html": b"hello"}))
    (uploads / job_id / "CANCEL").write_text("1", encoding="utf-8")

    outcome = _run(uploads, artifacts, job_id)

    assert outcome.status == "cancelled"
    assert outcome.error_code == X_CANCELLED
    assert not (artifacts / job_id / "result").exists()


def test_disk_reserve_is_enforced(
    roots: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    uploads, artifacts = roots
    job_id = _job_id()
    _put_source(uploads, job_id, _zip({"index.html": b"hello"}))
    monkeypatch.setattr(
        worker.os,
        "statvfs",
        lambda _path: SimpleNamespace(f_bavail=0, f_frsize=1),
    )

    outcome = _run(uploads, artifacts, job_id, reserve_bytes=1)

    assert outcome.status == "rejected"
    assert outcome.error_code == X_DISK_RESERVE


def test_attempts_quarantine_after_repeated_failures(
    roots: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    uploads, artifacts = roots
    job_id = _job_id()
    _put_source(uploads, job_id, _zip({"index.html": b"hello"}))

    def fail(*_args: object, **_kwargs: object) -> None:
        raise ExtractionError("X_IO", "boom")

    monkeypatch.setattr(worker, "extract_zip", fail)

    first = _run(uploads, artifacts, job_id)
    second = _run(uploads, artifacts, job_id)
    third = _run(uploads, artifacts, job_id)

    assert (first.status, first.attempts) == ("rejected", 1)
    assert (second.status, second.attempts) == ("rejected", 2)
    assert third.status == "quarantined"
    assert third.error_code == X_QUARANTINED


def test_active_job_lock_returns_busy(roots: tuple[Path, Path]) -> None:
    uploads, artifacts = roots
    job_id = _job_id()
    _put_source(uploads, job_id, _zip({"index.html": b"hello"}))
    paths = worker.job_paths(job_id, uploads_root=uploads, artifacts_root=artifacts)
    (artifacts / job_id).mkdir()
    lock = worker._JobLock(paths)
    assert lock.acquire()
    try:
        outcome = _run(uploads, artifacts, job_id)
    finally:
        lock.release()

    assert outcome.status == "busy"
    assert outcome.error_code == X_JOB_BUSY


def test_cleanup_removes_expired_and_skips_active(roots: tuple[Path, Path]) -> None:
    uploads, artifacts = roots
    now = time.time()
    expired_completed = artifacts / _job_id()
    expired_completed.mkdir()
    (expired_completed / "COMPLETED.json").write_text("{}", encoding="utf-8")
    _age(expired_completed / "COMPLETED.json", now - 100)
    expired_incomplete = artifacts / _job_id()
    expired_incomplete.mkdir()
    _age(expired_incomplete, now - 100)
    active = artifacts / _job_id()
    active.mkdir()
    (active / "COMPLETED.json").write_text("{}", encoding="utf-8")
    _age(active / "COMPLETED.json", now - 100)
    lock = worker._JobLock(
        worker.job_paths(active.name, uploads_root=uploads, artifacts_root=artifacts)
    )
    assert lock.acquire()
    try:
        result = cleanup_expired_jobs(
            artifacts_root=artifacts,
            staging_ttl=10,
            completed_ttl=10,
            now=now,
        )
    finally:
        lock.release()

    assert result == {"removed": 2, "skipped": 1}
    assert not expired_completed.exists()
    assert not expired_incomplete.exists()
    assert active.exists()


def _age(path: Path, timestamp: float) -> None:
    os.utime(path, (timestamp, timestamp))


def test_normalize_job_id_rejects_garbage() -> None:
    with pytest.raises(WorkerError) as error:
        normalize_job_id("../../etc/passwd")
    assert error.value.code == X_JOB_ID


def test_queue_routing_and_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.pipeline.tasks import enqueue_extraction, extract_zip_task

    assert settings.CELERY_TASK_ROUTES["apps.pipeline.tasks.extract_zip_task"]["queue"] == "zip"
    assert settings.CELERY_TASK_ROUTES["apps.pipeline.tasks.cleanup_zip_staging"]["queue"] == "zip"
    assert {"default", "celery", "zip"} <= {queue.name for queue in settings.CELERY_TASK_QUEUES}
    annotations = settings.CELERY_TASK_ANNOTATIONS["apps.pipeline.tasks.extract_zip_task"]
    assert annotations["acks_late"] is True
    assert annotations["soft_time_limit"] == 55
    assert annotations["time_limit"] == 60
    assert annotations["reject_on_worker_lost"] is True

    calls: dict[str, object] = {}

    def fake_apply_async(args: object = None, kwargs: object = None, **options: object):
        calls["args"] = args
        calls["options"] = options
        return SimpleNamespace(id="task-id")

    monkeypatch.setattr(extract_zip_task, "apply_async", fake_apply_async)
    assert enqueue_extraction("job-id") == "task-id"
    assert calls["args"] == ("job-id",)
    assert calls["options"] == {"queue": "zip"}


def test_timeout_code_maps_to_timeout_status() -> None:
    assert worker._status_for(X_TIMEOUT) == "timeout"
