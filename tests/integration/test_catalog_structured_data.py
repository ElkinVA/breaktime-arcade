"""schema.org VideoGame/Game and BreadcrumbList JSON-LD (§2.19)."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from typing import Any

import pytest
from django.conf import settings
from django.core.cache import caches
from django.test import Client
from django.utils import timezone

from apps.catalog.models import Game, GameTranslation, Genre, GenreTranslation
from apps.i18n.models import Language, TranslationEntry
from apps.i18n.services import invalidate_language
from apps.i18n.services.language_registry import invalidate_language_cache

JSON_LD_RE = re.compile(
    r'<script type="application/ld\+json"[^>]*>(.*?)</script>',
    re.DOTALL,
)
RU_CATALOG_TITLE = "Каталог игр"
EN_GAME_NAME = "Alpha EN"
RU_GAME_NAME = "Альфа RU"
RU_GENRE_NAME = "Головоломка"
EN_DESCRIPTION = "Short description EN"
RU_DESCRIPTION = "Короткое описание RU"


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


def _seed_ru_catalog_title() -> None:
    ru = Language.objects.get(code="ru")
    TranslationEntry.objects.update_or_create(
        namespace="catalog",
        key="title",
        language=ru,
        defaults={
            "value": RU_CATALOG_TITLE,
            "status": TranslationEntry.STATUS_PUBLISHED,
        },
    )
    invalidate_language(ru)


def _genre() -> Genre:
    genre = Genre.objects.create(code="puzzle")
    for code, name in (("en", "Puzzle"), ("ru", RU_GENRE_NAME)):
        GenreTranslation.objects.create(
            genre=genre,
            language=Language.objects.get(code=code),
            name=name,
            slug=f"puzzle-{code}",
        )
    return genre


def _game(name: str = "alpha", technical_id: str = "structured_game") -> Game:
    game = Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=f"{name}-game",
        primary_genre=_genre(),
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
    )
    GameTranslation.objects.create(
        game=game,
        language=Language.objects.get(code="en"),
        name=EN_GAME_NAME,
        slug=f"{name}-en",
        short_description=EN_DESCRIPTION,
        description="Long EN",
    )
    GameTranslation.objects.create(
        game=game,
        language=Language.objects.get(code="ru"),
        name=RU_GAME_NAME,
        slug=f"{name}-ru",
        short_description=RU_DESCRIPTION,
        description="Long RU",
    )
    return game


def _blocks(body: str) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for match in JSON_LD_RE.finditer(body):
        raw = match.group(1)
        assert "</script" not in raw.lower()
        parsed.append(json.loads(raw))
    return parsed


def _types(node: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        value = node.get("@type")
        if isinstance(value, str):
            found.add(value)
        elif isinstance(value, list):
            found.update(str(item) for item in value)
        for child in node.values():
            found.update(_types(child))
    elif isinstance(node, list):
        for child in node:
            found.update(_types(child))
    return found


def _block_of_type(blocks: Iterable[dict[str, Any]], type_name: str) -> dict[str, Any]:
    matches = [block for block in blocks if type_name in _types(block)]
    assert len(matches) == 1, f"expected exactly one {type_name} block"
    return matches[0]


@pytest.mark.django_db
def test_catalog_list_emits_localized_item_list_and_breadcrumb() -> None:
    _activate("en", "ru")
    _seed_ru_catalog_title()
    _game()

    body = Client().get("/ru/games/").content.decode()
    blocks = _blocks(body)
    types = _types(blocks)

    assert "BreadcrumbList" in types
    assert "ItemList" in types
    assert {"VideoGame", "Game"} <= types

    breadcrumbs = _block_of_type(blocks, "BreadcrumbList")
    crumb_items = breadcrumbs["itemListElement"]
    assert [item["position"] for item in crumb_items] == [1, 2]
    assert crumb_items[0]["name"] == "Breaktime Arcade"
    assert crumb_items[0]["item"] == f"{_origin()}/ru/"
    assert crumb_items[1]["name"] == RU_CATALOG_TITLE
    assert crumb_items[1]["item"] == f"{_origin()}/ru/games/"

    item_list = _block_of_type(blocks, "ItemList")
    entries = item_list["itemListElement"]
    assert len(entries) == 1
    game_data = entries[0]["item"]
    assert game_data["@context"] == "https://schema.org"
    assert {"VideoGame", "Game"} <= set(game_data["@type"])
    assert game_data["name"] == RU_GAME_NAME
    assert game_data["description"] == RU_DESCRIPTION
    assert game_data["inLanguage"] == "ru"
    assert game_data["url"] == f"{_origin()}/ru/games/alpha-ru/"
    assert game_data["genre"] == RU_GENRE_NAME
    assert game_data["publisher"]["name"] == "Breaktime Arcade"


@pytest.mark.django_db
def test_game_detail_emits_localized_video_game_and_breadcrumb() -> None:
    _activate("en", "ru")
    _seed_ru_catalog_title()
    _game()

    body = Client().get("/ru/games/alpha-ru/").content.decode()
    blocks = _blocks(body)
    types = _types(blocks)

    assert "BreadcrumbList" in types
    assert {"VideoGame", "Game"} <= types

    game_data = _block_of_type(blocks, "VideoGame")
    assert {"VideoGame", "Game"} <= set(game_data["@type"])
    assert game_data["name"] == RU_GAME_NAME
    assert game_data["description"] == RU_DESCRIPTION
    assert game_data["inLanguage"] == "ru"
    assert game_data["url"] == f"{_origin()}/ru/games/alpha-ru/"
    assert game_data["genre"] == RU_GENRE_NAME
    assert game_data["datePublished"]

    breadcrumbs = _block_of_type(blocks, "BreadcrumbList")
    crumb_items = breadcrumbs["itemListElement"]
    assert [item["position"] for item in crumb_items] == [1, 2, 3]
    assert [item["name"] for item in crumb_items] == [
        "Breaktime Arcade",
        RU_CATALOG_TITLE,
        RU_GAME_NAME,
    ]
    assert crumb_items[2]["item"] == f"{_origin()}/ru/games/alpha-ru/"


@pytest.mark.django_db
def test_game_detail_json_ld_is_safe_against_script_injection() -> None:
    _activate("en")
    game = _game(technical_id="structured_escape")
    malicious = '</script><script>alert("x")</script>'
    GameTranslation.objects.filter(game=game, language__code="en").update(
        name=malicious,
        short_description=malicious,
    )

    body = Client().get("/en/games/alpha-en/").content.decode()
    raw_blocks = JSON_LD_RE.findall(body)
    assert raw_blocks
    assert all("</script" not in raw.lower() for raw in raw_blocks)
    assert "\\u003c" in raw_blocks[0]

    game_data = _block_of_type(_blocks(body), "VideoGame")
    assert game_data["name"] == malicious
    assert game_data["description"] == malicious


@pytest.mark.django_db
def test_empty_catalog_emits_breadcrumb_without_item_list() -> None:
    _activate("en")

    body = Client().get("/en/games/").content.decode()
    blocks = _blocks(body)

    assert "BreadcrumbList" in _types(blocks)
    assert "ItemList" not in _types(blocks)
