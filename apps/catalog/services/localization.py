"""Покрытие локализации игры (§2.15).

Effective languages игры — ``GameVersion.supported_languages``, пересечённые
с активными языками сайта. CRM-переопределения (``GameLocaleOverride``) в
рамках этой задачи не учитываются.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from apps.i18n.services.language_registry import get_active_language_codes_safely

if TYPE_CHECKING:
    from apps.catalog.models import Game, GameVersion


@dataclass(frozen=True)
class LocalizationCoverage:
    """Сколько активных языков сайта покрывает текущая версия игры."""

    covered: int
    total: int

    @property
    def is_full(self) -> bool:
        return self.covered == self.total

    @property
    def missing(self) -> int:
        return max(self.total - self.covered, 0)


def _normalize_codes(codes: Iterable[str]) -> tuple[str, ...]:
    """Приводит коды к нижнему регистру и убирает дубликаты, сохраняя порядок."""
    seen: set[str] = set()
    normalized: list[str] = []
    for code in codes:
        value = str(code).strip().lower()
        if value and value not in seen:
            seen.add(value)
            normalized.append(value)
    return tuple(normalized)


def effective_languages(
    version: GameVersion | None,
    active_language_codes: Iterable[str],
) -> tuple[str, ...]:
    """Языки пакета, которые одновременно являются активными языками сайта."""
    if version is None:
        return ()
    supported = {str(code).strip().lower() for code in (version.supported_languages or [])}
    return tuple(code for code in _normalize_codes(active_language_codes) if code in supported)


def localization_coverage(
    game: Game,
    active_language_codes: Iterable[str] | None = None,
) -> LocalizationCoverage | None:
    """Покрытие для игры; ``None`` — нет текущей версии или активных языков.

    ``active_language_codes`` передаётся, когда список уже получен на запрос
    (карточки каталога), чтобы не читать реестр для каждой игры.
    """
    if active_language_codes is None:
        active_language_codes = get_active_language_codes_safely()
    active = _normalize_codes(active_language_codes)
    version = game.current_version
    if version is None or not active:
        return None
    covered = len(effective_languages(version, active))
    return LocalizationCoverage(covered=covered, total=len(active))
