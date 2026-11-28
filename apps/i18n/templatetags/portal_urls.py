"""URL-теги портала: безопасная смена языкового префикса."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast
from urllib.parse import urlsplit

from django import template
from django.http import HttpRequest

from apps.i18n.services.language_registry import get_active_language_codes_safely

register = template.Library()


def _local_override(value: object) -> str:
    """Accept only a local absolute path supplied by a page-specific mapping."""
    if not isinstance(value, str) or not value.startswith("/") or value.startswith("//"):
        return ""
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        return ""
    return value


@register.simple_tag(takes_context=True)
def language_url(context: dict[str, object], language_code: str) -> str:
    """Возвращает текущий путь с заменённым языковым префиксом и query-string.

    A page may provide ``language_paths`` (localized page-specific URLs) for
    routes whose slug is language-dependent, e.g. a genre page where the same
    slug can belong to another genre in a different language. The mapping is
    validated as a local path before it is rendered.

    Код языка должен быть активным; внешние URL не строятся.
    """
    request = context.get("request")
    if not isinstance(request, HttpRequest):
        return ""

    active_codes = set(get_active_language_codes_safely())
    if language_code not in active_codes:
        return ""

    overrides = context.get("language_paths")
    if isinstance(overrides, Mapping):
        override = _local_override(cast(Mapping[object, object], overrides).get(language_code))
        if override:
            return override

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
