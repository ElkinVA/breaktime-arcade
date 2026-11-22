"""Плюрализация по CLDR через Babel (§2.15).

Legacy-ключи каталога хранятся как ``<base>_one``/``<base>_other``; новые
формы (``_few``, ``_many``, ``_zero``) добавляются без переименования ключей.
Отсутствующая форма откатывается на ``_other`` в том же языке, затем на
резервный язык (``en``), поэтому ключ никогда не показывается и страница не
теряет текст при неполном наборе переводов.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from babel import Locale

if TYPE_CHECKING:
    from apps.i18n.models import Language

PLURAL_FALLBACK_FORM = "other"


def plural_form(count: int, language_code: str) -> str:
    """Возвращает CLDR-форму: zero, one, two, few, many, other."""
    try:
        return Locale.parse(language_code).plural_form(count)
    except Exception:  # noqa: BLE001 - неизвестная/битая локаль не должна ломать рендер
        return PLURAL_FALLBACK_FORM


def _form_chain(form: str) -> tuple[str, ...]:
    """CLDR-форма и безопасный откат на ``other`` в рамках одного языка."""
    if form == PLURAL_FALLBACK_FORM:
        return (PLURAL_FALLBACK_FORM,)
    return (form, PLURAL_FALLBACK_FORM)


def _language_chain(
    language: Language,
    fallback: Language | None,
) -> tuple[Language, ...]:
    if fallback is None or fallback.pk == language.pk:
        return (language,)
    return (language, fallback)


def _interpolate(value: str, params: dict[str, Any]) -> str:
    for key, replacement in params.items():
        value = value.replace(f"{{{key}}}", str(replacement))
    return value


def plural_translation(
    namespace: str,
    base_key: str,
    count: int,
    language: Language,
    *,
    fallback: Language | None = None,
    params: dict[str, Any] | None = None,
) -> str:
    """Перевод плюрализованной строки для ``count`` на языке ``language``.

    Кандидаты перебираются в порядке: ``<base>_<cldr>``, ``<base>_other``,
    устаревший ``<base>`` без суффикса; затем те же кандидаты на резервном
    языке. Пустая строка означает, что перевода нет ни в одном языке.
    """
    from apps.i18n.services.dictionary import get_dictionary

    replacements: dict[str, Any] = {"count": count}
    if params:
        replacements.update(params)

    for candidate_language in _language_chain(language, fallback):
        dictionary = get_dictionary(candidate_language)
        entries = dictionary.get(namespace, {})
        for form in _form_chain(plural_form(count, candidate_language.code)):
            value = entries.get(f"{base_key}_{form}")
            if value is not None:
                return _interpolate(value, replacements)
        legacy = entries.get(base_key)
        if legacy is not None:
            return _interpolate(legacy, replacements)

    return ""
