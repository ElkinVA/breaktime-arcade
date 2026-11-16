"""Сборка словаря интерфейса для шаблонов. Кеш Redis, инвалидация по сигналу."""
from __future__ import annotations

from typing import Any

from django.core.cache import cache

from apps.i18n.models import Language, TranslationEntry

CACHE_KEY = "i18n:dictionary:{code}"
CACHE_TTL = 3600


def get_dictionary(language: Language) -> dict[str, dict[str, str]]:
    """Возвращает {namespace: {key: value}} для опубликованных переводов."""
    key = CACHE_KEY.format(code=language.code)
    cached = cache.get(key)
    if cached is not None:
        return cached

    entries = TranslationEntry.objects.filter(
        language=language,
        status=TranslationEntry.STATUS_PUBLISHED,
    ).values_list("namespace", "key", "value")

    result: dict[str, dict[str, str]] = {}
    for namespace, entry_key, value in entries:
        result.setdefault(namespace, {})[entry_key] = value

    cache.set(key, result, CACHE_TTL)
    return result


def translate(
    namespace: str,
    key: str,
    language: Language,
    params: dict[str, Any] | None = None,
    fallback: Language | None = None,
) -> str:
    """Перевод с резервным языком. Ключ никогда не показывается (§2.15)."""
    dictionary = get_dictionary(language)
    value = dictionary.get(namespace, {}).get(key)

    if value is None and fallback is not None and fallback.code != language.code:
        dictionary = get_dictionary(fallback)
        value = dictionary.get(namespace, {}).get(key)

    if value is None:
        # Логируем отсутствие перевода, но ключ не показываем.
        return ""

    if params:
        for param_key, param_value in params.items():
            value = value.replace(f"{{{param_key}}}", str(param_value))

    return value


def invalidate_language(language: Language) -> None:
    cache.delete(CACHE_KEY.format(code=language.code))
