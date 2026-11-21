"""Шаблонный тег {% ba_t "namespace.key" param=value %} (§2.15)."""

from __future__ import annotations

from typing import Any

from django import template
from django.http import HttpRequest

from apps.i18n.middleware import get_active_languages
from apps.i18n.services import translate

register = template.Library()


@register.simple_tag(takes_context=True)
def ba_t(context: dict[str, Any], full_key: str, **params: Any) -> str:
    """Перевод строки интерфейса. Ключ никогда не показывается."""
    request: HttpRequest | None = context.get("request")
    if request is None:
        return ""

    parts = full_key.split(".", 1)
    if len(parts) != 2:
        return ""
    namespace, key = parts

    current_code = getattr(request, "LANGUAGE_CODE", "en")
    # Memoise per request: the tag runs once per card and must not issue a
    # language query for every rendered card.
    languages = getattr(request, "_ba_active_languages", None)
    if languages is None:
        languages = get_active_languages()
        request._ba_active_languages = languages  # type: ignore[attr-defined]
    current = next((lang for lang in languages if lang.code == current_code), None)
    fallback = next((lang for lang in languages if lang.code == "en"), None)

    if current is None:
        return ""

    return translate(namespace, key, current, params=params, fallback=fallback)


@register.simple_tag(takes_context=True)
def ba_lang_switcher(context: dict[str, Any]) -> str:
    """HTML-разметка переключателя языков."""
    request: HttpRequest | None = context.get("request")
    if request is None:
        return ""

    languages = get_active_languages()
    current_code = getattr(request, "LANGUAGE_CODE", "en")

    items = []
    for lang in languages:
        active = "active" if lang.code == current_code else ""
        items.append(
            f'<a href="/{lang.code}/{request.path_info.lstrip("/").lstrip(current_code + "/")}" '
            f'class="lang-switcher__item {active}" lang="{lang.code}">{lang.name}</a>'
        )

    return f'<div class="lang-switcher">{"".join(items)}</div>'
