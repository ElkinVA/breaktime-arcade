"""Retention purge for the game import wizard (§2.22, RETENTION_PROPOSAL §D).

``GameImportDraft`` lives 7 days since its last change. Deleting a draft also
cascades its ``ZipExtractionJob`` rows, so the reported count is taken from
the per-model deletion report rather than the overall total. The strict
``updated_at`` cutoff makes the purge idempotent under at-least-once delivery
(R-036): a rerun deletes nothing.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from django.db.models import QuerySet
from django.utils import timezone

from apps.pipeline.models import GameImportDraft

GAME_IMPORT_DRAFT_RETENTION_DAYS = 7


def _now(value: datetime | None) -> datetime:
    return value or timezone.now()


def _purge(queryset: QuerySet[Any]) -> int:
    _, per_model = queryset.delete()
    return int(per_model.get(GameImportDraft._meta.label, 0))


def purge_expired_import_drafts(*, now: datetime | None = None) -> int:
    """Remove import drafts unchanged for more than 7 days."""
    cutoff = _now(now) - timedelta(days=GAME_IMPORT_DRAFT_RETENTION_DAYS)
    return _purge(GameImportDraft.objects.filter(updated_at__lt=cutoff))


def cleanup_pipeline_retention(*, now: datetime | None = None) -> dict[str, int]:
    """Run the pipeline purges and return per-type deletion counts."""
    return {"game_import_drafts": purge_expired_import_drafts(now=now)}
