"""P3 integration: product imports extract only in the isolated zip-worker."""

from __future__ import annotations

import inspect
import io
import json
import os
import stat
import uuid
import zipfile
from pathlib import Path

import pytest

from apps.pipeline.models import GameImportDraft, ZipExtractionJob
from apps.pipeline.services import extraction, importer
from apps.pipeline.services.extraction import WorkerClientError
from apps.pipeline.services.importer import import_package
from apps.pipeline.services.worker import X_SOURCE_UNSAFE, cleanup_upload_jobs


def _zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def _package() -> bytes:
    return _zip(
        {
            "manifest.json": b'{"id": "worker_game"}',
            "index.html": b"<!doctype html><title>worker</title>",
        }
    )


def _import(tmp_path: Path, data: bytes, **kwargs: object):
    return import_package(
        data,
        storage_root=tmp_path / "store",
        runtime_root=tmp_path / "runtime",
        sdk_root=tmp_path / "sdk",
        uploads_root=tmp_path / "uploads",
        artifacts_root=tmp_path / "artifacts",
        **kwargs,
    )


def test_importer_has_no_in_process_extraction_path() -> None:
    source = inspect.getsource(importer)

    assert not hasattr(importer, "extract_zip")
    assert "extract_zip(" not in source
    assert "run_extraction(" not in source


def test_worker_unavailable_rejects_without_fallback(
    db, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(_job_id: str) -> str:
        raise RuntimeError("broker down")

    monkeypatch.setattr(extraction, "enqueue_extraction", unavailable)

    result = _import(tmp_path, _package(), worker_wait_seconds=0.5)

    assert result.status == "rejected"
    codes = {item.code for item in result.report.diagnostics}
    assert "X_WORKER_UNAVAILABLE" in codes
    job = ZipExtractionJob.objects.get()
    assert job.status == ZipExtractionJob.STATUS_FAILED
    assert job.error_code == "X_WORKER_UNAVAILABLE"
    assert not (tmp_path / "artifacts" / str(job.id) / "result").exists()
    assert result.draft.status == GameImportDraft.STATUS_REJECTED


def test_worker_timeout_is_reported(db, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extraction, "enqueue_extraction", lambda _job_id: "task-id")

    result = _import(
        tmp_path,
        _package(),
        worker_wait_seconds=0.05,
        worker_poll_interval=0.01,
    )

    assert result.status == "rejected"
    codes = {item.code for item in result.report.diagnostics}
    assert "X_WORKER_TIMEOUT" in codes
    job = ZipExtractionJob.objects.get()
    assert job.status == ZipExtractionJob.STATUS_TIMEOUT
    assert job.error_code == "X_WORKER_TIMEOUT"
    assert job.task_id == "task-id"
    # Cooperative cancel is requested; source stays until cleanup TTL.
    assert (tmp_path / "uploads" / str(job.id) / "CANCEL").is_file()


def test_worker_status_failure_is_reported(
    db, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts = tmp_path / "artifacts"

    def rejected(job_id: str) -> str:
        job_dir = artifacts / job_id
        job_dir.mkdir(parents=True)
        (job_dir / "STATUS.json").write_text(
            json.dumps(
                {
                    "job_id": job_id,
                    "status": "rejected",
                    "error_code": X_SOURCE_UNSAFE,
                    "attempts": 1,
                }
            ),
            encoding="utf-8",
        )
        return "task-id"

    monkeypatch.setattr(extraction, "enqueue_extraction", rejected)

    result = _import(tmp_path, _package(), worker_wait_seconds=0.5)

    assert result.status == "rejected"
    codes = {item.code for item in result.report.diagnostics}
    assert X_SOURCE_UNSAFE in codes
    job = ZipExtractionJob.objects.get()
    assert job.status == ZipExtractionJob.STATUS_REJECTED
    assert job.error_code == X_SOURCE_UNSAFE
    assert not (tmp_path / "uploads" / str(job.id)).exists()


def test_traversal_package_is_rejected_before_enqueue(
    db, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def record(job_id: str) -> str:
        calls.append(job_id)
        return "task-id"

    monkeypatch.setattr(extraction, "enqueue_extraction", record)
    data = _zip(
        {
            "manifest.json": b"{}",
            "index.html": b"ok",
            "../evil.js": b"alert(1)",
        }
    )

    result = _import(tmp_path, data, worker_wait_seconds=0.5)

    assert calls == []
    assert ZipExtractionJob.objects.count() == 0
    assert result.status == "rejected"
    codes = {item.code for item in result.report.diagnostics}
    assert "V_PATH_TRAVERSAL" in codes


def test_malformed_package_is_rejected_before_enqueue(
    db, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def record(job_id: str) -> str:
        calls.append(job_id)
        return "task-id"

    monkeypatch.setattr(extraction, "enqueue_extraction", record)

    result = _import(tmp_path, b"this is not a zip", worker_wait_seconds=0.5)

    assert calls == []
    assert ZipExtractionJob.objects.count() == 0
    codes = {item.code for item in result.report.diagnostics}
    assert "V_ARCHIVE_BAD" in codes


def test_source_upload_is_private_and_uses_job_uuid(tmp_path: Path) -> None:
    data = _package()
    job_id = str(uuid.uuid4())

    source = extraction.write_source(job_id, data, tmp_path / "uploads")

    assert source == tmp_path / "uploads" / job_id / "source.zip"
    assert source.read_bytes() == data
    assert stat.S_IMODE(source.stat().st_mode) == 0o600
    assert stat.S_IMODE(source.parent.stat().st_mode) == 0o700


def test_source_upload_rejects_symlinked_job_dir(tmp_path: Path) -> None:
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    job_id = str(uuid.uuid4())
    (uploads / job_id).symlink_to(outside)

    with pytest.raises(WorkerClientError) as error:
        extraction.write_source(job_id, b"data", uploads)

    assert error.value.code == "X_UPLOAD_IO"


def test_cancel_marker_is_created(tmp_path: Path) -> None:
    uploads = tmp_path / "uploads"
    job_id = str(uuid.uuid4())
    extraction.write_source(job_id, b"data", uploads)

    assert extraction.cancel_job(job_id, uploads) is True
    assert (uploads / job_id / "CANCEL").is_file()


def test_cleanup_removes_abandoned_upload_jobs(tmp_path: Path) -> None:
    uploads = tmp_path / "uploads"
    job_id = str(uuid.uuid4())
    extraction.write_source(job_id, b"data", uploads)
    old = 1_000_000.0
    os.utime(uploads / job_id, (old, old))

    result = cleanup_upload_jobs(
        uploads_root=uploads,
        staging_ttl=60,
        now=old + 61,
    )

    assert result["removed"] == 1
    assert not (uploads / job_id).exists()
