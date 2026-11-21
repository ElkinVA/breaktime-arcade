"""30-day popularity read for the catalog (§2.8).

Popularity is the sum of ``GameDailyStats.unique_sessions`` over the
trailing 30 UTC days (today inclusive). Values are cached per game for 15
minutes in the default cache; a cache miss falls back to a single aggregate
query for all requested games.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from django.core.cache import cache
from django.db.models import IntegerField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.gameplay.models import GameDailyStats

POPULARITY_WINDOW_DAYS = 30
POPULARITY_CACHE_TIMEOUT = 15 * 60
CACHE_KEY_TEMPLATE = "catalog:popularity30d:{start}:{game_id}"


def _utc_today(now: datetime | None = None) -> date:
    current = now or timezone.now()
    if timezone.is_naive(current):
        current = current.replace(tzinfo=UTC)
    return current.astimezone(UTC).date()


def window_bounds(now: datetime | None = None) -> tuple[date, date]:
    """Return the inclusive ``(start, end)`` dates of the 30-day UTC window."""
    today = _utc_today(now)
    return today - timedelta(days=POPULARITY_WINDOW_DAYS - 1), today


def _cache_key(start: date, game_id: UUID) -> str:
    return CACHE_KEY_TEMPLATE.format(start=start.isoformat(), game_id=game_id)


def _read_cache(keys: list[str]) -> dict[str, Any]:
    try:
        return dict(cache.get_many(keys))
    except Exception:  # noqa: BLE001 - cache is best-effort, DB is authoritative
        return {}


def _write_cache(values: dict[str, int]) -> None:
    try:
        cache.set_many(values, POPULARITY_CACHE_TIMEOUT)
    except Exception:  # noqa: BLE001 - cache is best-effort, DB is authoritative
        return


def popularity_counts(game_ids: Iterable[UUID], *, now: datetime | None = None) -> dict[UUID, int]:
    """Return 30-day credit counts for ``game_ids`` with batched lookups."""
    ids = list(dict.fromkeys(game_ids))
    if not ids:
        return {}
    start, today = window_bounds(now)
    keys = {game_id: _cache_key(start, game_id) for game_id in ids}

    counts: dict[UUID, int] = {}
    missing: list[UUID] = []
    cached = _read_cache(list(keys.values()))
    for game_id in ids:
        key = keys[game_id]
        if key in cached:
            counts[game_id] = int(cached[key])
        else:
            missing.append(game_id)

    if missing:
        totals = {
            row["game_id"]: int(row["total"] or 0)
            for row in GameDailyStats.objects.filter(
                game_id__in=missing,
                date__gte=start,
                date__lte=today,
            )
            .values("game_id")
            .annotate(total=Sum("unique_sessions"))
        }
        pending: dict[str, int] = {}
        for game_id in missing:
            value = totals.get(game_id, 0)
            counts[game_id] = value
            pending[keys[game_id]] = value
        _write_cache(pending)

    return {game_id: counts.get(game_id, 0) for game_id in ids}


def popularity(game_id: UUID, *, now: datetime | None = None) -> int:
    """Return the 30-day credit count for a single game."""
    return popularity_counts([game_id], now=now).get(game_id, 0)


def popularity_subquery(now: datetime | None = None) -> Coalesce:
    """Database annotation usable for ``sort=popular`` ordering."""
    start, today = window_bounds(now)
    totals = (
        GameDailyStats.objects.filter(
            game_id=OuterRef("pk"),
            date__gte=start,
            date__lte=today,
        )
        .values("game")
        .annotate(total=Sum("unique_sessions"))
        .values("total")
    )
    return Coalesce(Subquery(totals, output_field=IntegerField()), Value(0))
