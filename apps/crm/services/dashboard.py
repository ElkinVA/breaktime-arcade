"""Operational counters for the staff CRM dashboard (§2.16.2).

Every counter is produced by a single bounded aggregation so rendering the
dashboard does not issue per-game or per-user queries. Service modes
(``preview``/``autotest``) are excluded from the session counter, matching the
product aggregate rules of §2.18.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.db.models import Sum
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Game
from apps.catalog.services.popularity import window_bounds
from apps.crm.models.backup import BackupRun
from apps.gameplay.models import GameDailyStats, GameSession
from apps.ratings.models import GameRatingAggregate, GameRatingVote

TOP_GAMES_LIMIT = 5
ACTIVE_ACCOUNT_WINDOW_DAYS = 30


@dataclass(frozen=True)
class PopularGame:
    """One row of the "top popular games" block."""

    technical_id: str
    slug: str
    sessions: int


@dataclass(frozen=True)
class DashboardStats:
    """Snapshot of the counters shown on the CRM dashboard."""

    published_games: int
    total_accounts: int
    active_accounts_30d: int
    sessions_today: int
    top_games: tuple[PopularGame, ...]
    average_rating: float
    new_votes_today: int
    latest_backup: BackupRun | None


def _utc_day_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Return the inclusive/exclusive UTC bounds of the current day."""
    current = now or timezone.now()
    if timezone.is_naive(current):
        current = current.replace(tzinfo=UTC)
    start = current.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _top_popular_games(*, now: datetime | None = None) -> tuple[PopularGame, ...]:
    """Top published games by 30-day popularity, bounded to ``TOP_GAMES_LIMIT``."""
    start, today = window_bounds(now)
    rows = (
        GameDailyStats.objects.filter(
            date__gte=start,
            date__lte=today,
            game__status=Game.STATUS_PUBLISHED,
        )
        .values("game__technical_id", "game__slug")
        .annotate(sessions=Sum("unique_sessions"))
        .order_by("-sessions", "game__technical_id")[:TOP_GAMES_LIMIT]
    )
    return tuple(
        PopularGame(
            technical_id=str(row["game__technical_id"]),
            slug=str(row["game__slug"]),
            sessions=int(row["sessions"] or 0),
        )
        for row in rows
    )


def _average_rating() -> float:
    """Vote-weighted average across published games with ratings."""
    totals = GameRatingAggregate.objects.filter(
        game__status=Game.STATUS_PUBLISHED,
        count__gt=0,
    ).aggregate(total=Sum("total"), count=Sum("count"))
    count = int(totals["count"] or 0)
    if count == 0:
        return 0.0
    return round(int(totals["total"] or 0) / count, 2)


def dashboard_stats(*, now: datetime | None = None) -> DashboardStats:
    """Build the dashboard snapshot with one query per counter."""
    current = now or timezone.now()
    day_start, day_end = _utc_day_bounds(current)
    active_cutoff = current - timedelta(days=ACTIVE_ACCOUNT_WINDOW_DAYS)

    published_games = Game.objects.filter(status=Game.STATUS_PUBLISHED).count()
    total_accounts = User.objects.count()
    active_accounts_30d = User.objects.filter(
        is_active=True,
        last_login__gte=active_cutoff,
    ).count()
    sessions_today = GameSession.objects.filter(
        created_at__gte=day_start,
        created_at__lt=day_end,
        mode__in=[GameSession.MODE_USER, GameSession.MODE_GUEST],
    ).count()
    new_votes_today = GameRatingVote.objects.filter(
        created_at__gte=day_start,
        created_at__lt=day_end,
    ).count()
    latest_backup = BackupRun.objects.order_by("-started_at").first()

    return DashboardStats(
        published_games=published_games,
        total_accounts=total_accounts,
        active_accounts_30d=active_accounts_30d,
        sessions_today=sessions_today,
        top_games=_top_popular_games(now=current),
        average_rating=_average_rating(),
        new_votes_today=new_votes_today,
        latest_backup=latest_backup,
    )
