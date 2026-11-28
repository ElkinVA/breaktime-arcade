"""Публичные представления каталога: только опубликованные игры."""

from __future__ import annotations

from urllib.parse import quote, urlparse

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import (
    Http404,
    HttpRequest,
    HttpResponsePermanentRedirect,
)
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.utils.translation import get_language

from apps.catalog.models import GameAsset, Genre, GenreTranslation
from apps.catalog.services.catalog import (
    card_items,
    filter_games,
    game_taxonomy,
    genre_options,
    localized_translation,
    parse_filters,
    popular_games,
    published_games,
    search_fallback_required,
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
from apps.catalog.services.seo import catalog_seo, game_seo, genre_seo, home_seo
from apps.catalog.services.slugs import canonical_game_path, resolve_old_slug
from apps.i18n.services.language_registry import get_active_language_codes_safely
from apps.leaderboards.services.queries import get_leaderboard, get_personal_section
from apps.ratings.services.aggregates import summary as rating_summary
from apps.ratings.services.voting import vote_eligibility

LEADERBOARD_PAGE_SIZE = 10


def _language(request: HttpRequest) -> str:
    return str(getattr(request, "LANGUAGE_CODE", "en"))


def _asset_alt(asset: GameAsset | None, language: str) -> str:
    if asset is None or not isinstance(asset.alt, dict):
        return ""
    return str(asset.alt.get(language) or asset.alt.get("en") or "")


def _page_number(request: HttpRequest) -> int:
    """Blank/non-integer/non-positive input maps to the first page.

    ``Paginator.get_page`` clamps values beyond the last page itself.
    """
    raw = request.GET.get("page")
    if raw is None:
        return 1
    value = raw.strip()
    if not value:
        return 1
    try:
        number = int(value)
    except ValueError:
        return 1
    return number if number >= 1 else 1


def canonical_url_for_home(language_code: str) -> str:
    """Canonical home URL without relying on the request host/path."""
    return f"{settings.PORTAL_ORIGIN.rstrip('/')}/{language_code}/"


def home(request: HttpRequest) -> TemplateResponse:
    language_code = _language(request)
    active_language_codes = get_active_language_codes_safely()
    canonical_url = canonical_url_for_home(language_code)
    seo = home_seo(
        language_code,
        active_language_codes,
        canonical_url=canonical_url,
    )
    return TemplateResponse(
        request,
        "catalog/home.html",
        {
            "title": seo.title,
            "seo": seo,
            "genres": genre_options(language_code),
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
    cards = card_items(page_obj.object_list, language_code, active_language_codes)
    search_fallback = search_fallback_required(filters, page_obj.paginator.count)
    search_fallback_cards = (
        card_items(popular_games(filters=filters), language_code, active_language_codes)
        if search_fallback
        else []
    )
    if search_fallback and not search_fallback_cards:
        # Keep the suggestive block useful even when no popular game matches
        # the other active filters.
        search_fallback_cards = card_items(popular_games(), language_code, active_language_codes)
    # Structured data must describe the games actually visible on the page,
    # including the popular suggestions shown for an empty search.
    structured_cards = cards or (search_fallback_cards if search_fallback else [])
    genres = genre_options(language_code)
    seo = catalog_seo(
        language_code,
        active_language_codes,
        canonical_url=page_canonical_url,
        noindex=robots_noindex,
        cards=structured_cards,
        genre_names={genre["code"]: genre["name"] for genre in genres},
    )
    context = {
        "title": seo.title,
        "games": page_obj.object_list,
        "cards": cards,
        "search_fallback": search_fallback,
        "search_fallback_cards": search_fallback_cards,
        "filters": filters,
        "genres": genres,
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


def game_detail(
    request: HttpRequest, slug: str
) -> TemplateResponse | HttpResponsePermanentRedirect:
    language = _language(request)
    game = (
        published_games()
        .prefetch_related(
            "primary_genre__translations__language",
            "additional_genres__translations__language",
            "tags__translations__language",
        )
        .filter(Q(slug=slug) | Q(translations__slug=slug))
        .distinct()
        .first()
    )
    if game is None:
        # A slug recorded before a rename: permanent redirect to the current
        # canonical URL for the requested language (§2.4.1/§2.6).
        previous_game = resolve_old_slug(slug, language)
        if previous_game is not None:
            return HttpResponsePermanentRedirect(canonical_game_path(previous_game, language))
        raise Http404("game not found")
    translation = localized_translation(game, language)
    active_language_codes = get_active_language_codes_safely()
    ratings = rating_summary(game, request.user)
    seo = game_seo(game, translation, language, active_language_codes)
    fallback_alt = translation.name if translation is not None else game.technical_id
    cover = game.assets.filter(type=GameAsset.TYPE_COVER).order_by("sort_order").first()
    screenshots = list(
        game.assets.filter(type=GameAsset.TYPE_SCREENSHOT).order_by("sort_order")[:3]
    )
    return TemplateResponse(
        request,
        "catalog/game_detail.html",
        {
            "title": seo.title,
            "game": game,
            "translation": translation,
            "cover": cover,
            "cover_alt": _asset_alt(cover, language) or fallback_alt,
            "screenshots": [
                {"asset": asset, "alt": _asset_alt(asset, language) or fallback_alt}
                for asset in screenshots
            ],
            "rating_average": ratings["average"],
            "rating_count": ratings["count"],
            "rating_my_vote": ratings["my_vote"],
            "rating_eligibility": vote_eligibility(game, request.user),
            "rating_values": [1, 2, 3, 4, 5],
            "popularity": popularity(game.pk),
            "localization": localization_coverage(game, active_language_codes),
            "taxonomy": game_taxonomy(game, language),
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


def game_play(request: HttpRequest, slug: str) -> TemplateResponse:
    """Render the player shell; session creation is a separate POST API call."""
    game = (
        published_games()
        .select_related("current_version")
        .filter(Q(slug=slug) | Q(translations__slug=slug))
        .distinct()
        .first()
    )
    if game is None or game.current_version is None:
        raise Http404("game is not available")
    version = game.current_version
    runtime_url = (
        f"{_runtime_origin(game.host_label)}/v/{version.runtime_hash}/index.html"
        f"#p={quote(settings.PORTAL_ORIGIN, safe='')}"
    )
    response = TemplateResponse(
        request,
        "gameplay/play.html",
        {
            "title": game.technical_id,
            "game": game,
            "game_id": game.technical_id,
            "csrf_token": get_token(request),
            "runtime_url": runtime_url,
            "portal_origin": settings.PORTAL_ORIGIN.rstrip("/"),
        },
    )
    response["Cache-Control"] = "no-store"
    # The session API is unprefixed; without this cookie LocaleMiddleware
    # would fall back to Accept-Language and the game context would disagree
    # with the /<language>/ page (BA-PLAT language invariant).
    language = get_language() or game.default_language
    if language in dict(settings.LANGUAGES):
        response.set_cookie(
            settings.LANGUAGE_COOKIE_NAME,
            language,
            max_age=settings.LANGUAGE_COOKIE_AGE,
            domain=settings.LANGUAGE_COOKIE_DOMAIN,
            path="/",
            secure=request.is_secure(),
            samesite=settings.LANGUAGE_COOKIE_SAMESITE,
        )
    return response


def game_leaderboard(request: HttpRequest, slug: str) -> TemplateResponse:
    game = published_games().filter(Q(slug=slug) | Q(translations__slug=slug)).distinct().first()
    if game is None or not game.leaderboard_enabled:
        raise Http404("leaderboard is not available")
    translation = localized_translation(game, _language(request))
    payload = get_leaderboard(game, limit=100, user=request.user)
    my_entry = payload["me"]
    entries = [
        {
            **entry,
            "is_me": my_entry is not None and entry["rank"] == my_entry["rank"],
        }
        for entry in payload["entries"]
    ]
    page_obj = Paginator(entries, LEADERBOARD_PAGE_SIZE).get_page(_page_number(request))
    page_entries = list(page_obj.object_list)
    my_entry_on_page = any(entry["is_me"] for entry in page_entries)
    personal = get_personal_section(game, request.user)
    return TemplateResponse(
        request,
        "catalog/game_leaderboard.html",
        {
            "title": translation.name if translation else game.technical_id,
            "game": game,
            "translation": translation,
            "entries": entries,
            "page_obj": page_obj,
            "page_entries": page_entries,
            "my_entry": my_entry,
            "my_entry_on_page": my_entry_on_page,
            "my_rank": my_entry["rank"] if my_entry else None,
            "score_direction": payload["direction"],
            "personal": personal,
        },
    )


def genre_detail(
    request: HttpRequest, slug: str
) -> TemplateResponse | HttpResponsePermanentRedirect:
    language_code = _language(request)
    # The language switcher swaps only the URL prefix. Resolve a slug from any
    # language first, then redirect to the current language's canonical slug
    # instead of returning 404 or serving a canonical/hreflang mismatch.
    found = GenreTranslation.objects.filter(slug=slug).select_related("genre").first()
    genre = found.genre if found is not None else get_object_or_404(Genre, code=slug)
    translation = (
        GenreTranslation.objects.filter(genre=genre, language__code=language_code)
        .select_related("genre")
        .first()
    )
    if translation is None:
        translation = (
            GenreTranslation.objects.filter(genre=genre, language__code="en")
            .select_related("genre")
            .first()
        )
    if translation is None:
        translation = found
    if found is not None and translation is not None and translation.slug != slug:
        target = f"/{language_code}/genres/{translation.slug}/"
        query = request.META.get("QUERY_STRING", "")
        if query:
            target = f"{target}?{query}"
        return HttpResponsePermanentRedirect(target)
    params = request.GET
    filters = parse_filters(params)
    games = (
        filter_games(filters, language_code)
        .filter(Q(primary_genre=genre) | Q(additional_genres=genre))
        .distinct()
    )
    page_obj = paginate_games(games, params)
    active_language_codes = get_active_language_codes_safely()
    page_canonical_url = canonical_url(request, params, page_obj.number)
    robots_noindex = should_noindex(page_obj.number)
    seo = genre_seo(
        genre,
        translation,
        language_code,
        active_language_codes,
        canonical_url=page_canonical_url,
        noindex=robots_noindex,
    )
    genre_name = translation.name if translation else genre.code
    return TemplateResponse(
        request,
        "catalog/genre_list.html",
        {
            "title": seo.title,
            "seo": seo,
            "genre": genre,
            "genre_name": genre_name,
            "genre_description": translation.description if translation else "",
            "genre_image": genre.image if genre.image else None,
            "genre_image_alt": genre_name,
            "genre_game_count": page_obj.paginator.count,
            "filters": filters,
            "games": page_obj.object_list,
            "cards": card_items(page_obj.object_list, language_code, active_language_codes),
            "language_code": language_code,
            "page_obj": page_obj,
            "pagination_query": pagination_query(params),
            "canonical_url": page_canonical_url,
            "robots_noindex": robots_noindex,
        },
    )
