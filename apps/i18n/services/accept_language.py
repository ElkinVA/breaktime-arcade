"""Разбор Accept-Language и выбор активного языка портала."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

# parse_accept_lang_header — внутренний API Django (не экспортируется из
# django.utils.translation в 5.2.19). Публичный get_language_from_request()
# учитывает settings.LANGUAGES/cookie/path и не даёт q-веса для активных
# языков БД. При обновлении Django проверить сигнатуру и поведение парсера.
from django.utils.translation.trans_real import parse_accept_lang_header

FALLBACK_LANGUAGE_CODE = "en"


def _normalize(language: str) -> str:
    return language.replace("_", "-").lower()


def is_fallback_language_active() -> bool:
    """Проверяет обязательный en напрямую в БД, не через общий кэш языков."""
    from apps.i18n.models import Language

    return Language.objects.filter(
        code=FALLBACK_LANGUAGE_CODE,
        is_active=True,
    ).exists()


def _active_matches(language: str, active: set[str]) -> Iterable[str]:
    """Возвращает активные коды, соответствующие языковому тегу."""
    normalized = _normalize(language)
    if normalized in active:
        yield normalized

    base = normalized.split("-", 1)[0]
    if base != normalized and base in active:
        yield base


def parse_accept_language(header: str) -> list[tuple[str, float]]:
    """Разбирает заголовок по элементам, не отбрасывая корректные из-за соседних."""
    entries: list[tuple[str, float]] = []
    for raw_part in header.split(","):
        part = raw_part.strip()
        if not part:
            continue

        parsed = parse_accept_lang_header(part)
        if len(parsed) != 1:
            continue
        language, quality = parsed[0]
        if not 0 <= quality <= 1:
            continue
        entries.append((language, quality))
    return entries


def select_language(header: str, active_codes: Sequence[str]) -> str | None:
    """Выбирает язык по q-весам; None означает 406 Not Acceptable."""
    active_order = [code.lower() for code in active_codes]
    active = set(active_order)
    entries = parse_accept_language(header)

    # Пустой или полностью некорректный заголовок — fallback en.
    if not entries:
        return FALLBACK_LANGUAGE_CODE if FALLBACK_LANGUAGE_CODE in active else None

    # q=0 исключает язык (включая региональный вариант → базовый код).
    excluded: set[str] = set()
    wildcard_excluded = False
    for language, quality in entries:
        if quality > 0:
            continue
        if _normalize(language) == "*":
            wildcard_excluded = True
            continue
        excluded.update(_active_matches(language, active))

    # Python sort стабилен: при равных q сохраняется порядок заголовка.
    entries.sort(key=lambda item: item[1], reverse=True)

    for language, quality in entries:
        if quality <= 0:
            continue
        if _normalize(language) == "*":
            for code in active_order:
                if code not in excluded:
                    return code
            return None

        for code in _active_matches(language, active):
            if code not in excluded:
                return code

    # Без явного совпадения используется fallback en, если он активен и не исключён.
    if wildcard_excluded:
        return None
    if FALLBACK_LANGUAGE_CODE in active and FALLBACK_LANGUAGE_CODE not in excluded:
        return FALLBACK_LANGUAGE_CODE
    return None
