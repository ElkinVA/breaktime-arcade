"""Game credits rendering on the public detail page (§2.21, App J)."""

from __future__ import annotations

import importlib

import pytest
from django.apps import apps as django_apps
from django.core.cache import caches
from django.test import Client, override_settings
from django.utils import timezone

from apps.catalog.models import Game, Genre
from apps.i18n.models import Language
from apps.i18n.services import invalidate_language

LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "throttle": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}
PRODUCTION_SEED = "apps.i18n.migrations.0014_seed_game_credits_strings"

CREDITS = [
    {"author": "Ada Artist", "license": "CC0-1.0", "aiGenerated": True},
    {"author": "Bob Composer", "license": "CC-BY-4.0", "aiGenerated": False},
]


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    caches["default"].clear()
    caches["throttle"].clear()
    yield
    caches["default"].clear()
    caches["throttle"].clear()


def _apply_production_seed() -> None:
    """Apply the idempotent production data migration before rendering."""
    module = importlib.import_module(PRODUCTION_SEED)
    module.seed_strings(django_apps, None)
    for code in ("en", "ru"):
        invalidate_language(Language.objects.get(code=code))


def _published_game(technical_id: str, credits: list[dict[str, object]]) -> Game:
    genre, _ = Genre.objects.get_or_create(code="credits_genre")
    return Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=technical_id.replace("_", "-"),
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
        credits=credits,
    )


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_game_detail_renders_credits_for_published_game() -> None:
    _apply_production_seed()
    game = _published_game("credits_game", CREDITS)

    response = Client().get(f"/en/games/{game.slug}/")
    content = response.content.decode()

    assert response.status_code == 200
    assert 'data-testid="game-credits"' in content
    assert ">Credits<" in content
    assert "Ada Artist" in content
    assert "CC0-1.0" in content
    assert "Bob Composer" in content
    assert "CC-BY-4.0" in content
    assert content.count('data-testid="game-credit"') == 2
    # Only the entry with aiGenerated=True gets the AI-generated flag.
    assert content.count('data-testid="game-credit-ai"') == 1
    assert "AI-generated" in content


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_game_detail_omits_credits_block_when_credit_list_is_empty() -> None:
    _apply_production_seed()
    game = _published_game("credits_empty", [])

    response = Client().get(f"/en/games/{game.slug}/")
    content = response.content.decode()

    assert response.status_code == 200
    assert 'data-testid="game-credits"' not in content
    assert ">Credits<" not in content


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_game_detail_credits_use_ru_translation_and_english_fallback() -> None:
    _apply_production_seed()
    game = _published_game("credits_i18n", CREDITS)

    russian = Client().get(f"/ru/games/{game.slug}/").content.decode()
    assert "Авторы и лицензии" in russian
    assert "Сгенерировано ИИ" in russian
    assert "Ada Artist" in russian
    assert ">Credits<" not in russian

    german = Client().get(f"/de/games/{game.slug}/").content.decode()
    assert ">Credits<" in german
    assert "AI-generated" in german
