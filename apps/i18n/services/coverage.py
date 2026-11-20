"""Процент покрытия переводами для языка или игры."""

from __future__ import annotations

from apps.i18n.models import Language, TranslationEntry


def language_coverage(language: Language) -> tuple[int, int]:
    """Возвращает (переведено, всего) для всех ключей всех namespace."""
    total = (
        TranslationEntry.objects.filter(language__is_active=True)
        .values("namespace", "key")
        .distinct()
        .count()
    )
    translated = (
        TranslationEntry.objects.filter(
            language=language,
            status=TranslationEntry.STATUS_PUBLISHED,
        )
        .values("namespace", "key")
        .distinct()
        .count()
    )
    return translated, total


def language_coverage_percent(language: Language) -> int:
    translated, total = language_coverage(language)
    if total == 0:
        return 100
    return int(translated * 100 / total)
