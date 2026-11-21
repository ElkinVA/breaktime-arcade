"""Per-language SEO meta, hreflang and social tags for catalog pages (§2.19)."""

from __future__ import annotations

import html
import re
from collections.abc import Iterator

import pytest
from django.conf import settings
from django.core.cache import caches
from django.test import Client
from django.utils import timezone

from apps.catalog.models import Game, GameTranslation, Genre
from apps.i18n.models import Language, TranslationEntry
from apps.i18n.services import invalidate_language
from apps.i18n.services.language_registry import invalidate_language_cache

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.DOTALL)
DESCRIPTION_RE = re.compile(r'<meta name="description" content="([^"]*)">')
CANONICAL_RE = re.compile(r'<link rel="canonical" href="([^"]*)">')
ALTERNATE_RE = re.compile(r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)">')
OG_TITLE_RE = re.compile(r'<meta property="og:title" content="([^"]*)">')
OG_DESCRIPTION_RE = re.compile(r'<meta property="og:description" content="([^"]*)">')
OG_URL_RE = re.compile(r'<meta property="og:url" content="([^"]*)">')
OG_TYPE_RE = re.compile(r'<meta property="og:type" content="([^"]*)">')
OG_LOCALE_RE = re.compile(r'<meta property="og:locale" content="([^"]*)">')
TWITTER_CARD_RE = re.compile(r'<meta name="twitter:card" content="([^"]*)">')
TWITTER_TITLE_RE = re.compile(r'<meta name="twitter:title" content="([^"]*)">')
TWITTER_DESCRIPTION_RE = re.compile(r'<meta name="twitter:description" content="([^"]*)">')

RU_META_DESCRIPTION = "Короткие браузерные игры для быстрого перерыва."
EN_GAME_NAME = "Alpha EN"
RU_GAME_NAME = "Альфа RU"
EN_GAME_DESCRIPTION = "Short description EN"
RU_GAME_DESCRIPTION = "Короткое описание RU"


@pytest.fixture(autouse=True)
def clear_caches() -> Iterator[None]:
    caches["default"].clear()
    caches["throttle"].clear()
    invalidate_language_cache()
    yield
    caches["default"].clear()
    caches["throttle"].clear()
    invalidate_language_cache()


def _activate(*codes: str) -> None:
    Language.objects.exclude(code__in=codes).update(is_active=False)
    Language.objects.filter(code__in=codes).update(is_active=True)
    invalidate_language_cache()


def _origin() -> str:
    return settings.PORTAL_ORIGIN.rstrip("/")


def _genre() -> Genre:
    return Genre.objects.create(code="puzzle")


def _game() -> Game:
    return Game.objects.create(
        technical_id="seo_game",
        host_label="seo-game.games.test",
        slug="seo-game",
        primary_genre=_genre(),
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
    )


def _add_translation(game: Game, code: str, *, name: str, slug: str, description: str) -> None:
    GameTranslation.objects.create(
        game=game,
        language=Language.objects.get(code=code),
        name=name,
        slug=slug,
        short_description=description,
        description=f"Full description {code}",
    )


def _localized_game() -> Game:
    game = _game()
    _add_translation(
        game,
        "en",
        name=EN_GAME_NAME,
        slug="alpha-en",
        description=EN_GAME_DESCRIPTION,
    )
    _add_translation(
        game,
        "ru",
        name=RU_GAME_NAME,
        slug="alpha-ru",
        description=RU_GAME_DESCRIPTION,
    )
    return game


def _seed_ru_catalog_strings() -> None:
    ru = Language.objects.get(code="ru")
    for key, value in {
        "title": "Каталог игр",
        "meta_description": RU_META_DESCRIPTION,
    }.items():
        TranslationEntry.objects.update_or_create(
            namespace="catalog",
            key=key,
            language=ru,
            defaults={"value": value, "status": TranslationEntry.STATUS_PUBLISHED},
        )
    invalidate_language(ru)


def _match(pattern: re.Pattern[str], body: str, label: str) -> str:
    match = pattern.search(body)
    assert match is not None, f"{label} is missing"
    return html.unescape(match.group(1))


def _alternates(body: str) -> dict[str, str]:
    return {code: html.unescape(url) for code, url in ALTERNATE_RE.findall(body)}


@pytest.mark.django_db
def test_game_detail_renders_per_language_title_and_description() -> None:
    _activate("en", "ru")
    _localized_game()
    client = Client()

    english = client.get("/en/games/alpha-en/")
    russian = client.get("/ru/games/alpha-ru/")

    assert english.status_code == 200
    assert russian.status_code == 200

    english_body = english.content.decode()
    russian_body = russian.content.decode()

    assert _match(TITLE_RE, english_body, "title") == f"{EN_GAME_NAME} — Breaktime Arcade"
    assert _match(DESCRIPTION_RE, english_body, "description") == EN_GAME_DESCRIPTION
    assert _match(TITLE_RE, russian_body, "title") == f"{RU_GAME_NAME} — Breaktime Arcade"
    assert _match(DESCRIPTION_RE, russian_body, "description") == RU_GAME_DESCRIPTION


