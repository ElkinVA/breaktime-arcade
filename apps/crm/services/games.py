"""Staff game inventory services (§2.16.2).

The list and card screens are read-only projections of the catalog. Queries are
bounded: relation access is prefetched once per request so a list or a card
never issues a query per game or per version.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from django.db.models import Count, Prefetch, Q, QuerySet

from apps.catalog.models import Game, GameVersion, Genre
from apps.catalog.services.catalog import localized_translation
from apps.catalog.services.localization import LocalizationCoverage, localization_coverage
from apps.pipeline.services.publishing import autotest_passed

GAME_STATUS_FILTERS = tuple(code for code, _label in Game.STATUS_CHOICES)


@dataclass(frozen=True)
class GameFilters:
    """Validated list filters. Unknown values are ignored."""

    status: str = ""
    genre: str = ""


@dataclass(frozen=True)
class GameCounters:
    """Inventory counters shown above the list."""

    total: int
    published: int
    draft: int


@dataclass(frozen=True)
class VersionRow:
    """One immutable version in the card history."""

    version: GameVersion
    blockers: int
    autotest_passed: bool
    is_current: bool

    @property
    def publishable(self) -> bool:
        return not self.is_current and self.blockers == 0 and self.autotest_passed


@dataclass(frozen=True)
class GameListRow:
    """A single inventory row."""

    game: Game
    title: str
    version: GameVersion | None
    localization: LocalizationCoverage | None


@dataclass(frozen=True)
class GameListPage:
    """Everything the list template needs, already resolved."""

    counters: GameCounters
    rows: tuple[GameListRow, ...]
    filters: GameFilters
    genres: tuple[Genre, ...]
    statuses: tuple[tuple[str, str], ...]
    active_language_codes: tuple[str, ...]


@dataclass(frozen=True)
class GameCard:
    """Game card projection with its version history."""

    game: Game
    title: str
    current_version: GameVersion | None
    versions: tuple[VersionRow, ...]
    localization: LocalizationCoverage | None


def parse_filters(params: Any) -> GameFilters:
    """Read status/genre filters from a query dict; reject unknown values."""
    status = str(params.get("status") or "").strip().lower()
    if status not in GAME_STATUS_FILTERS:
        status = ""
    genre = str(params.get("genre") or "").strip()[:32]
    return GameFilters(status=status, genre=genre)


def game_counters() -> GameCounters:
    """Total/published/draft counters in one aggregate query."""
    values = Game.objects.aggregate(
        total=Count("pk"),
        published=Count("pk", filter=Q(status=Game.STATUS_PUBLISHED)),
        draft=Count("pk", filter=Q(status=Game.STATUS_DRAFT)),
    )
    return GameCounters(
        total=int(values["total"] or 0),
        published=int(values["published"] or 0),
        draft=int(values["draft"] or 0),
    )


def _game_queryset() -> QuerySet[Game]:
    """Base game queryset with every relation used by the screens prefetched."""
    return Game.objects.select_related("primary_genre", "current_version").prefetch_related(
        "translations__language"
    )


def filter_games(filters: GameFilters) -> QuerySet[Game]:
    """All games matching the validated filters, deterministic order."""
    queryset = _game_queryset()
    if filters.status:
        queryset = queryset.filter(status=filters.status)
    if filters.genre:
        queryset = queryset.filter(
            Q(primary_genre__code=filters.genre) | Q(additional_genres__code=filters.genre)
        ).distinct()
    return queryset.order_by("technical_id")


def _title(game: Game, language_code: str) -> str:
    translation = localized_translation(game, language_code)
    return translation.name if translation is not None else str(game.technical_id)


def build_game_list_page(
    filters: GameFilters,
    active_language_codes: Iterable[str],
    *,
    language_code: str = "en",
) -> GameListPage:
    """Build the list screen without per-game queries."""
    codes = tuple(active_language_codes)
    rows = tuple(
        GameListRow(
            game=game,
            title=_title(game, language_code),
            version=game.current_version,
            localization=localization_coverage(game, codes),
        )
        for game in filter_games(filters)
    )
    return GameListPage(
        counters=game_counters(),
        rows=rows,
        filters=filters,
        genres=tuple(Genre.objects.order_by("sort_order", "code")),
        statuses=tuple(Game.STATUS_CHOICES),
        active_language_codes=codes,
    )


def _version_blockers(version: GameVersion) -> int:
    report = version.validation_report or {}
    summary = report.get("summary") if isinstance(report, dict) else None
    if isinstance(summary, dict):
        value = summary.get("blocker", 0)
        if isinstance(value, int):
            return value
    return 0 if report.get("ok", True) else 1


def _autotest_passed(version: GameVersion) -> bool:
    return autotest_passed(version)


def _version_rows(game: Game) -> tuple[VersionRow, ...]:
    current_id = game.current_version_id
    return tuple(
        VersionRow(
            version=version,
            blockers=_version_blockers(version),
            autotest_passed=_autotest_passed(version),
            is_current=version.pk == current_id,
        )
        for version in game.versions.all()
    )


def load_game_card(
    game_id: UUID,
    active_language_codes: Iterable[str],
    *,
    language_code: str = "en",
) -> GameCard | None:
    """Load a card with current version and full history in bounded queries."""
    game = (
        _game_queryset()
        .prefetch_related(
            Prefetch("versions", queryset=GameVersion.objects.order_by("-created_at"))
        )
        .filter(pk=game_id)
        .first()
    )
    if game is None:
        return None
    codes = tuple(active_language_codes)
    return GameCard(
        game=game,
        title=_title(game, language_code),
        current_version=game.current_version,
        versions=_version_rows(game),
        localization=localization_coverage(game, codes),
    )
