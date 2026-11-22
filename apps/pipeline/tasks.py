"""Celery tasks for the isolated ZIP extraction worker (BA-ZIP-WORKER-001)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from celery.exceptions import SoftTimeLimitExceeded

from apps.pipeline.services.worker import (
    WorkerError,
    cleanup_expired_jobs,
    cleanup_upload_jobs,
    run_extraction,
)
from celery import shared_task


@shared_task(name="apps.pipeline.tasks.extract_zip_task")
def extract_zip_task(job_id: str) -> dict[str, Any]:
    """Extract one uploaded package; permanent errors are returned, not retried.

    R-036: acks_late + reject_on_worker_lost; idempotent via job lock/ATTEMPTS/reuse.
    """
    try:
        return asdict(run_extraction(job_id))
    except SoftTimeLimitExceeded:
        return {"job_id": job_id, "status": "timeout", "error_code": "X_TIMEOUT"}
    except WorkerError as exc:
        return {"job_id": job_id, "status": "rejected", "error_code": exc.code}


@shared_task(name="apps.pipeline.tasks.cleanup_zip_staging")
def cleanup_zip_staging() -> dict[str, int]:
    """Hourly backstop for abandoned staging directories and expired results.

    R-036: acks_late + reject_on_worker_lost; idempotent cleanup.
    """
    return cleanup_expired_jobs()


@shared_task(name="apps.pipeline.tasks.cleanup_zip_uploads")
def cleanup_zip_uploads() -> dict[str, int]:
    """Remove abandoned source ZIPs on the writable default-worker mount."""
    return cleanup_upload_jobs()


def enqueue_extraction(job_id: str) -> str:
    """Publish extraction explicitly to the isolated queue (web-side helper)."""
    result = extract_zip_task.apply_async((job_id,), queue="zip")
    return str(result.id)
