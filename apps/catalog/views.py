"""Публичные представления каталога: только опубликованные игры."""

from __future__ import annotations

import json
import secrets
from types import SimpleNamespace
from urllib.parse import quote, urlparse

from django.conf import settings
from django.db.models import Q
from django.http import Http404, HttpRequest
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse

from apps.accounts.services.anonymous import COOKIE_NAME
from apps.catalog.models import Genre, GenreTranslation
from apps.catalog.services.catalog import (
    card_items,
    filter_games,
    genre_options,
    localized_translation,
    parse_filters,
    popular_games,
    published_games,
    tag_options,
    top_rated_games,
)
from apps.catalog.services.localization import localization_coverage
from apps.catalog.services.pagination import (
    canonical_url,
    paginate_games,
    pagination_query,
    should_noindex,
)
from apps.catalog.services.popularity import popularity
from apps.catalog.services.seo import catalog_seo, game_seo
from apps.gameplay.api.throttling import (
    GuestIpRateThrottle,
    SubjectScopedRateThrottle,
)
from apps.gameplay.services.sessions import (
    SessionError,
    activate_session,
    create_session,
)
from apps.i18n.services.language_registry import get_active_language_codes_safely
from apps.leaderboards.services.queries import get_leaderboard, get_personal_section
from apps.ratings.services.aggregates import summary as rating_summary


def _language(request: HttpRequest) -> str:
    return str(getattr(request, "LANGUAGE_CODE", "en"))


def home(request: HttpRequest) -> TemplateResponse:
    language_code = _language(request)
    active_language_codes = get_active_language_codes_safely()
    return TemplateResponse(
        request,
        "catalog/home.html",
        {
            "title": "Breaktime Arcade",
            "popular_cards": card_items(popular_games(), language_code, active_language_codes),
            "rated_cards": card_items(top_rated_games(), language_code, active_language_codes),
            "latest_cards": card_items(
                published_games().order_by("-published_at", "-id")[:6],
                language_code,
                active_language_codes,
            ),
        },
    )


def game_list(request: HttpRequest) -> TemplateResponse:
    language_code = _language(request)
    params = request.GET
    filters = parse_filters(params)
    games = filter_games(filters, language_code)
    page_obj = paginate_games(games, params)
    active_language_codes = get_active_language_codes_safely()
    page_canonical_url = canonical_url(request, params, page_obj.number)
    robots_noindex = should_noindex(page_obj.number)
    seo = catalog_seo(
        language_code,
        active_language_codes,
        canonical_url=page_canonical_url,
        noindex=robots_noindex,
    )
    context = {
        "title": seo.title,
        "games": page_obj.object_list,
        "cards": card_items(page_obj.object_list, language_code, active_language_codes),
        "filters": filters,
        "genres": genre_options(language_code),
        "tags": tag_options(language_code),
        "language_code": language_code,
        "page_obj": page_obj,
        "pagination_query": pagination_query(params),
        "pagination_hx_target": "#game-results",
        "canonical_url": page_canonical_url,
        "robots_noindex": robots_noindex,
        "seo": seo,
    }
    if request.headers.get("HX-Request") == "true":
        return TemplateResponse(request, "catalog/_game_cards.html", context)
    return TemplateResponse(request, "catalog/game_list.html", context)


def game_detail(request: HttpRequest, slug: str) -> TemplateResponse:
    game = published_games().filter(Q(slug=slug) | Q(translations__slug=slug)).distinct().first()
    if game is None:
        raise Http404("game not found")
    translation = localized_translation(game, _language(request))
    active_language_codes = get_active_language_codes_safely()
    ratings = rating_summary(game)
    seo = game_seo(game, translation, _language(request), active_language_codes)
    return TemplateResponse(
        request,
        "catalog/game_detail.html",
        {
            "title": seo.title,
            "game": game,
            "translation": translation,
            "rating_average": ratings["average"],
            "rating_count": ratings["count"],
            "popularity": popularity(game.pk),
            "localization": localization_coverage(game, active_language_codes),
            "seo": seo,
        },
    )


