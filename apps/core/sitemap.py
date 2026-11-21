"""SEO-маршруты портала: sitemap-index, языковые sitemap и robots.txt (§2.19).

Источник активных языков — таблица ``i18n.Language``: тот же реестр, что
используют языковой префикс URL и middleware (§2.15). В sitemap попадают
только опубликованные игры и локализованные слаги языков/жанров.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse

from apps.catalog.models import Game, Genre
from apps.i18n.models import Language

FALLBACK_LANGUAGE_CODE = "en"
SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"
XML_CONTENT_TYPE = "application/xml; charset=utf-8"
ROBOTS_CONTENT_TYPE = "text/plain; charset=utf-8"


def _origin() -> str:
    return settings.PORTAL_ORIGIN.rstrip("/")


def _absolute(path: str) -> str:
    return f"{_origin()}{path}"


def _active_language_codes() -> list[str]:
    """Активные языки читаются напрямую из БД — единый источник §2.15."""
    return [
        str(code).lower()
        for code in Language.objects.filter(is_active=True)
        .order_by("sort_order", "code")
        .values_list("code", flat=True)
    ]


def _game_location(game: Game, language_code: str) -> str:
    slugs = {
        translation.language.code.lower(): translation.slug
        for translation in game.translations.all()
    }
    slug = slugs.get(language_code) or slugs.get(FALLBACK_LANGUAGE_CODE) or game.slug
    return _absolute(f"/{language_code}/games/{slug}/")


def _genre_location(genre: Genre, language_code: str) -> str:
    slugs = {
        translation.language.code.lower(): translation.slug
        for translation in genre.translations.all()
    }
    slug = slugs.get(language_code) or slugs.get(FALLBACK_LANGUAGE_CODE) or genre.code
    return _absolute(f"/{language_code}/genres/{slug}/")


def sitemap_index(request: HttpRequest) -> HttpResponse:
    """sitemap-index: по одной карте на каждый активный язык из БД."""
    entries = "".join(
        f"<sitemap><loc>{escape(_absolute(f'/{code}/sitemap.xml'))}</loc></sitemap>"
        for code in _active_language_codes()
    )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<sitemapindex xmlns="{SITEMAP_NAMESPACE}">{entries}</sitemapindex>'
    )
    return HttpResponse(body, content_type=XML_CONTENT_TYPE)


def sitemap_language(request: HttpRequest) -> HttpResponse:
    """Языковая карта: главная, каталог, опубликованные игры и страницы жанров."""
    language_code = str(getattr(request, "LANGUAGE_CODE", settings.LANGUAGE_CODE)).lower()
    if language_code not in _active_language_codes():
        raise Http404("sitemap language is not active")

    locations = [
        _absolute(f"/{language_code}/"),
        _absolute(f"/{language_code}/games/"),
    ]
    games = (
        Game.objects.filter(status=Game.STATUS_PUBLISHED)
        .prefetch_related("translations__language")
        .order_by("id")
    )
    locations.extend(_game_location(game, language_code) for game in games)

    genres = Genre.objects.prefetch_related("translations__language").order_by("sort_order", "code")
    locations.extend(_genre_location(genre, language_code) for genre in genres)

    entries = "".join(f"<url><loc>{escape(location)}</loc></url>" for location in locations)
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="{SITEMAP_NAMESPACE}">{entries}</urlset>'
    )
    return HttpResponse(body, content_type=XML_CONTENT_TYPE)


def robots_txt(request: HttpRequest) -> HttpResponse:
    """robots.txt закрывает кабинет, CRM и игровые URL; ссылается на sitemap-index."""
    lines = [
        "User-agent: *",
        "Disallow: /account/",
        "Disallow: /*/account/",
        "Disallow: /crm/",
        "Disallow: /*/games/*/play/",
        f"Sitemap: {_absolute('/sitemap.xml')}",
        "",
    ]
    return HttpResponse("\n".join(lines), content_type=ROBOTS_CONTENT_TYPE)
