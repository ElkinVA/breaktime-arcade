"""URL-теги портала: безопасная смена языкового префикса."""

from __future__ import annotations

from django import template
from django.http import HttpRequest

from apps.i18n.services.language_registry import get_active_language_codes_safely

register = template.Library()


@register.simple_tag(takes_context=True)
def language_url(context: dict[str, object], language_code: str) -> str:
    """Возвращает текущий путь с заменённым языковым префиксом и query-string.

    Код языка должен быть активным; внешние URL не строятся.
    """
    request = context.get("request")
    if not isinstance(request, HttpRequest):
        return ""

    active_codes = set(get_active_language_codes_safely())
    if language_code not in active_codes:
        return ""

    path = request.path_info or "/"
    segments = path.split("/")

    if len(segments) > 1 and segments[1] in active_codes:
        segments[1] = language_code
        new_path = "/".join(segments)
    elif path == "/":
        new_path = f"/{language_code}/"
    else:
        # Strict 404: неизвестный/отсутствующий языковой префикс не является
        # языковым URL и не должен переноситься в ссылку переключателя.
        return ""

    query = request.META.get("QUERY_STRING", "")
    if query:
        return f"{new_path}?{query}"
    return new_path
