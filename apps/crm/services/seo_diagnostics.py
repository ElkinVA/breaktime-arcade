"""SEO-диагностика CRM (§2.19).

Read-only projections of the published catalog for the staff SEO screen:
empty localized descriptions, duplicate per-language page titles, assets
without alt text and incomplete translation coverage. Every diagnostic is a
separate function so it can be tested in isolation; a screen build loads the
published games once and reuses that prefetched list for all four queries.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from django.db.models import QuerySet

from apps.catalog.models import Game, GameTranslation

DESCRIPTION_MISSING = "description"
META_DESCRIPTION_MISSING = "meta_description"
MISSING_TRANSLATION = "missing_translation"
UNSUPPORTED_LANGUAGE = "unsupported_language"


def _normalized_codes(codes: Iterable[str]) -> tuple[str, ...]:
    """Lower-case, de-duplicate and keep the caller's language order."""
    seen: set[str] = set()
    normalized: list[str] = []
    for code in codes:
        value = str(code).strip().lower()
        if value and value not in seen:
            seen.add(value)
            normalized.append(value)
    return tuple(normalized)


def published_games() -> QuerySet[Game]:
    """Published games only, with relations used by every diagnostic prefetched."""
    return (
        Game.objects.filter(status=Game.STATUS_PUBLISHED)
        .select_related("current_version")
        .prefetch_related("translations__language", "assets")
        .order_by("technical_id")
    )


def _translations(game: Game) -> dict[str, GameTranslation]:
    return {
        str(translation.language.code).lower(): translation
        for translation in game.translations.all()
    }


def _effective_title(translation: GameTranslation) -> str:
    """Page title mirrors the public SEO page: SEO title, then name (§2.19)."""
    return translation.seo_title.strip() or translation.name.strip()


def _title_key(title: str) -> str:
    """Compare titles case-insensitively and with collapsed whitespace."""
    return " ".join(title.casefold().split())


@dataclass(frozen=True)
class DescriptionIssue:
    """A published game with an empty localized description."""

    game: Game
    language_code: str
    reason: str


@dataclass(frozen=True)
class DuplicateTitleIssue:
    """Two or more games sharing the same effective page title in one language."""

    language_code: str
    title: str
    games: tuple[Game, ...]


@dataclass(frozen=True)
class MissingAltIssue:
    """An asset without alt text for one active language."""

    game: Game
    language_code: str
    asset_type: str
    sort_order: int


@dataclass(frozen=True)
class TranslationIssue:
    """A published game missing localized catalog content for one language."""

    game: Game
    language_code: str
    reason: str


@dataclass(frozen=True)
class LanguageSummary:
    """Per-language counts for the diagnostics overview."""

    language_code: str
    empty_descriptions: int
    duplicate_titles: int
    missing_alt: int
    incomplete_translations: int

    @property
    def total(self) -> int:
        return (
            self.empty_descriptions
            + self.duplicate_titles
            + self.missing_alt
            + self.incomplete_translations
        )


@dataclass(frozen=True)
class SeoDiagnostics:
    """Everything the SEO diagnostics template needs, already resolved."""

    language_codes: tuple[str, ...]
    summaries: tuple[LanguageSummary, ...]
    descriptions: tuple[DescriptionIssue, ...]
    duplicate_titles: tuple[DuplicateTitleIssue, ...]
    missing_alt: tuple[MissingAltIssue, ...]
    incomplete_translations: tuple[TranslationIssue, ...]

    @property
    def total_issues(self) -> int:
        return (
            len(self.descriptions)
            + len(self.duplicate_titles)
            + len(self.missing_alt)
            + len(self.incomplete_translations)
        )


def empty_description_issues(
    active_language_codes: Iterable[str],
    games: Iterable[Game] | None = None,
) -> tuple[DescriptionIssue, ...]:
    """Localized translations with a blank long or meta description.

    Missing translations are reported by :func:`incomplete_translation_issues`;
    this query only inspects translations that exist, so fallback pages are not
    double-counted here.
    """
    active = _normalized_codes(active_language_codes)
    published = published_games() if games is None else games
    issues: list[DescriptionIssue] = []
    for game in published:
        translations = _translations(game)
        for code in active:
            translation = translations.get(code)
            if translation is None:
                continue
            if not translation.description.strip():
                issues.append(DescriptionIssue(game, code, DESCRIPTION_MISSING))
            elif not (translation.seo_description.strip() or translation.short_description.strip()):
                issues.append(DescriptionIssue(game, code, META_DESCRIPTION_MISSING))
    return tuple(issues)


