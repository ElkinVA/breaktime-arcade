"""Transactional rating aggregates (§2.9.5)."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from decimal import Decimal
from uuid import UUID

from django.conf import settings
from django.db import connection
from django.db.models import Count, Sum

from apps.ratings.models import GameRatingAggregate, GameRatingVote


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


def recalculate(game) -> GameRatingAggregate:
    _lock(game.id)
    votes = GameRatingVote.objects.filter(game=game, is_valid=True, user__is_active=True)
    totals = votes.aggregate(total=Sum("value"), count=Count("id"))
    total = int(totals["total"] or 0)
    count = int(totals["count"] or 0)
    average = (Decimal(total) / count) if count else Decimal("0")
    distribution = {str(star): votes.filter(value=star).count() for star in range(1, 6)}
    aggregate, _ = GameRatingAggregate.objects.update_or_create(
        game=game,
        defaults={
            "total": total,
            "count": count,
            "average": average.quantize(Decimal("0.01")),
            "wr_score": weighted_rating(average, count),
            "distribution": distribution,
        },
    )
    return aggregate


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
