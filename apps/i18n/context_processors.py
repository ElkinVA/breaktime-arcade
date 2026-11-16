"""Контекст для шаблонов: активные языки, текущий язык."""
from __future__ import annotations

from django.http import HttpRequest

from apps.i18n.middleware import get_active_languages


def i18n(request: HttpRequest) -> dict[str, object]:
    current_code = getattr(request, "LANGUAGE_CODE", "en")
    languages = get_active_languages()
    current = next((lang for lang in languages if lang.code == current_code), None)

    return {
        "active_languages": languages,
        "current_language": current,
        "current_language_code": current_code,
    }
