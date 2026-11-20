"""Game rating vote rules (§2.9)."""

from __future__ import annotations

import hashlib
from datetime import timedelta
from uuid import UUID

from django.db import connection, transaction
from django.utils import timezone

from apps.catalog.models import Game
from apps.gameplay.models import UserGamePlaytime
from apps.gameplay.services.sessions import SessionError
from apps.ratings.models import GameRatingVote
from apps.ratings.services.aggregates import recalculate, summary

MIN_ACCOUNT_AGE = timedelta(hours=1)
CHANGE_COOLDOWN = timedelta(hours=24)
CHANGE_WINDOW = timedelta(days=30)
MAX_CHANGES_PER_WINDOW = 5
MAX_VOTES_PER_DAY = 20


def _lock_vote(game_id: UUID, user_id: UUID) -> None:
    raw = f"rating-vote:{game_id}:{user_id}".encode()
    key = int.from_bytes(hashlib.blake2b(raw, digest_size=8).digest(), "big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])


def _published_game(game_id: str) -> Game:
    game = Game.objects.filter(technical_id=game_id, status=Game.STATUS_PUBLISHED).first()
    if game is None:
        raise SessionError("E_SESSION_INVALID", "Game is not available", 404)
    return game


def vote(request, game_id: str, value: int) -> dict[str, object]:
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or not user.is_active:
        raise SessionError("E_AUTH_REQUIRED", "Authentication required", 403)
    game = _published_game(game_id)
    now = timezone.now()

    if now - user.created_at < MIN_ACCOUNT_AGE:
        raise SessionError("E_RATE_LIMIT", "Account is too new to rate", 429)

    playtime = UserGamePlaytime.objects.filter(user=user, game=game).first()
    verified = playtime.verified_seconds if playtime is not None else 0
    if verified < game.rating_min_playtime_seconds:
        raise SessionError("E_PLAYTIME_REQUIRED", "Not enough playtime to rate", 403)

    today = now.date()
    votes_today = (
        GameRatingVote.objects.filter(user=user, changed_at__date=today).exclude(game=game).count()
    )
    if votes_today >= MAX_VOTES_PER_DAY:
        raise SessionError("E_RATE_LIMIT", "Too many ratings today", 429)

    with transaction.atomic():
        _lock_vote(game.id, user.id)
        existing = GameRatingVote.objects.select_for_update().filter(game=game, user=user).first()
        if existing is not None and existing.value == value and existing.is_valid:
            return summary(game, user)

        if existing is None:
            GameRatingVote.objects.create(
                game=game,
                user=user,
                value=value,
                changed_at=now,
                change_window_started_at=now,
            )
        else:
            if existing.changed_at is not None and now - existing.changed_at < CHANGE_COOLDOWN:
                raise SessionError("E_RATE_LIMIT", "Rating was changed recently", 429)
            window_start = existing.change_window_started_at or existing.created_at
            changes = existing.change_count_30d
            if now - window_start > CHANGE_WINDOW:
                changes = 0
                window_start = now
            if changes >= MAX_CHANGES_PER_WINDOW:
                raise SessionError("E_RATE_LIMIT", "Too many rating changes", 429)
            existing.value = value
            existing.changed_at = now
            existing.change_count_30d = changes + 1
            existing.change_window_started_at = window_start
            existing.save(
                update_fields=[
                    "value",
                    "changed_at",
                    "change_count_30d",
                    "change_window_started_at",
                ]
            )
        recalculate(game)
    return summary(game, user)


def remove_user_ratings(user) -> None:
    """Account deletion removes votes and recalculates affected aggregates."""
    game_ids = list(GameRatingVote.objects.filter(user=user).values_list("game_id", flat=True))
    with transaction.atomic():
        GameRatingVote.objects.filter(user=user).delete()
        for game in Game.objects.filter(id__in=game_ids):
            recalculate(game)
