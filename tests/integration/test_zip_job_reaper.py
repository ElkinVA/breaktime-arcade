"""Stale RUNNING extraction jobs are reaped after the TTL (§5.5)."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from django.conf import settings
from django.utils import timezone

from apps.pipeline.models import GameImportDraft, ZipExtractionJob
from apps.pipeline.services.reaper import STALE_ERROR_CODE, reap_stale_extraction_jobs


def _draft() -> GameImportDraft:
    return GameImportDraft.objects.create(
        package_hash=uuid4().hex * 2,
        original_filename="reaper.zip",
    )


def _job(
    draft: GameImportDraft,
    *,
    status: str,
    started_at=None,
    created_at=None,
) -> ZipExtractionJob:
    job = ZipExtractionJob.objects.create(
        draft=draft,
        package_hash=draft.package_hash,
        status=status,
        started_at=started_at,
    )
    if created_at is not None:
        ZipExtractionJob.objects.filter(pk=job.pk).update(created_at=created_at)
    return job


@pytest.mark.django_db
def test_reaper_times_out_only_stale_running_jobs() -> None:
    now = timezone.now()
    draft = _draft()
    stale = _job(
        draft,
        status=ZipExtractionJob.STATUS_RUNNING,
        started_at=now - timedelta(seconds=settings.ZIP_JOB_STALE_SECONDS + 1),
    )
    recent = _job(
        draft,
        status=ZipExtractionJob.STATUS_RUNNING,
        started_at=now - timedelta(seconds=settings.ZIP_JOB_STALE_SECONDS - 1),
    )
    null_started = _job(
        draft,
        status=ZipExtractionJob.STATUS_RUNNING,
        started_at=None,
        created_at=now - timedelta(seconds=settings.ZIP_JOB_STALE_SECONDS + 1),
    )
    null_started_recent = _job(
        draft,
        status=ZipExtractionJob.STATUS_RUNNING,
        started_at=None,
        created_at=now - timedelta(seconds=settings.ZIP_JOB_STALE_SECONDS - 1),
    )
    exact_boundary = _job(
        draft,
        status=ZipExtractionJob.STATUS_RUNNING,
        started_at=now - timedelta(seconds=settings.ZIP_JOB_STALE_SECONDS),
    )
    queued = _job(
        draft,
        status=ZipExtractionJob.STATUS_QUEUED,
        created_at=now - timedelta(days=1),
    )
    completed = _job(
        draft,
        status=ZipExtractionJob.STATUS_COMPLETED,
        started_at=now - timedelta(days=1),
    )

    assert reap_stale_extraction_jobs(now=now) == 2

    stale.refresh_from_db()
    null_started.refresh_from_db()
    null_started_recent.refresh_from_db()
    exact_boundary.refresh_from_db()
    recent.refresh_from_db()
    queued.refresh_from_db()
    completed.refresh_from_db()
    assert stale.status == ZipExtractionJob.STATUS_TIMEOUT
    assert stale.error_code == STALE_ERROR_CODE
    assert stale.finished_at == now
    assert null_started.status == ZipExtractionJob.STATUS_TIMEOUT
    assert null_started_recent.status == ZipExtractionJob.STATUS_RUNNING
    assert exact_boundary.status == ZipExtractionJob.STATUS_RUNNING
    assert recent.status == ZipExtractionJob.STATUS_RUNNING
    assert queued.status == ZipExtractionJob.STATUS_QUEUED
    assert completed.status == ZipExtractionJob.STATUS_COMPLETED

    assert reap_stale_extraction_jobs(now=now) == 0


def test_reaper_is_scheduled_and_registered() -> None:
    entry = settings.CELERY_BEAT_SCHEDULE["pipeline-reap-stale-zip-jobs"]
    assert entry["task"] == "apps.pipeline.tasks.reap_stale_zip_jobs"
    from apps.pipeline.tasks import reap_stale_zip_jobs

    assert reap_stale_zip_jobs.name == "apps.pipeline.tasks.reap_stale_zip_jobs"


@pytest.mark.django_db
def test_reaper_task_executes_the_service() -> None:
    from apps.pipeline.tasks import reap_stale_zip_jobs

    draft = _draft()
    _job(
        draft,
        status=ZipExtractionJob.STATUS_RUNNING,
        started_at=timezone.now() - timedelta(seconds=settings.ZIP_JOB_STALE_SECONDS + 1),
    )

    assert reap_stale_zip_jobs() == {"reaped": 1}
    assert reap_stale_zip_jobs() == {"reaped": 0}
