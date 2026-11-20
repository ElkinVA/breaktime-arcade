"""Публичные представления каталога: только опубликованные игры."""

from __future__ import annotations

from django.db.models import Q
from django.http import Http404, HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse

from apps.catalog.models import Genre, GenreTranslation
from apps.catalog.services.catalog import (
    card_items,
    filter_games,
    genre_options,
    localized_translation,
    parse_filters,
    published_games,
    tag_options,
)


def _language(request: HttpRequest) -> str:
    return str(getattr(request, "LANGUAGE_CODE", "en"))


def home(request: HttpRequest) -> TemplateResponse:
    return TemplateResponse(
        request,
        "catalog/home.html",
        {
            "title": "Breaktime Arcade",
            "latest_cards": card_items(
                published_games().order_by("-published_at", "-id")[:6],
                _language(request),
            ),
        },
    )


def game_list(request: HttpRequest) -> TemplateResponse:
    filters = parse_filters(request.GET)
    games = filter_games(filters, _language(request))
    context = {
        "title": "Каталог",
        "games": games,
        "cards": card_items(games, _language(request)),
        "filters": filters,
        "genres": genre_options(_language(request)),
        "tags": tag_options(_language(request)),
        "language_code": _language(request),
    }
    if request.headers.get("HX-Request") == "true":
        return TemplateResponse(request, "catalog/_game_cards.html", context)
    return TemplateResponse(request, "catalog/game_list.html", context)


def game_detail(request: HttpRequest, slug: str) -> TemplateResponse:
    game = published_games().filter(Q(slug=slug) | Q(translations__slug=slug)).distinct().first()
    if game is None:
        raise Http404("game not found")
    translation = localized_translation(game, _language(request))
    return TemplateResponse(
        request,
        "catalog/game_detail.html",
        {
            "title": translation.name if translation else game.technical_id,
            "game": game,
            "translation": translation,
        },
    )


def game_play(request: HttpRequest, slug: str) -> JsonResponse:
    return JsonResponse({"status": "stub", "slug": slug})


def game_leaderboard(request: HttpRequest, slug: str) -> JsonResponse:
    return JsonResponse({"status": "stub", "slug": slug})


def genre_detail(request: HttpRequest, slug: str) -> TemplateResponse:
    language_code = _language(request)
    translation = (
        GenreTranslation.objects.filter(language__code=language_code, slug=slug)
        .select_related("genre")
        .first()
    )
    if translation is None:
        translation = (
            GenreTranslation.objects.filter(language__code="en", slug=slug)
            .select_related("genre")
            .first()
        )
    genre = translation.genre if translation is not None else get_object_or_404(Genre, code=slug)
    games = (
        filter_games(parse_filters(request.GET), language_code)
        .filter(Q(primary_genre=genre) | Q(additional_genres=genre))
        .distinct()
    )
    return TemplateResponse(
        request,
        "catalog/genre_list.html",
        {
            "title": translation.name if translation else genre.code,
            "genre": genre,
            "genre_name": translation.name if translation else genre.code,
            "games": games,
            "cards": card_items(games, language_code),
            "language_code": language_code,
        },
    )
