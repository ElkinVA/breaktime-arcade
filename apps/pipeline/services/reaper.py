"""Reap extraction jobs left RUNNING by a crashed web/worker process."""

from __future__ import annotations

from datetime import datetime, timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.pipeline.models import ZipExtractionJob

STALE_ERROR_CODE = "X_JOB_STALE"


def reap_stale_extraction_jobs(
    *,
    stale_seconds: int | None = None,
    now: datetime | None = None,
) -> int:
    """Mark RUNNING jobs older than the TTL as timed out; idempotent."""
    current = now or timezone.now()
    ttl = settings.ZIP_JOB_STALE_SECONDS if stale_seconds is None else stale_seconds
    cutoff = current - timedelta(seconds=ttl)
    candidates = (
        ZipExtractionJob.objects.filter(status=ZipExtractionJob.STATUS_RUNNING)
        .filter(Q(started_at__lt=cutoff) | Q(started_at__isnull=True, created_at__lt=cutoff))
        .values_list("pk", flat=True)
    )
    reaped = 0
    for job_id in list(candidates):
        reaped += ZipExtractionJob.objects.filter(
            pk=job_id,
            status=ZipExtractionJob.STATUS_RUNNING,
        ).update(
            status=ZipExtractionJob.STATUS_TIMEOUT,
            error_code=STALE_ERROR_CODE,
            finished_at=current,
            updated_at=current,
        )
    return reaped
