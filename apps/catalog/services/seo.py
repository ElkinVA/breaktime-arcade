"""Per-language SEO metadata for public catalog pages (§2.19).

Game detail pages derive the title/description from the localized
``GameTranslation`` (SEO overrides first, then name/short description).
Catalog list pages use the localized catalog UI strings. Alternates are
emitted for every active site language plus ``x-default`` pointing at the
fallback language, matching the language sitemap (§2.15/§2.19).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from django.conf import settings

from apps.catalog.constants import FALLBACK_LANGUAGE_CODE
from apps.catalog.models import Game, GameTranslation, Genre, GenreTranslation
from apps.i18n.models import Language
from apps.i18n.services import translate

SITE_NAME = "Breaktime Arcade"
OG_LOCALES = {
    "en": "en_US",
    "de": "de_DE",
    "nl": "nl_NL",
    "ru": "ru_RU",
    "fr": "fr_FR",
    "es": "es_ES",
}


@dataclass(frozen=True)
class SeoAlternate:
    """A ``<link rel="alternate" hreflang="...">`` entry."""

    hreflang: str
    url: str


@dataclass(frozen=True)
class SeoMeta:
    """Rendered by ``templates/partials/seo_meta.html``.

    ``json_ld`` holds pre-serialized, HTML-safe JSON-LD documents emitted as
    ``<script type="application/ld+json">`` blocks.
    """

    title: str
    description: str
    canonical_url: str
    alternates: tuple[SeoAlternate, ...] = field(default_factory=tuple)
    og_type: str = "website"
    og_locale: str = FALLBACK_LANGUAGE_CODE
    noindex: bool = False
    json_ld: tuple[str, ...] = field(default_factory=tuple)


def _og_locale(language_code: str) -> str:
    """Open Graph locale is ``language_TERRITORY``; fall back to the code."""
    return OG_LOCALES.get(language_code, language_code)


def _origin() -> str:
    return settings.PORTAL_ORIGIN.rstrip("/")


def _absolute(path: str) -> str:
    return f"{_origin()}{path}"


def _normalize_codes(codes: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    normalized: list[str] = []
    for code in codes:
        value = str(code).strip().lower()
        if value and value not in seen:
            seen.add(value)
            normalized.append(value)
    return tuple(normalized)


def _x_default(codes: tuple[str, ...]) -> str:
    """Fallback language for ``x-default``; ``en`` is mandatory for routing."""
    return FALLBACK_LANGUAGE_CODE if FALLBACK_LANGUAGE_CODE in codes else codes[0]


def _ui_string(language_code: str, key: str) -> str:
    language = Language.objects.filter(code=language_code).first()
    fallback = Language.objects.filter(code=FALLBACK_LANGUAGE_CODE).first()
    if language is None:
        language = fallback
    if language is None:
        return ""
    return translate("catalog", key, language, fallback=fallback)


def _translation_slugs(game: Game) -> dict[str, str]:
    return {
        str(translation.language.code).lower(): translation.slug
        for translation in game.translations.all()
    }


def _slug_for(slugs: dict[str, str], language_code: str, fallback_slug: str) -> str:
    return slugs.get(language_code) or slugs.get(FALLBACK_LANGUAGE_CODE) or fallback_slug


def _alternates(
    language_codes: tuple[str, ...],
    path_for: Callable[[str], str],
) -> tuple[SeoAlternate, ...]:
    """Alternates for active languages plus ``x-default``."""
    alternates = [
        SeoAlternate(hreflang=code, url=_absolute(path_for(code))) for code in language_codes
    ]
    alternates.append(
        SeoAlternate(
            hreflang="x-default",
            url=_absolute(path_for(_x_default(language_codes))),
        )
    )
    return tuple(alternates)


def _game_title(translation: GameTranslation | None, game: Game) -> str:
    if translation is not None:
        if translation.seo_title.strip():
            return translation.seo_title.strip()
        if translation.name.strip():
            return translation.name.strip()
    return game.technical_id


def _game_description(translation: GameTranslation | None) -> str:
    if translation is None:
        return ""
    if translation.seo_description.strip():
        return translation.seo_description.strip()
    return translation.short_description.strip()


def _localized_genre(game: Game, language_code: str) -> str:
    """Genre name in ``language_code``; falls back to English, then the code."""
    translations = list(game.primary_genre.translations.all())
    for translation in translations:
        if translation.language.code == language_code and translation.name.strip():
            return translation.name.strip()
    for translation in translations:
        if translation.language.code == FALLBACK_LANGUAGE_CODE and translation.name.strip():
            return translation.name.strip()
    return game.primary_genre.code


def _video_game_payload(
    *,
    name: str,
    description: str,
    url: str,
    language_code: str,
    genre: str = "",
    published_at: datetime | None = None,
    play_minutes: int | None = None,
) -> dict[str, Any]:
    """A schema.org ``VideoGame``/``Game`` document from localized values."""
    payload: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": ["VideoGame", "Game"],
        "name": name,
        "url": url,
        "inLanguage": language_code,
        "applicationCategory": "Game",
        "gamePlatform": "Web browser",
        "publisher": {
            "@type": "Organization",
            "name": SITE_NAME,
            "url": f"{_origin()}/",
        },
    }
    if description:
        payload["description"] = description
    if genre:
        payload["genre"] = genre
    if published_at is not None:
        payload["datePublished"] = published_at.date().isoformat()
    if play_minutes:
        # ISO 8601 duration, e.g. PT5M.
        payload["timeRequired"] = f"PT{int(play_minutes)}M"
    return payload


def _breadcrumb_payload(items: Iterable[tuple[str, str]]) -> dict[str, Any]:
    """A schema.org ``BreadcrumbList`` from ``(localized name, absolute URL)``."""
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": position, "name": name, "item": url}
            for position, (name, url) in enumerate(items, start=1)
        ],
    }


def _json_ld(payload: dict[str, Any]) -> str:
    """Serialize JSON-LD and make it safe to embed inside ``<script>``."""
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return serialized.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _genre_title(translation: GenreTranslation | None, genre: Genre) -> str:
    if translation is not None:
        if translation.seo_title.strip():
            return translation.seo_title.strip()
        if translation.name.strip():
            return translation.name.strip()
    return genre.code


def _genre_description(translation: GenreTranslation | None, language_code: str) -> str:
    if translation is not None:
        if translation.seo_description.strip():
            return translation.seo_description.strip()
        if translation.description.strip():
            return translation.description.strip()
    return _ui_string(language_code, "meta_description") or _ui_string(language_code, "title")


def _genre_translation_slugs(genre: Genre) -> dict[str, str]:
    return {
        str(translation.language.code).lower(): translation.slug
        for translation in genre.translations.all()
    }


def home_seo(
    language_code: str,
    active_language_codes: Iterable[str],
    *,
    canonical_url: str,
) -> SeoMeta:
    """SEO metadata for the localized public home page."""
    language_code = str(language_code).lower()
    codes = _normalize_codes(active_language_codes)
    if not codes:
        codes = (FALLBACK_LANGUAGE_CODE,)
    title = (
        _ui_string(language_code, "meta_title")
        or _ui_string(language_code, "hero_title")
        or SITE_NAME
    )
    description = (
        _ui_string(language_code, "meta_description")
        or _ui_string(language_code, "hero_subtitle")
        or title
    )

    def path_for(code: str) -> str:
        return f"/{code}/"

    return SeoMeta(
        title=title,
        description=description,
        canonical_url=canonical_url,
        alternates=_alternates(codes, path_for),
        og_type="website",
        og_locale=_og_locale(language_code),
    )


def genre_seo(
    genre: Genre,
    translation: GenreTranslation | None,
    language_code: str,
    active_language_codes: Iterable[str],
    *,
    canonical_url: str,
    noindex: bool = False,
) -> SeoMeta:
    """SEO metadata for one localized genre landing page."""
    language_code = str(language_code).lower()
    codes = _normalize_codes(active_language_codes)
    if not codes:
        codes = (FALLBACK_LANGUAGE_CODE,)
    title = _genre_title(translation, genre)
    description = _genre_description(translation, language_code)
    slugs = _genre_translation_slugs(genre)

    def path_for(code: str) -> str:
        slug = _slug_for(slugs, code, genre.code)
        return f"/{code}/genres/{slug}/"

    breadcrumbs = _breadcrumb_payload(
        (
            (SITE_NAME, _absolute(f"/{language_code}/")),
            (
                _ui_string(language_code, "title") or "Game catalog",
                _absolute(f"/{language_code}/games/"),
            ),
            (title, canonical_url),
        )
    )
    collection = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title,
        "description": description,
        "url": canonical_url,
        "inLanguage": language_code,
    }
    return SeoMeta(
        title=title,
        description=description,
        canonical_url=canonical_url,
        alternates=_alternates(codes, path_for),
        og_type="website",
        og_locale=_og_locale(language_code),
        noindex=noindex,
        json_ld=(_json_ld(breadcrumbs), _json_ld(collection)),
    )


def game_seo(
    game: Game,
    translation: GameTranslation | None,
    language_code: str,
    active_language_codes: Iterable[str],
) -> SeoMeta:
    """SEO metadata for a published game detail page in ``language_code``."""
    language_code = str(language_code).lower()
    codes = _normalize_codes(active_language_codes)
    if not codes:
        codes = (FALLBACK_LANGUAGE_CODE,)

    slugs = _translation_slugs(game)

    def path_for(code: str) -> str:
        slug = _slug_for(slugs, code, game.slug)
        return f"/{code}/games/{slug}/"

    current_slug = _slug_for(slugs, language_code, game.slug)
    canonical_url = _absolute(f"/{language_code}/games/{current_slug}/")
    title = _game_title(translation, game)
    description = _game_description(translation)
    catalog_title = _ui_string(language_code, "title") or "Game catalog"

    video_game = _video_game_payload(
        name=title,
        description=description,
        url=canonical_url,
        language_code=language_code,
        genre=_localized_genre(game, language_code),
        published_at=game.published_at,
        play_minutes=game.estimated_play_minutes,
    )
    breadcrumbs = _breadcrumb_payload(
        (
            (SITE_NAME, _absolute(f"/{language_code}/")),
            (catalog_title, _absolute(f"/{language_code}/games/")),
            (title, canonical_url),
        )
    )
    return SeoMeta(
        title=title,
        description=description,
        canonical_url=canonical_url,
        alternates=_alternates(codes, path_for),
        og_type="website",
        og_locale=_og_locale(language_code),
        json_ld=(_json_ld(video_game), _json_ld(breadcrumbs)),
    )


def catalog_seo(
    language_code: str,
    active_language_codes: Iterable[str],
    *,
    canonical_url: str,
    noindex: bool = False,
    cards: Iterable[dict[str, Any]] | None = None,
    genre_names: Mapping[str, str] | None = None,
) -> SeoMeta:
    """SEO metadata for the public catalog list in ``language_code``.

    When ``cards`` (the visible localized cards) are supplied, the page also
    emits an ``ItemList`` of ``VideoGame``/``Game`` entries. ``genre_names``
    maps canonical genre codes to their localized names.
    """
    language_code = str(language_code).lower()
    codes = _normalize_codes(active_language_codes)
    if not codes:
        codes = (FALLBACK_LANGUAGE_CODE,)

    title = _ui_string(language_code, "title") or "Game catalog"
    description = _ui_string(language_code, "meta_description") or title
    catalog_url = _absolute(f"/{language_code}/games/")

    def path_for(code: str) -> str:
        return f"/{code}/games/"

    blocks = [
        _json_ld(
            _breadcrumb_payload(
                (
                    (SITE_NAME, _absolute(f"/{language_code}/")),
                    (title, catalog_url),
                )
            )
        )
    ]
    if cards is not None:
        items: list[dict[str, Any]] = []
        for position, card in enumerate(cards, start=1):
            game = card["game"]
            translation = card.get("translation")
            card_slug = (
                translation.slug if translation is not None and translation.slug else game.slug
            )
            card_name = (
                translation.name.strip()
                if translation is not None and translation.name.strip()
                else game.technical_id
            )
            card_description = (
                translation.short_description.strip() if translation is not None else ""
            )
            genre_code = game.primary_genre.code
            card_genre = (
                genre_names.get(genre_code, genre_code) if genre_names is not None else genre_code
            )
            items.append(
                {
                    "@type": "ListItem",
                    "position": position,
                    "item": _video_game_payload(
                        name=card_name,
                        description=card_description,
                        url=_absolute(f"/{language_code}/games/{card_slug}/"),
                        language_code=language_code,
                        genre=card_genre,
                        published_at=game.published_at,
                        play_minutes=game.estimated_play_minutes,
                    ),
                }
            )
        if items:
            blocks.append(
                _json_ld(
                    {
                        "@context": "https://schema.org",
                        "@type": "ItemList",
                        "itemListElement": items,
                    }
                )
            )

    return SeoMeta(
        title=title,
        description=description,
        canonical_url=canonical_url,
        alternates=_alternates(codes, path_for),
        og_type="website",
        og_locale=_og_locale(language_code),
        noindex=noindex,
        json_ld=tuple(blocks),
    )
