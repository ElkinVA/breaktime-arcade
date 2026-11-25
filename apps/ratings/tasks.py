"""Nightly rating aggregate maintenance (§2.9)."""

from __future__ import annotations

from apps.ratings.services.aggregates import recalculate_all
from celery import shared_task


@shared_task(name="apps.ratings.tasks.recalculate_rating_aggregates")
def recalculate_rating_aggregates() -> dict[str, int]:
    """Recompute all rating aggregates; safe to rerun after a partial failure."""
    return recalculate_all()
