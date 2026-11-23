"""Read-side queries for public leaderboards (§2.11)."""

from __future__ import annotations

from typing import Any

from django.db.models import (
    Count,
    Expression,
    IntegerField,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Value,
)
from django.db.models.functions import Coalesce

from apps.gameplay.models import GameResult, LeaderboardEntry

PERSONAL_ATTEMPTS_LIMIT = 20

# §2.11.1: for ``leaderboard_only_verified`` games a result is admissible only
# from ``heuristic_validated`` upwards.
_ADMISSIBLE_TRUST_LEVELS = (
    GameResult.TRUST_HEURISTIC_VALIDATED,
    GameResult.TRUST_REPLAY_VERIFIED,
    GameResult.TRUST_SERVER_AUTHORITATIVE,
)


def rank_annotation() -> Expression:
    """Correlated count of strictly better entries for one ``LeaderboardEntry``.

    Mirrors :func:`_rank` (§2.11 tie-break: direction, then ``achieved_at ASC``,
    then ``user_id ASC``) but can annotate a whole user's game list in a single
    query, so the profile does not issue one rank query per game.
    """
    same_board = LeaderboardEntry.objects.filter(
        game_id=OuterRef("game_id"),
        epoch=OuterRef("epoch"),
        is_public=True,
    )
    better = same_board.filter(
        Q(game__score_direction="lower_is_better", value__lt=OuterRef("value"))
        | Q(game__score_direction="higher_is_better", value__gt=OuterRef("value"))
        | Q(value=OuterRef("value"), achieved_at__lt=OuterRef("achieved_at"))
        | Q(
            value=OuterRef("value"),
            achieved_at=OuterRef("achieved_at"),
            user_id__lt=OuterRef("user_id"),
        )
    )
    count = better.order_by().values("game_id").annotate(total=Count("pk")).values("total")
    return Coalesce(Subquery(count, output_field=IntegerField()), Value(0)) + 1


def annotate_rank(queryset: QuerySet[LeaderboardEntry]) -> QuerySet[LeaderboardEntry]:
    """Annotate entries with their public-board rank without per-row queries."""
    return queryset.annotate(rank=rank_annotation())


def leaderboard_ordering(game) -> list[str]:
    """Public board ordering for one game (§2.11 tie-break).

    Shared by the public leaderboard and read-only staff projections so both
    screens always present rows in exactly the same order.
    """
    if game.score_direction == "lower_is_better":
        return ["value", "achieved_at", "user_id"]
    return ["-value", "achieved_at", "user_id"]


def _entry_payload(entry: LeaderboardEntry, rank: int) -> dict[str, Any]:
    profile = getattr(entry.user, "profile", None)
    return {
        "rank": rank,
        "nickname": profile.nickname if profile is not None else None,
        "value": entry.value,
        "achieved_at": entry.achieved_at.isoformat(),
        "trust_level": entry.trust_level,
    }


def _rank(game, epoch: int, value: int, achieved_at, user_id) -> int:
    entries = LeaderboardEntry.objects.filter(game=game, epoch=epoch, is_public=True)
    if game.score_direction == "lower_is_better":
        better = entries.filter(value__lt=value) | entries.filter(
            value=value, achieved_at__lt=achieved_at
        )
    else:
        better = entries.filter(value__gt=value) | entries.filter(
            value=value, achieved_at__lt=achieved_at
        )
    tie_break = entries.filter(value=value, achieved_at=achieved_at, user_id__lt=user_id)
    return better.count() + tie_break.count() + 1


def get_leaderboard(game, *, limit: int, user) -> dict[str, Any]:
    """TOP-N for the current epoch plus the subject's own row."""
    epoch = game.leaderboard_epoch
    queryset = LeaderboardEntry.objects.filter(
        game=game, epoch=epoch, is_public=True
    ).select_related("user__profile")
    entries = list(queryset.order_by(*leaderboard_ordering(game))[:limit])
    payload = {
        "game_id": game.technical_id,
        "epoch": epoch,
        "direction": game.score_direction,
        "entries": [_entry_payload(entry, index) for index, entry in enumerate(entries, start=1)],
        "me": None,
    }
    if user is not None and user.is_authenticated:
        own = queryset.filter(user=user).first()
        if own is not None:
            payload["me"] = _entry_payload(
                own, _rank(game, epoch, own.value, own.achieved_at, own.user_id)
            )
    return payload


def get_personal_best(game, user) -> dict[str, Any]:
    epoch = game.leaderboard_epoch
    entry = (
        LeaderboardEntry.objects.filter(game=game, epoch=epoch, user=user, is_public=True)
        .select_related("user__profile")
        .first()
    )
    if entry is None:
        return {"value": None, "achieved_at": None, "rank": None}
    rank = _rank(game, epoch, entry.value, entry.achieved_at, entry.user_id)
    return {
        "value": entry.value,
        "achieved_at": entry.achieved_at.isoformat(),
        "rank": rank,
    }


def get_personal_attempts(
    game, user, *, limit: int = PERSONAL_ATTEMPTS_LIMIT
) -> list[dict[str, Any]]:
    """Latest admissible own attempts, newest first (§2.11 item 6).

    Admission mirrors §2.11.1: only public, non-quarantined, non-test results
    of the current epoch; for ``leaderboard_only_verified`` games only results
    at ``heuristic_validated`` or above are listed.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return []
    queryset = GameResult.objects.filter(
        game=game,
        epoch=game.leaderboard_epoch,
        user=user,
        is_public=True,
        is_quarantined=False,
        is_test=False,
    )
    if game.leaderboard_only_verified:
        queryset = queryset.filter(trust_level__in=_ADMISSIBLE_TRUST_LEVELS)
    return [
        {
            "value": result.value,
            "achieved_at": result.created_at,
            "trust_level": result.trust_level,
        }
        for result in queryset.order_by("-created_at", "-id")[:limit]
    ]


def get_personal_section(
    game, user, *, limit: int = PERSONAL_ATTEMPTS_LIMIT
) -> dict[str, Any] | None:
    """Personal best and latest attempts for the signed-in subject (§2.11 item 6).

    Returns ``None`` for guests so the public leaderboard stays unchanged.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    epoch = game.leaderboard_epoch
    entry = (
        LeaderboardEntry.objects.filter(game=game, epoch=epoch, user=user, is_public=True)
        .only("value", "achieved_at", "user_id")
        .first()
    )
    best = None
    if entry is not None:
        best = {
            "value": entry.value,
            "rank": _rank(game, epoch, entry.value, entry.achieved_at, entry.user_id),
            "achieved_at": entry.achieved_at,
        }
    return {"best": best, "attempts": get_personal_attempts(game, user, limit=limit)}
