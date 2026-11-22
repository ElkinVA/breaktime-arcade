"""Local, read-only product analytics for the CRM (§2.18).

There is no external analytics provider and no device identifier: every
number is derived from existing platform records for an explicit inclusive
date range. ``preview``/``autotest`` sessions are excluded from all product
aggregates, and only published games appear in top lists, so unreleased game
data cannot leak through the dashboard or its exports.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from django.db.models import Avg, Sum
from django.utils import timezone

from apps.catalog.models import Game
from apps.gameplay.models import GameDailyStats, GameSession
from apps.moderation.models import Complaint
from apps.ratings.models import GameRatingVote

DEFAULT_RANGE_DAYS = 30
MAX_RANGE_DAYS = 366
TOP_GAMES_LIMIT = 10


class AnalyticsRangeError(ValueError):
    """Invalid or unsafe date range requested by a staff member."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class DateRange:
    """Inclusive calendar range in UTC."""

    start: date
    end: date

    @property
    def start_at(self) -> datetime:
        return datetime.combine(self.start, time.min, tzinfo=UTC)

    @property
    def end_at_exclusive(self) -> datetime:
        return datetime.combine(self.end + timedelta(days=1), time.min, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class TopGame:
    technical_id: str
    slug: str
    sessions: int
    unique_sessions: int
    completions: int


@dataclass(frozen=True, slots=True)
class AnalyticsSnapshot:
    date_from: date
    date_to: date
    published_games: int
    new_games: int
    sessions: int
    user_sessions: int
    guest_sessions: int
    finished_sessions: int
    completion_rate: float
    plays: int
    rating_votes: int
    average_rating: float
    complaints: int
    open_complaints: int
    resolved_complaints: int
    top_games: tuple[TopGame, ...]


def _today() -> date:
    return timezone.now().astimezone(UTC).date()


def _parse_date(raw: str, field: str) -> date:
    try:
        return date.fromisoformat(raw.strip())
    except TypeError, ValueError:
        raise AnalyticsRangeError(
            "invalid_date",
            f"Некорректная дата {field}: используйте формат YYYY-MM-DD.",
        ) from None


def parse_date_range(
    params: Mapping[str, str],
    *,
    today: date | None = None,
    default_days: int = DEFAULT_RANGE_DAYS,
    max_days: int = MAX_RANGE_DAYS,
) -> DateRange:
    """Build a bounded inclusive range from ``date_from``/``date_to``."""
    current = today or _today()
    raw_start = str(params.get("date_from") or "").strip()
    raw_end = str(params.get("date_to") or "").strip()

    if raw_start and raw_end:
        start = _parse_date(raw_start, "date_from")
        end = _parse_date(raw_end, "date_to")
    elif raw_start:
        start = _parse_date(raw_start, "date_from")
        end = current
    elif raw_end:
        end = _parse_date(raw_end, "date_to")
        start = end - timedelta(days=default_days - 1)
    else:
        end = current
        start = end - timedelta(days=default_days - 1)

    if end < start:
        raise AnalyticsRangeError(
            "range_order",
            "Конец диапазона не может быть раньше начала.",
        )
    if (end - start).days + 1 > max_days:
        raise AnalyticsRangeError(
            "range_too_large",
            f"Диапазон не может превышать {max_days} дней.",
        )
    return DateRange(start=start, end=end)


def _top_games(date_range: DateRange) -> tuple[TopGame, ...]:
    rows = (
        GameDailyStats.objects.filter(
            date__range=(date_range.start, date_range.end),
            game__status=Game.STATUS_PUBLISHED,
        )
        .values("game__technical_id", "game__slug")
        .annotate(
            sessions=Sum("sessions"),
            unique_sessions=Sum("unique_sessions"),
            completions=Sum("completions"),
        )
        .order_by("-sessions", "game__technical_id")[:TOP_GAMES_LIMIT]
    )
    return tuple(
        TopGame(
            technical_id=str(row["game__technical_id"]),
            slug=str(row["game__slug"]),
            sessions=int(row["sessions"] or 0),
            unique_sessions=int(row["unique_sessions"] or 0),
            completions=int(row["completions"] or 0),
        )
        for row in rows
    )


def build_snapshot(date_range: DateRange) -> AnalyticsSnapshot:
    """Aggregate existing records for ``date_range`` with bounded queries."""
    start_at = date_range.start_at
    end_at = date_range.end_at_exclusive
    in_range = {"created_at__gte": start_at, "created_at__lt": end_at}

    sessions = GameSession.objects.filter(
        **in_range,
        mode__in=[GameSession.MODE_USER, GameSession.MODE_GUEST],
    )
    sessions_total = sessions.count()
    user_sessions = sessions.filter(mode=GameSession.MODE_USER).count()
    guest_sessions = sessions.filter(mode=GameSession.MODE_GUEST).count()
    finished_sessions = sessions.filter(state=GameSession.STATE_FINISHED).count()
    completion_rate = round(finished_sessions * 100 / sessions_total, 1) if sessions_total else 0.0

    plays_total = (
        GameDailyStats.objects.filter(
            date__range=(date_range.start, date_range.end),
            game__status=Game.STATUS_PUBLISHED,
        ).aggregate(total=Sum("sessions"))["total"]
        or 0
    )

    votes = GameRatingVote.objects.filter(**in_range, is_valid=True)
    rating_votes = votes.count()
    average_rating = votes.aggregate(average=Avg("value"))["average"]
    average_rating_value = round(float(average_rating), 2) if average_rating else 0.0

    complaints = Complaint.objects.filter(**in_range)
    complaints_total = complaints.count()
    open_complaints = complaints.filter(
        status__in=[Complaint.STATUS_NEW, Complaint.STATUS_ASSIGNED],
    ).count()
    resolved_complaints = complaints.filter(status=Complaint.STATUS_RESOLVED).count()

    published_games = Game.objects.filter(status=Game.STATUS_PUBLISHED).count()
    new_games = Game.objects.filter(
        status=Game.STATUS_PUBLISHED,
        published_at__gte=start_at,
        published_at__lt=end_at,
    ).count()

    return AnalyticsSnapshot(
        date_from=date_range.start,
        date_to=date_range.end,
        published_games=published_games,
        new_games=new_games,
        sessions=sessions_total,
        user_sessions=user_sessions,
        guest_sessions=guest_sessions,
        finished_sessions=finished_sessions,
        completion_rate=completion_rate,
        plays=int(plays_total),
        rating_votes=rating_votes,
        average_rating=average_rating_value,
        complaints=complaints_total,
        open_complaints=open_complaints,
        resolved_complaints=resolved_complaints,
        top_games=_top_games(date_range),
    )


__all__ = [
    "AnalyticsRangeError",
    "AnalyticsSnapshot",
    "DEFAULT_RANGE_DAYS",
    "DateRange",
    "MAX_RANGE_DAYS",
    "TOP_GAMES_LIMIT",
    "TopGame",
    "build_snapshot",
    "parse_date_range",
]
