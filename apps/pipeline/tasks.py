"""Celery tasks for the isolated ZIP extraction worker (BA-ZIP-WORKER-001)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from celery.exceptions import SoftTimeLimitExceeded

from apps.pipeline.services.reaper import reap_stale_extraction_jobs
from apps.pipeline.services.retention import (
    cleanup_pipeline_retention as cleanup_pipeline_retention_service,
)
from apps.pipeline.services.runtime_cleanup import cleanup_orphan_runtimes
from apps.pipeline.services.worker import (
    WorkerError,
    cleanup_expired_jobs,
    cleanup_upload_jobs,
    run_extraction,
)
from celery import shared_task
from config.zip_celery import send_zip_task


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


@shared_task(name="apps.pipeline.tasks.dispatch_zip_cleanup")
def dispatch_zip_cleanup() -> dict[str, str]:
    """Publish the staging cleanup to the isolated zip broker.

    Beat schedules this lightweight task on the default broker; only this
    dispatcher and extraction jobs cross into `redis-zip`.
    """
    result_id = send_zip_task(
        "apps.pipeline.tasks.cleanup_zip_staging",
        queue="zip",
    )
    return {"task_id": result_id}


def _active_extraction_job_ids() -> set[str]:
    """Queued/running job ids that cleanup must never remove."""
    from apps.pipeline.models import ZipExtractionJob

    return {
        str(job_id)
        for job_id in ZipExtractionJob.objects.filter(
            status__in=[ZipExtractionJob.STATUS_QUEUED, ZipExtractionJob.STATUS_RUNNING]
        ).values_list("id", flat=True)
    }


@shared_task(name="apps.pipeline.tasks.cleanup_zip_uploads")
def cleanup_zip_uploads() -> dict[str, int]:
    """Remove abandoned source ZIPs on the writable default-worker mount.

    Active (queued/running) jobs are protected by DB state; the filesystem
    cleanup is idempotent and safe to rerun after a restart.
    """
    return cleanup_upload_jobs(active_job_ids=_active_extraction_job_ids())


@shared_task(name="apps.pipeline.tasks.reap_stale_zip_jobs")
def reap_stale_zip_jobs() -> dict[str, int]:
    """Recover jobs left RUNNING after a web/worker crash (idempotent)."""
    return {"reaped": reap_stale_extraction_jobs()}


@shared_task(name="apps.pipeline.tasks.cleanup_orphan_runtimes")
def cleanup_orphan_runtimes_task() -> dict[str, int]:
    """Daily TTL cleanup of runtime bundles not referenced by any version."""
    return cleanup_orphan_runtimes()


@shared_task(name="apps.pipeline.tasks.cleanup_pipeline_retention")
def cleanup_pipeline_retention() -> dict[str, int]:
    """Purge import drafts unchanged for more than 7 days (§2.22).

    R-036: at-least-once; the strict ``updated_at`` cutoff is idempotent.
    """
    return cleanup_pipeline_retention_service()


def enqueue_extraction(job_id: str) -> str:
    """Publish extraction explicitly to the isolated zip broker/queue."""
    return send_zip_task(
        "apps.pipeline.tasks.extract_zip_task",
        args=(job_id,),
        queue="zip",
    )
