"""Заглушки представлений каталога."""
from __future__ import annotations

from django.http import HttpRequest, JsonResponse
from django.template.response import TemplateResponse


def home(request: HttpRequest) -> TemplateResponse:
    return TemplateResponse(request, "catalog/home.html", {"title": "Breaktime Arcade"})


def game_list(request: HttpRequest) -> TemplateResponse:
    return TemplateResponse(request, "catalog/game_list.html", {"title": "Каталог"})


def game_detail(request: HttpRequest, slug: str) -> JsonResponse:
    return JsonResponse({"status": "stub", "slug": slug})


def game_play(request: HttpRequest, slug: str) -> JsonResponse:
    return JsonResponse({"status": "stub", "slug": slug})


def game_leaderboard(request: HttpRequest, slug: str) -> JsonResponse:
    return JsonResponse({"status": "stub", "slug": slug})


def genre_detail(request: HttpRequest, slug: str) -> JsonResponse:
    return JsonResponse({"status": "stub", "slug": slug})
