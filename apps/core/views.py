"""Служебная страница ядра и локализованная обработка ошибок."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import requires_csrf_token

from apps.i18n.services.language_registry import get_active_language_codes_safely


def index(request: HttpRequest) -> JsonResponse:
    return JsonResponse(
        {
            "service": "breaktime-arcade",
            "spec": "BA-PLAT-4.2",
            "stage": "1/core",
            "health": "/healthz",
            "ready": "/readyz",
        }
    )


@requires_csrf_token
def page_not_found(request: HttpRequest, exception: Exception) -> HttpResponse:
    """Локализованная 404-страница (§2.6).

    Переключатель языков показывается только внутри языкового URL: при
    неизвестном или отсутствующем префиксе это не языковая страница, поэтому
    ссылки на языки не предлагаются.
    """
    active_codes = set(get_active_language_codes_safely())
    language_prefix = request.path_info.lstrip("/").split("/", 1)[0]
    context: dict[str, object] = {}
    if language_prefix not in active_codes:
        context["hide_language_switcher"] = True
    return render(request, "errors/404.html", context, status=404)
