"""Popularity credit and daily stats (§2.8).

A session completion credits the subject at most once per 30 minutes and
increments the UTC daily counter only when the credit row was actually
updated. Preview/autotest and sub-15s sessions never count.
"""

from __future__ import annotations

from datetime import datetime

from django.db import connection, transaction
from django.utils import timezone

from apps.core.ids import uuid7
from apps.gameplay.models import GameSession

MIN_CREDIT_DURATION_MS = 15_000
CREDIT_WINDOW = "30 minutes"


def credit_session(
    session: GameSession,
    *,
    duration_ms: int,
    completed: bool,
    now: datetime | None = None,
) -> bool:
    if session.mode not in {GameSession.MODE_USER, GameSession.MODE_GUEST}:
        return False
    if duration_ms < MIN_CREDIT_DURATION_MS:
        return False
    current = now or timezone.now()

    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO gameplay_play_credit
                (id, game_id, subject_type, subject_id, last_credited_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (game_id, subject_type, subject_id) DO UPDATE
            SET last_credited_at = EXCLUDED.last_credited_at
            WHERE gameplay_play_credit.last_credited_at
                  <= EXCLUDED.last_credited_at - interval '30 minutes'
            RETURNING 1
            """,
            [uuid7(), session.game_id, session.subject_type, session.subject_id, current],
        )
        unique_credit = cursor.fetchone() is not None
        cursor.execute(
            """
            INSERT INTO gameplay_daily_stats
                (id, game_id, date, sessions, unique_sessions, completions, avg_duration_ms)
            VALUES (%s, %s, %s, 1, %s, %s, %s)
            ON CONFLICT (game_id, date) DO UPDATE
            SET sessions = gameplay_daily_stats.sessions + 1,
                unique_sessions = gameplay_daily_stats.unique_sessions + EXCLUDED.unique_sessions,
                completions = gameplay_daily_stats.completions + EXCLUDED.completions,
                avg_duration_ms = (
                    gameplay_daily_stats.avg_duration_ms * gameplay_daily_stats.sessions
                    + EXCLUDED.avg_duration_ms
                ) / (gameplay_daily_stats.sessions + 1)
            """,
            [
                uuid7(),
                session.game_id,
                current.date(),
                1 if unique_credit else 0,
                1 if completed else 0,
                duration_ms,
            ],
        )
    return unique_credit
