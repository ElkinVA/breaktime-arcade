"""Slug history: permanent 301 redirects after a slug change (§2.4.1, §2.6).

``Game.slug`` and ``GameTranslation.slug`` are editable; every persisted change
keeps the previous value here so old public URLs can answer ``301`` instead of
``404``.  The module also resolves an old slug to a published game and builds
the canonical current-language detail URL.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django.db import IntegrityError
from django.db.models import Q

from apps.catalog.constants import FALLBACK_LANGUAGE_CODE
from apps.catalog.models import Game, GameSlugHistory, GameTranslation


def _record(*, game_id: UUID, language_id: UUID | None, slug: str) -> None:
    normalized = str(slug)
    if not normalized:
        return
    lookup: dict[str, Any] = {"game_id": game_id, "slug": normalized}
    if language_id is None:
        lookup["language__isnull"] = True
    else:
        lookup["language_id"] = language_id
    try:
        GameSlugHistory.objects.get_or_create(**lookup)
    except IntegrityError:
        # A concurrent rename inserted the same history row between our
        # ``SELECT`` and ``INSERT``.  The unique constraint won the race, so
        # re-fetch the now-existing row instead of failing the slug change.
        GameSlugHistory.objects.get(**lookup)


def record_game_slug(game: Game, old_slug: str) -> None:
    """Remember a replaced language-neutral ``Game.slug``."""
    if game.pk is None:
        return
    _record(game_id=game.pk, language_id=None, slug=old_slug)


def record_translation_slug(translation: GameTranslation, old_slug: str) -> None:
    """Remember a replaced localized ``GameTranslation.slug``."""
    _record(
        game_id=translation.game_id,
        language_id=translation.language_id,
        slug=old_slug,
    )


def resolve_old_slug(slug: str, language_code: str) -> Game | None:
    """Return the published game whose history contains ``slug``.

    Language-neutral ``Game.slug`` entries apply to every language; localized
    entries only apply to their own language.  Only published games are
    returned, so a stale slug of a draft or hidden game still yields ``404``.
    """
    from apps.catalog.services.catalog import published_games

    return (
        published_games()
        .filter(
            Q(slug_history__language__isnull=True)
            | Q(slug_history__language__code=str(language_code).lower()),
            slug_history__slug=slug,
        )
        .order_by("-slug_history__created_at", "-slug_history__id")
        .first()
    )


def canonical_game_path(game: Game, language_code: str) -> str:
    """Current canonical detail URL for ``game`` in ``language_code``.

    Mirrors the catalog SEO canonical rule: the localized slug when it exists,
    then the English slug, then the language-neutral ``Game.slug``.
    """
    code = str(language_code).lower()
    slugs = {
        str(translation.language.code).lower(): translation.slug
        for translation in game.translations.all()
    }
    slug = slugs.get(code) or slugs.get(FALLBACK_LANGUAGE_CODE) or game.slug
    return f"/{code}/games/{slug}/"


__all__ = [
    "canonical_game_path",
    "record_game_slug",
    "record_translation_slug",
    "resolve_old_slug",
]
