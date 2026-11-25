"""Leaderboard rank shared by submit responses and read-side queries (§2.11)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from apps.gameplay.models import LeaderboardEntry


def entry_rank(game, epoch: int, value: int, achieved_at: datetime, user_id: UUID) -> int:
    """Return 1-based position on the public board for one candidate row.

    §2.11 item 3 tie-break: direction, then ``achieved_at ASC``, then
    ``user_id ASC``. Kept in one place so the submit response and the
    public/profile queries cannot drift.
    """
    entries = LeaderboardEntry.objects.filter(game=game, epoch=epoch, is_public=True)
    tie_break = entries.filter(value=value, achieved_at=achieved_at, user_id__lt=user_id)
    if game.score_direction == "lower_is_better":
        better = entries.filter(value__lt=value) | entries.filter(
            value=value, achieved_at__lt=achieved_at
        )
    else:
        better = entries.filter(value__gt=value) | entries.filter(
            value=value, achieved_at__lt=achieved_at
        )
    return better.count() + tie_break.count() + 1
