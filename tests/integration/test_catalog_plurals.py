"""CLDR rendering for the legacy catalog plural keys on production seed data.

Regression guard for the QA blocker: Russian ``_one`` forms must exist in the
production seed migration, and a missing CLDR form must fall back to the same
language's ``_other`` (then to English) instead of rendering an empty string.
"""

from __future__ import annotations

import importlib
from decimal import Decimal
from typing import Any

import pytest
from django.apps import apps as django_apps
from django.core.cache import caches
from django.test import Client, override_settings
from django.utils import timezone

from apps.catalog.models import Game, Genre, GenreTranslation
from apps.i18n.models import Language
from apps.i18n.services import invalidate_language, plural_translation
from apps.ratings.models import GameRatingAggregate

LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "throttle": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}
PRODUCTION_SEED = "apps.i18n.migrations.0012_seed_catalog_plural_strings"

RU_EXPECTED = {
    "rating_votes": {
        0: "0 голосов",
        1: "1 голос",
        2: "2 голоса",
        5: "5 голосов",
    },
    "vote": {0: "голосов", 1: "голос", 2: "голоса", 5: "голосов"},
    "credit": {0: "кредитов", 1: "кредит", 2: "кредита", 5: "кредитов"},
    "popularity_card": {
        0: "кредитов за 30 дней",
        1: "кредит за 30 дней",
        2: "кредита за 30 дней",
        5: "кредитов за 30 дней",
    },
}
LEGACY_PLURAL_KEYS = tuple(RU_EXPECTED)


def _clear_caches() -> None:
    caches["default"].clear()
    caches["throttle"].clear()


def _apply_production_seed() -> None:
    """Apply the idempotent production data migration before assertions."""
    module = importlib.import_module(PRODUCTION_SEED)
    module.seed_strings(django_apps, None)
    for code in ("en", "ru"):
        invalidate_language(Language.objects.get(code=code))


@pytest.fixture(autouse=True)
def _fresh_dictionary_cache() -> Any:
    _clear_caches()
    yield
    _clear_caches()


def _languages() -> tuple[Language, Language]:
    return Language.objects.get(code="ru"), Language.objects.get(code="en")


@pytest.mark.django_db
def test_production_seed_contains_russian_one_forms_for_legacy_keys() -> None:
    _apply_production_seed()
    ru, _en = _languages()

    for base_key in LEGACY_PLURAL_KEYS:
        assert ru.translations.filter(
            namespace="catalog",
            key=f"{base_key}_one",
            status="published",
        ).exists(), f"missing RU production seed {base_key}_one"


@pytest.mark.django_db
def test_russian_production_data_renders_cldr_forms_for_zero_one_two_five() -> None:
    _apply_production_seed()
    ru, en = _languages()

    for base_key, expected in RU_EXPECTED.items():
        for count, rendered in expected.items():
            assert (
                plural_translation(
                    "catalog",
                    base_key,
                    count,
                    ru,
                    fallback=en,
                )
                == rendered
            ), f"{base_key} count={count}"


@pytest.mark.django_db
def test_missing_russian_one_form_falls_back_to_russian_other_not_empty() -> None:
    _apply_production_seed()
    ru, en = _languages()
    ru.translations.filter(namespace="catalog", key="rating_votes_one").delete()
    invalidate_language(ru)

    rendered = plural_translation("catalog", "rating_votes", 1, ru, fallback=en)

    assert rendered == "1 голоса"
    assert rendered != ""


@pytest.mark.django_db
def test_missing_russian_forms_fall_back_to_english_plural() -> None:
    _apply_production_seed()
    ru, en = _languages()
    forms = ("one", "few", "many", "other")
    ru.translations.filter(
        namespace="catalog",
        key__in=[f"rating_votes_{form}" for form in forms],
    ).delete()
    invalidate_language(ru)

    assert plural_translation("catalog", "rating_votes", 1, ru, fallback=en) == "1 vote"
    assert plural_translation("catalog", "rating_votes", 2, ru, fallback=en) == "2 votes"
    assert plural_translation("catalog", "rating_votes", 5, ru, fallback=en) == "5 votes"


@pytest.mark.django_db
def test_language_without_seeded_plural_uses_english_fallback() -> None:
    _apply_production_seed()
    _ru, en = _languages()
    de = Language.objects.get(code="de")

    for count, expected in ((0, "0 votes"), (1, "1 vote"), (2, "2 votes"), (5, "5 votes")):
        assert plural_translation("catalog", "rating_votes", count, de, fallback=en) == expected


def _game(technical_id: str, rating_count: int) -> Game:
    genre = Genre.objects.create(code=f"genre_{technical_id}")
    GenreTranslation.objects.create(
        genre=genre,
        language=Language.objects.get(code="ru"),
        name="Головоломка",
        slug=f"genre-{technical_id}-ru",
    )
    game = Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=f"slug-{technical_id}",
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
    )
    GameRatingAggregate.objects.create(
        game=game,
        count=rating_count,
        average=Decimal("4.50"),
        wr_score=4.5,
    )
    return game


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_russian_catalog_renders_production_one_forms() -> None:
    _apply_production_seed()
    game = _game("plural_ru_one", rating_count=1)

    listing = Client().get("/ru/games/")
    detail = Client().get(f"/ru/games/{game.slug}/")

    assert listing.status_code == 200
    assert detail.status_code == 200
    assert 'data-testid="card-rating-count">1 голос<' in listing.content.decode()
    assert 'data-testid="rating-count">1<' in detail.content.decode()
    assert "голос" in detail.content.decode()
    assert "голосов" not in detail.content.decode()
