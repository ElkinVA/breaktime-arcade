"""Retention purge for App F gameplay records (§2.22, RETENTION_PROPOSAL §D).

Terms are fixed by the ТЗ (Приложение D): sessions live 30 days after the
terminal transition, play credits 90 days after the last credit, and guest
storage until the 90-day inactivity TTL (``expires_at``) passes. Game results
and leaderboard rows are never removed by time; sessions referenced by a
result are protected by ``GameResult.session`` (``on_delete=PROTECT``) and are
explicitly excluded from the purge queryset.

Every purge is expressed as a single idempotent ``DELETE`` with a strict
cutoff predicate, so an at-least-once redelivery (R-036) only deletes rows
that are still older than the horizon; a rerun returns zero counts.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from django.db.models import Model, QuerySet
from django.utils import timezone

from apps.gameplay.models import GamePlayCredit, GameSession, GameStorage

GAME_SESSION_RETENTION_DAYS = 30
GAME_PLAY_CREDIT_RETENTION_DAYS = 90

# Terminal states: the session has stopped moving and will never be credited
# again. ``created``/``active`` rows are left to the session service and are
# not part of the "terminal or expired" purge.
PURGEABLE_SESSION_STATES = (
    GameSession.STATE_FINISHED,
    GameSession.STATE_EXPIRED,
    GameSession.STATE_ABORTED,
)


def _now(value: datetime | None) -> datetime:
    return value or timezone.now()


def _purge(queryset: QuerySet[Any], model: type[Model]) -> int:
    """Delete ``queryset`` and return the number of deleted ``model`` rows.

    ``QuerySet.delete()`` reports cascade deletions separately per model, so
    the reported count stays accurate even when a related row is cascaded.
    """
    _, per_model = queryset.delete()
    return int(per_model.get(model._meta.label, 0))


def purge_terminal_sessions(*, now: datetime | None = None) -> int:
    """Remove terminal sessions older than 30 days that have no result.

    ``result__isnull=True`` excludes every session referenced by a
    ``GameResult`` (PROTECT); those results and their sessions survive.
    """
    cutoff = _now(now) - timedelta(days=GAME_SESSION_RETENTION_DAYS)
    return _purge(
        GameSession.objects.filter(
            state__in=PURGEABLE_SESSION_STATES,
            updated_at__lt=cutoff,
            result__isnull=True,
        ),
        GameSession,
    )


def purge_play_credits(*, now: datetime | None = None) -> int:
    """Remove popularity credits not credited for more than 90 days."""
    cutoff = _now(now) - timedelta(days=GAME_PLAY_CREDIT_RETENTION_DAYS)
    return _purge(
        GamePlayCredit.objects.filter(last_credited_at__lt=cutoff),
        GamePlayCredit,
    )


def purge_expired_guest_storage(*, now: datetime | None = None) -> int:
    """Remove guest storage whose 90-day inactivity TTL (``expires_at``) passed.

    Only ``subject_type=anon`` rows are considered; user documents have no
    ``expires_at`` and live until account deletion (§2.10.5).
    """
    return _purge(
        GameStorage.objects.filter(
            subject_type=GameStorage.SUBJECT_ANON,
            expires_at__lt=_now(now),
        ),
        GameStorage,
    )


def cleanup_gameplay_retention(*, now: datetime | None = None) -> dict[str, int]:
    """Run all gameplay purges and return per-type deletion counts."""
    return {
        "game_sessions": purge_terminal_sessions(now=now),
        "game_play_credits": purge_play_credits(now=now),
        "guest_game_storage": purge_expired_guest_storage(now=now),
    }
