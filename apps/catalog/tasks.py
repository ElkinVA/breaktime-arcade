"""Каталог: обслуживание поискового вектора."""

from __future__ import annotations

from apps.catalog.services.search import refresh_search_vectors
from celery import shared_task


@shared_task
def refresh_catalog_search_vectors() -> int:
    """Пересчитывает search_vector после bulk/import изменений.

    R-036: at-least-once; idempotent UPDATE.
    """
    return refresh_search_vectors()