def duplicate_title_issues(
    active_language_codes: Iterable[str],
    games: Iterable[Game] | None = None,
) -> tuple[DuplicateTitleIssue, ...]:
    """Published games whose effective title collides inside one language."""
    active = _normalized_codes(active_language_codes)
    published = published_games() if games is None else games
    grouped: dict[tuple[str, str], list[tuple[str, Game]]] = defaultdict(list)
    for game in published:
        translations = _translations(game)
        for code in active:
            translation = translations.get(code)
            if translation is None:
                continue
            title = _effective_title(translation)
            if not title:
                continue
            grouped[(code, _title_key(title))].append((title, game))

    issues: list[DuplicateTitleIssue] = []
    for code in active:
        keys = sorted(key for language, key in grouped if language == code)
        for key in keys:
            entries = grouped[(code, key)]
            if len(entries) < 2:
                continue
            issues.append(
                DuplicateTitleIssue(
                    language_code=code,
                    title=entries[0][0],
                    games=tuple(game for _title, game in entries),
                )
            )
    return tuple(issues)


def missing_alt_issues(
    active_language_codes: Iterable[str],
    games: Iterable[Game] | None = None,
) -> tuple[MissingAltIssue, ...]:
    """Assets without a non-blank ``alt`` value for one active language."""
    active = _normalized_codes(active_language_codes)
    published = published_games() if games is None else games
    issues: list[MissingAltIssue] = []
    for game in published:
        for asset in game.assets.all():
            alt = asset.alt if isinstance(asset.alt, dict) else {}
            for code in active:
                value = alt.get(code)
                if not isinstance(value, str) or not value.strip():
                    issues.append(
                        MissingAltIssue(
                            game=game,
                            language_code=code,
                            asset_type=str(asset.type),
                            sort_order=int(asset.sort_order),
                        )
                    )
    return tuple(issues)


def incomplete_translation_issues(
    active_language_codes: Iterable[str],
    games: Iterable[Game] | None = None,
) -> tuple[TranslationIssue, ...]:
    """Published games without localized content for an active language.

    A language is incomplete when no ``GameTranslation`` exists for it, or when
    the current version does not declare it in ``supported_languages``. Missing
    translations take precedence in the reported reason.
    """
    active = _normalized_codes(active_language_codes)
    published = published_games() if games is None else games
    issues: list[TranslationIssue] = []
    for game in published:
        translations = _translations(game)
        version = game.current_version
        supported = (
            {str(code).strip().lower() for code in (version.supported_languages or [])}
            if version is not None
            else set()
        )
        for code in active:
            if code not in translations:
                issues.append(TranslationIssue(game, code, MISSING_TRANSLATION))
            elif code not in supported:
                issues.append(TranslationIssue(game, code, UNSUPPORTED_LANGUAGE))
    return tuple(issues)


def build_seo_diagnostics(active_language_codes: Iterable[str]) -> SeoDiagnostics:
    """Run all four published-game diagnostics and add a per-language summary."""
    active = _normalized_codes(active_language_codes)
    games = tuple(published_games())
    descriptions = empty_description_issues(active, games)
    duplicates = duplicate_title_issues(active, games)
    alts = missing_alt_issues(active, games)
    translations = incomplete_translation_issues(active, games)

    summaries = tuple(
        LanguageSummary(
            language_code=code,
            empty_descriptions=sum(1 for issue in descriptions if issue.language_code == code),
            duplicate_titles=sum(1 for issue in duplicates if issue.language_code == code),
            missing_alt=sum(1 for issue in alts if issue.language_code == code),
            incomplete_translations=sum(1 for issue in translations if issue.language_code == code),
        )
        for code in active
    )
    return SeoDiagnostics(
        language_codes=active,
        summaries=summaries,
        descriptions=descriptions,
        duplicate_titles=duplicates,
        missing_alt=alts,
        incomplete_translations=translations,
    )


__all__ = [
    "DESCRIPTION_MISSING",
    "MISSING_TRANSLATION",
    "META_DESCRIPTION_MISSING",
    "UNSUPPORTED_LANGUAGE",
    "DescriptionIssue",
    "DuplicateTitleIssue",
    "LanguageSummary",
    "MissingAltIssue",
    "SeoDiagnostics",
    "TranslationIssue",
    "build_seo_diagnostics",
    "duplicate_title_issues",
    "empty_description_issues",
    "incomplete_translation_issues",
    "missing_alt_issues",
    "published_games",
]
