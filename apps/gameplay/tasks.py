"""Celery retention tasks for gameplay App F records (§2.22).

The purge horizons are defined by ``apps.gameplay.services.retention``.
R-036: tasks are at-least-once; every cutoff predicate is strict and the
deletes are idempotent, so a redelivered run only removes still-expired rows.
"""

from __future__ import annotations

from apps.gameplay.services.retention import (
    cleanup_gameplay_retention as cleanup_gameplay_retention_service,
)
from apps.gameplay.services.sessions import expire_stale_sessions
from celery import shared_task


@shared_task(name="apps.gameplay.tasks.cleanup_gameplay_retention")
def cleanup_gameplay_retention() -> dict[str, int]:
    """Purge old sessions, play credits and expired guest storage."""
    return cleanup_gameplay_retention_service()


@shared_task(name="apps.gameplay.tasks.expire_stale_sessions")
def expire_stale_game_sessions() -> int:
    """Expire abandoned ACTIVE sessions so they do not consume the play cap."""
    return expire_stale_sessions()
