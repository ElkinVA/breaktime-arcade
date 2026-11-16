"""Раздача /theme-<hash>.css с immutable-кешем (§2.7)."""
from __future__ import annotations

from django.http import HttpRequest, HttpResponse, HttpResponseNotFound

from apps.theme.services import get_active_theme_css


def theme_css(request: HttpRequest, hash: str) -> HttpResponse:
    """Возвращает CSS темы с кешем public, max-age=31536000, immutable."""
    active_hash, css = get_active_theme_css()

    if hash != active_hash:
        return HttpResponseNotFound("Theme not found")

    response = HttpResponse(css, content_type="text/css; charset=utf-8")
    response["Cache-Control"] = "public, max-age=31536000, immutable"
    return response