def _runtime_origin(host_label: str) -> str:
    parsed = urlparse(settings.PORTAL_ORIGIN)
    port = parsed.port
    suffix = "" if port in (None, 443) else f":{port}"
    host = (
        host_label
        if host_label.endswith(f".{settings.GAMES_DOMAIN}")
        else f"{host_label}.{settings.GAMES_DOMAIN}"
    )
    return f"https://{host}{suffix}"


def _session_create_allowed(request: HttpRequest) -> bool:
    """Apply the same subject/IP session limits as the public API."""
    view = SimpleNamespace(throttle_scope="sessions", kwargs={})
    return all(
        throttle.allow_request(request, view)
        for throttle in (SubjectScopedRateThrottle(), GuestIpRateThrottle())
    )


def game_play(request: HttpRequest, slug: str) -> TemplateResponse:
    game = (
        published_games()
        .select_related("current_version")
        .filter(Q(slug=slug) | Q(translations__slug=slug))
        .distinct()
        .first()
    )
    if game is None or game.current_version is None:
        raise Http404("game is not available")
    if not _session_create_allowed(request):
        response = TemplateResponse(
            request,
            "gameplay/play.html",
            {
                "title": game.technical_id,
                "game": game,
                "error_code": "E_RATE_LIMIT",
                "error_message": "Too many sessions",
            },
        )
        response.status_code = 429
        response["Cache-Control"] = "no-store"
        return response

    response = TemplateResponse(
        request,
        "gameplay/play.html",
        {
            "title": game.technical_id,
            "game": game,
            "game_id": game.technical_id,
            "csrf_token": get_token(request),
        },
    )
    response["Cache-Control"] = "no-store"
    binding_nonce = secrets.token_urlsafe(32)
    try:
        session, ticket, _expires_at = create_session(
            request,
            response,
            game_id=game.technical_id,
        )
        cookie = response.cookies.get(COOKIE_NAME)
        if cookie is not None:
            request.COOKIES[COOKIE_NAME] = cookie.value
        context = activate_session(
            request,
            session.id,
            ticket=ticket,
            binding_nonce=binding_nonce,
        )
    except SessionError as exc:
        response.status_code = exc.status
        context_data = response.context_data or {}
        context_data.update(
            {
                "title": game.technical_id,
                "error_code": exc.code,
                "error_message": exc.message,
                "context_json": "{}",
            }
        )
        response.context_data = context_data
        return response

    version = game.current_version
    runtime_url = (
        f"{_runtime_origin(game.host_label)}/v/{version.runtime_hash}/index.html"
        f"#p={quote(settings.PORTAL_ORIGIN, safe='')}&s={context['sessionId']}"
    )
    context_data = response.context_data or {}
    context_data.update(
        {
            "context": context,
            "context_json": json.dumps(context, separators=(",", ":"), ensure_ascii=False),
            "runtime_url": runtime_url,
            "session_id": context["sessionId"],
            "portal_origin": settings.PORTAL_ORIGIN.rstrip("/"),
        }
    )
    response.context_data = context_data
    return response


def game_leaderboard(request: HttpRequest, slug: str) -> TemplateResponse:
    game = published_games().filter(Q(slug=slug) | Q(translations__slug=slug)).distinct().first()
    if game is None or not game.leaderboard_enabled:
        raise Http404("leaderboard is not available")
    translation = localized_translation(game, _language(request))
    payload = get_leaderboard(game, limit=10, user=request.user)
    personal = get_personal_section(game, request.user)
    return TemplateResponse(
        request,
        "catalog/game_leaderboard.html",
        {
            "title": translation.name if translation else game.technical_id,
            "game": game,
            "translation": translation,
            "entries": payload["entries"],
            "my_rank": payload["me"]["rank"] if payload["me"] else None,
            "score_direction": payload["direction"],
            "personal": personal,
        },
    )


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
            "cards": card_items(games, language_code, get_active_language_codes_safely()),
            "language_code": language_code,
        },
    )
