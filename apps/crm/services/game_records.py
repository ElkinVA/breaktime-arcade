"""Read-only leaderboard/epoch projection for the CRM game card (§2.16.2).

The staff card must show the same board the public site shows, so ordering and
rank are not re-implemented here: both screens share
:func:`apps.leaderboards.services.queries.annotate_rank` and
:func:`apps.leaderboards.services.queries.leaderboard_ordering`.

Only public entries are rendered; archived epochs are shown as a read-only
snapshot. The module performs no writes and exposes no moderation actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.core.paginator import Page, Paginator
from django.db.models import QuerySet

from apps.catalog.models import Game
from apps.gameplay.models import LeaderboardEntry
from apps.leaderboards.services.queries import annotate_rank, leaderboard_ordering

RECORDS_PAGE_SIZE = 25


@dataclass(frozen=True)
class RecordRow:
    """One public board row with its rank inside the selected epoch."""

    rank: int
    nickname: str | None
    value: int
    achieved_at: datetime
    trust_level: str
    trust_level_label: str


@dataclass(frozen=True)
class GameRecords:
    """Everything the records partial needs for one game card request."""

    epochs: tuple[int, ...]
    current_epoch: int
    selected_epoch: int
    is_current_epoch: bool
    rows: tuple[RecordRow, ...]
    page_obj: Page[LeaderboardEntry]

    @property
    def empty(self) -> bool:
        return not self.rows


def available_epochs(game: Game) -> tuple[int, ...]:
    """Every distinct epoch that has at least one ``LeaderboardEntry`` row."""
    epochs = (
        LeaderboardEntry.objects.filter(game=game)
        .values_list("epoch", flat=True)
        .distinct()
        .order_by("-epoch")
    )
    return tuple(int(epoch) for epoch in epochs)


def _selected_epoch(game: Game, raw: Any, epochs: tuple[int, ...]) -> int:
    """Requested epoch when it exists for the game, otherwise the current one."""
    try:
        requested = int(str(raw).strip())
    except ValueError:
        return game.leaderboard_epoch
    return requested if requested in epochs else game.leaderboard_epoch


def _page_number(raw: Any) -> int:
    """Blank, non-integer and non-positive input maps to the first page.

    ``Paginator.get_page`` maps non-positive or out-of-range values to the
    last page (non-integers already fall back to page 1); the public
    leaderboard normalises invalid values to page 1, so the staff view does
    the same.
    """
    if raw is None:
        return 1
    value = str(raw).strip()
    if not value:
        return 1
    try:
        number = int(value)
    except ValueError:
        return 1
    return number if number >= 1 else 1


def _record_row(entry: LeaderboardEntry) -> RecordRow:
    profile = getattr(entry.user, "profile", None)
    return RecordRow(
        rank=int(getattr(entry, "rank", 0)),
        nickname=profile.nickname if profile is not None else None,
        value=entry.value,
        achieved_at=entry.achieved_at,
        trust_level=entry.trust_level,
        trust_level_label=entry.get_trust_level_display(),
    )


def _entry_queryset(game: Game, epoch: int) -> QuerySet[LeaderboardEntry]:
    """Public entries of one epoch in exactly the public board order."""
    return annotate_rank(
        LeaderboardEntry.objects.filter(game=game, epoch=epoch, is_public=True).select_related(
            "user__profile"
        )
    ).order_by(*leaderboard_ordering(game))


def build_game_records(
    game: Game,
    *,
    epoch: Any = None,
    page: Any = None,
    per_page: int = RECORDS_PAGE_SIZE,
) -> GameRecords:
    """Build the current or archived board page for the staff card.

    Invalid epoch/page values are clamped instead of raising: the staff screen
    must stay usable when a URL is edited by hand.
    """
    epochs = available_epochs(game)
    selected_epoch = _selected_epoch(game, epoch, epochs)
    page_obj: Page[LeaderboardEntry] = Paginator(
        _entry_queryset(game, selected_epoch), per_page
    ).get_page(_page_number(page))
    rows = tuple(_record_row(entry) for entry in page_obj.object_list)
    return GameRecords(
        epochs=epochs,
        current_epoch=game.leaderboard_epoch,
        selected_epoch=selected_epoch,
        is_current_epoch=selected_epoch == game.leaderboard_epoch,
        rows=rows,
        page_obj=page_obj,
    )


__all__ = [
    "RECORDS_PAGE_SIZE",
    "GameRecords",
    "RecordRow",
    "available_epochs",
    "build_game_records",
]
