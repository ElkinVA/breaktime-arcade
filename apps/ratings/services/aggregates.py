"""Transactional rating aggregates (§2.9.5)."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable
from decimal import Decimal
from uuid import UUID

from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.db import connection, transaction
from django.db.models import Count, Sum

from apps.ratings.models import GameRatingAggregate, GameRatingVote

logger = logging.getLogger("apps.ratings.aggregates")

NIGHTLY_BATCH_SIZE = 200
AGGREGATE_FIELDS = ("total", "count", "average", "wr_score", "distribution")


def weighted_rating(average: Decimal, count: int) -> float:
    """Bayesian WR = (v/(v+m))*R + (m/(v+m))*C (§2.8)."""
    votes = Decimal(count)
    m = Decimal(str(settings.RATING_WR_M))
    c = Decimal(str(settings.RATING_WR_C))
    return float((votes / (votes + m)) * average + (m / (votes + m)) * c)


def _lock(game_id: UUID) -> None:
    raw = f"rating:{game_id}".encode()
    key = int.from_bytes(hashlib.blake2b(raw, digest_size=8).digest(), "big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])


def _computed_values(game) -> dict[str, object]:
    votes = GameRatingVote.objects.filter(game=game, is_valid=True, user__is_active=True)
    totals = votes.aggregate(total=Sum("value"), count=Count("id"))
    total = int(totals["total"] or 0)
    count = int(totals["count"] or 0)
    average = (Decimal(total) / count) if count else Decimal("0")
    distribution = {str(star): votes.filter(value=star).count() for star in range(1, 6)}
    return {
        "total": total,
        "count": count,
        "average": average.quantize(Decimal("0.01")),
        "wr_score": weighted_rating(average, count),
        "distribution": distribution,
    }


def _matches(aggregate: GameRatingAggregate, values: dict[str, object]) -> bool:
    return all(getattr(aggregate, field) == values[field] for field in AGGREGATE_FIELDS)


def recalculate(game) -> GameRatingAggregate:
    _lock(game.id)
    aggregate, _ = GameRatingAggregate.objects.update_or_create(
        game=game,
        defaults=_computed_values(game),
    )
    return aggregate


def recalculate_all(
    *,
    apply: bool = True,
    limit: int | None = None,
    offset: int = 0,
) -> dict[str, int]:
    """Recompute every game that has votes or an existing aggregate (§2.9).

    ``apply=False`` is a read-only dry run: no advisory locks are taken and
    nothing is written. Each game is processed in its own transaction with a
    single advisory lock, in ascending pk order, so the nightly job cannot
    deadlock with vote/block transitions and never holds locks for the whole
    catalog. One failing game is logged and counted, not fatal.

    ``offset`` skips the first N eligible games in pk order before ``limit`` is
    applied, so ``limit``/``offset`` walk the catalog in deterministic backfill
    pages without re-processing earlier ones.
    """
    from apps.catalog.models import Game

    game_ids = sorted(
        set(GameRatingVote.objects.values_list("game_id", flat=True))
        | set(GameRatingAggregate.objects.values_list("game_id", flat=True))
    )
    if offset > 0:
        game_ids = game_ids[offset:]
    if limit is not None:
        game_ids = game_ids[: max(0, limit)]
    scanned = updated = unchanged = failed = 0
    for start in range(0, len(game_ids), NIGHTLY_BATCH_SIZE):
        batch = game_ids[start : start + NIGHTLY_BATCH_SIZE]
        for game in Game.objects.filter(pk__in=batch).order_by("pk"):
            scanned += 1
            try:
                if apply:
                    with transaction.atomic():
                        _lock(game.id)
                        values = _computed_values(game)
                        existing = GameRatingAggregate.objects.filter(game=game).first()
                        if existing is not None and _matches(existing, values):
                            unchanged += 1
                            continue
                        GameRatingAggregate.objects.update_or_create(game=game, defaults=values)
                        updated += 1
                else:
                    values = _computed_values(game)
                    existing = GameRatingAggregate.objects.filter(game=game).first()
                    if existing is not None and _matches(existing, values):
                        unchanged += 1
                    else:
                        updated += 1
            except SoftTimeLimitExceeded:
                raise
            except Exception:
                failed += 1
                logger.exception(
                    "ratings.nightly_recalculate_failed",
                    extra={"game_id": str(game.id)},
                )
        logger.info(
            "ratings.nightly_progress",
            extra={"scanned": scanned, "updated": updated, "failed": failed},
        )
    return {
        "scanned": scanned,
        "updated": updated,
        "unchanged": unchanged,
        "failed": failed,
    }


def recalculate_user_ratings(user) -> None:
    """Recalculate every game the user voted on, in deterministic lock order.

    Advisory locks are taken per game and held until commit, so all callers
    must acquire them in the same order to avoid a multi-key deadlock. The
    caller must hold a database transaction; in autocommit the locks would be
    released after each statement and no longer protect the recalculation.
    """
    from apps.catalog.models import Game

    game_ids = sorted(
        set(GameRatingVote.objects.filter(user=user).values_list("game_id", flat=True))
    )
    for game in Game.objects.filter(pk__in=game_ids).order_by("pk"):
        recalculate(game)


def summaries(game_ids: Iterable[UUID]) -> dict[UUID, dict[str, object]]:
    """Return average/count summaries for many games in a single query."""
    ids = list(dict.fromkeys(game_ids))
    aggregates = {row.game_id: row for row in GameRatingAggregate.objects.filter(game_id__in=ids)}
    return {
        game_id: {
            "average": float(aggregates[game_id].average) if game_id in aggregates else 0.0,
            "count": aggregates[game_id].count if game_id in aggregates else 0,
        }
        for game_id in ids
    }


def summary(game, user=None) -> dict[str, object]:
    aggregate = GameRatingAggregate.objects.filter(game=game).first()
    my_vote = None
    if user is not None and getattr(user, "is_authenticated", False):
        vote = GameRatingVote.objects.filter(game=game, user=user, is_valid=True).first()
        my_vote = vote.value if vote is not None else None
    return {
        "average": float(aggregate.average) if aggregate else 0.0,
        "count": aggregate.count if aggregate else 0,
        "distribution": aggregate.distribution if aggregate else {str(i): 0 for i in range(1, 6)},
        "my_vote": my_vote,
    }
