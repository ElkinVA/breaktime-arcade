"""Служебная страница ядра. Заменяется порталом на блоке 2."""

from __future__ import annotations

from django.http import HttpRequest, JsonResponse


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
