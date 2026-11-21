"""Per-language SEO metadata for public catalog pages (§2.19).

Game detail pages derive the title/description from the localized
``GameTranslation`` (SEO overrides first, then name/short description).
Catalog list pages use the localized catalog UI strings. Alternates are
emitted for every active site language plus ``x-default`` pointing at the
fallback language, matching the language sitemap (§2.15/§2.19).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from django.conf import settings

from apps.catalog.models import Game, GameTranslation
from apps.i18n.models import Language
from apps.i18n.services import translate

FALLBACK_LANGUAGE_CODE = "en"
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
    """Rendered by ``templates/partials/seo_meta.html``."""

    title: str
    description: str
    canonical_url: str
    alternates: tuple[SeoAlternate, ...] = field(default_factory=tuple)
    og_type: str = "website"
    og_locale: str = FALLBACK_LANGUAGE_CODE
    noindex: bool = False


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
    return SeoMeta(
        title=_game_title(translation, game),
        description=_game_description(translation),
        canonical_url=_absolute(f"/{language_code}/games/{current_slug}/"),
        alternates=_alternates(codes, path_for),
        og_type="website",
        og_locale=_og_locale(language_code),
    )


def catalog_seo(
    language_code: str,
    active_language_codes: Iterable[str],
    *,
    canonical_url: str,
    noindex: bool = False,
) -> SeoMeta:
    """SEO metadata for the public catalog list in ``language_code``."""
    language_code = str(language_code).lower()
    codes = _normalize_codes(active_language_codes)
    if not codes:
        codes = (FALLBACK_LANGUAGE_CODE,)

    title = _ui_string(language_code, "title") or "Game catalog"
    description = _ui_string(language_code, "meta_description") or title

    def path_for(code: str) -> str:
        return f"/{code}/games/"

    return SeoMeta(
        title=title,
        description=description,
        canonical_url=canonical_url,
        alternates=_alternates(codes, path_for),
        og_type="website",
        og_locale=_og_locale(language_code),
        noindex=noindex,
    )
