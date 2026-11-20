"""Transactional rating aggregates (§2.9.5)."""

from __future__ import annotations

import hashlib
from decimal import Decimal
from uuid import UUID

from django.db import connection
from django.db.models import Count, Sum

from apps.ratings.models import GameRatingAggregate, GameRatingVote


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
            "wr_score": float(average),
            "distribution": distribution,
        },
    )
    return aggregate


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