@pytest.mark.django_db
def test_game_detail_emits_hreflang_x_default_og_and_twitter() -> None:
    _activate("en", "ru")
    _localized_game()

    body = Client().get("/en/games/alpha-en/").content.decode()
    origin = _origin()

    assert _alternates(body) == {
        "en": f"{origin}/en/games/alpha-en/",
        "ru": f"{origin}/ru/games/alpha-ru/",
        "x-default": f"{origin}/en/games/alpha-en/",
    }
    assert _match(CANONICAL_RE, body, "canonical") == f"{origin}/en/games/alpha-en/"
    assert _match(OG_TYPE_RE, body, "og:type") == "website"
    assert _match(OG_LOCALE_RE, body, "og:locale") == "en_US"
    assert _match(OG_TITLE_RE, body, "og:title") == EN_GAME_NAME
    assert _match(OG_DESCRIPTION_RE, body, "og:description") == EN_GAME_DESCRIPTION
    assert _match(OG_URL_RE, body, "og:url") == f"{origin}/en/games/alpha-en/"
    assert _match(TWITTER_CARD_RE, body, "twitter:card") == "summary"
    assert _match(TWITTER_TITLE_RE, body, "twitter:title") == EN_GAME_NAME
    assert _match(TWITTER_DESCRIPTION_RE, body, "twitter:description") == EN_GAME_DESCRIPTION


@pytest.mark.django_db
def test_catalog_list_renders_per_language_title_and_description() -> None:
    _activate("en", "ru")
    _seed_ru_catalog_strings()
    client = Client()

    english = client.get("/en/games/")
    russian = client.get("/ru/games/")

    assert english.status_code == 200
    assert russian.status_code == 200

    english_body = english.content.decode()
    russian_body = russian.content.decode()

    assert _match(TITLE_RE, english_body, "title") == "Game catalog — Breaktime Arcade"
    assert _match(TITLE_RE, russian_body, "title") == "Каталог игр — Breaktime Arcade"
    assert "Short browser games for a quick break" in _match(
        DESCRIPTION_RE, english_body, "description"
    )
    assert _match(DESCRIPTION_RE, russian_body, "description") == RU_META_DESCRIPTION


@pytest.mark.django_db
def test_catalog_list_emits_hreflang_x_default_og_and_twitter() -> None:
    _activate("en", "ru")
    _seed_ru_catalog_strings()

    body = Client().get("/ru/games/").content.decode()
    origin = _origin()

    assert _alternates(body) == {
        "en": f"{origin}/en/games/",
        "ru": f"{origin}/ru/games/",
        "x-default": f"{origin}/en/games/",
    }
    assert _match(CANONICAL_RE, body, "canonical") == f"{origin}/ru/games/"
    assert _match(OG_TYPE_RE, body, "og:type") == "website"
    assert _match(OG_LOCALE_RE, body, "og:locale") == "ru_RU"
    assert _match(OG_TITLE_RE, body, "og:title") == "Каталог игр"
    assert _match(OG_DESCRIPTION_RE, body, "og:description") == RU_META_DESCRIPTION
    assert _match(OG_URL_RE, body, "og:url") == f"{origin}/ru/games/"
    assert _match(TWITTER_CARD_RE, body, "twitter:card") == "summary"
    assert _match(TWITTER_TITLE_RE, body, "twitter:title") == "Каталог игр"
    assert _match(TWITTER_DESCRIPTION_RE, body, "twitter:description") == RU_META_DESCRIPTION


@pytest.mark.django_db
def test_translation_text_is_html_escaped_in_meta_tags() -> None:
    _activate("en")
    game = _game()
    malicious_name = '<script>alert("name")</script>'
    malicious_description = '"><img src=x onerror=alert(1)>'
    _add_translation(
        game,
        "en",
        name=malicious_name,
        slug="escaped-game",
        description=malicious_description,
    )

    body = Client().get("/en/games/escaped-game/").content.decode()

    assert "<script>alert" not in body
    assert "<img src=x" not in body
    assert "&lt;script&gt;" in body
    assert "&lt;img" in body
    assert "&quot;&gt;" in body
    assert _match(OG_TITLE_RE, body, "og:title") == malicious_name
    assert _match(OG_DESCRIPTION_RE, body, "og:description") == malicious_description
