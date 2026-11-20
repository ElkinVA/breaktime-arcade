"""Контекст для шаблонов: URL файла темы."""

from __future__ import annotations

from django.http import HttpRequest

from apps.theme.services import get_active_theme_css


def theme(request: HttpRequest) -> dict[str, object]:
    active_hash, _ = get_active_theme_css()
    return {
        "theme_css_url": f"/theme-{active_hash}.css",
    }
