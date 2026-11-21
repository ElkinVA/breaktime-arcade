"""Personal game records and verified playtime for the account cabinet (§2.10.4)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from django.db.models import F

from apps.accounts.models import User
from apps.catalog.models import Game
from apps.catalog.services.catalog import localized_translation
from apps.gameplay.models import LeaderboardEntry, UserGamePlaytime
from apps.i18n.middleware import get_active_languages
from apps.i18n.services import translate
from apps.leaderboards.services.queries import annotate_rank

__all__ = ["personal_game_records"]


def _seconds_formatter(language_code: str) -> Callable[[int | None], str | None]:
    """Build the playtime label once so rows do not re-query active languages."""
    languages = get_active_languages()
    current = next((language for language in languages if language.code == language_code), None)
    fallback = next((language for language in languages if language.code == "en"), None)
    if current is None:
        return lambda seconds: None

    def format_seconds(seconds: int | None) -> str | None:
        if seconds is None:
            return None
        translated = translate(
            "account",
            "playtime_seconds",
            current,
            params={"seconds": seconds},
            fallback=fallback,
        )
        return translated or f"{seconds} s"

    return format_seconds


def personal_game_records(user: User, language_code: str) -> list[dict[str, Any]]:
    """Union of public current-epoch records and verified playtime per game.

    Rows are built from two queries (records and playtime) with related games
    and translations prefetched, so the profile renders without N+1 queries.
    A game appears when it has a public ``LeaderboardEntry`` for the current
    epoch or a ``UserGamePlaytime`` row. Only published games are exposed
    because the cabinet links to their public detail/leaderboard pages.
    """
    entries = annotate_rank(
        LeaderboardEntry.objects.filter(
            user=user,
            is_public=True,
            epoch=F("game__leaderboard_epoch"),
            game__status=Game.STATUS_PUBLISHED,
        )
        .select_related("game")
        .prefetch_related("game__translations__language")
    )
    playtimes = (
        UserGamePlaytime.objects.filter(user=user, game__status=Game.STATUS_PUBLISHED)
        .select_related("game")
        .prefetch_related("game__translations__language")
    )

    format_seconds = _seconds_formatter(language_code)
    records: dict[Any, dict[str, Any]] = {}
    for entry in entries:
        translation = localized_translation(entry.game, language_code)
        records[entry.game_id] = {
            "game": entry.game,
            "name": translation.name if translation is not None else entry.game.technical_id,
            "best_value": entry.value,
            "rank": cast(Any, entry).rank,
            "achieved_at": entry.achieved_at,
            "playtime_seconds": None,
            "playtime_display": None,
        }

    for playtime in playtimes:
        record = records.get(playtime.game_id)
        if record is not None:
            record["playtime_seconds"] = playtime.verified_seconds
            record["playtime_display"] = format_seconds(playtime.verified_seconds)
            continue
        translation = localized_translation(playtime.game, language_code)
        records[playtime.game_id] = {
            "game": playtime.game,
            "name": translation.name if translation is not None else playtime.game.technical_id,
            "best_value": None,
            "rank": None,
            "achieved_at": None,
            "playtime_seconds": playtime.verified_seconds,
            "playtime_display": format_seconds(playtime.verified_seconds),
        }

    return sorted(
        records.values(),
        key=lambda record: (record["name"].casefold(), record["game"].technical_id.casefold()),
    )
