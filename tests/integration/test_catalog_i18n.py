"""Localization of the new catalog rating, popularity and sort UI (§2.15)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.cache import caches
from django.test import Client, override_settings
from django.utils import timezone

from apps.catalog.models import Game, Genre
from apps.gameplay.models import GameDailyStats
from apps.i18n.models import Language, TranslationEntry
from apps.i18n.services import invalidate_language
from apps.ratings.models import GameRatingAggregate

LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "throttle": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}

RU_TRANSLATIONS = {
    "rating_title": "Оценки",
    "rating_out_of": "из 5",
    "rating_votes_one": "{count} голос",
    "rating_votes_other": "{count} голосов",
    "vote_one": "голос",
    "vote_other": "голосов",
    "rating_empty": "Оценок пока нет.",
    "popularity_label": "Популярность (30 дней)",
    "credit_one": "кредит",
    "credit_other": "кредитов",
    "popularity_card_one": "кредит за 30 дней",
    "popularity_card_other": "кредитов за 30 дней",
    "sort_label": "Сортировка",
    "sort_new": "Сначала новые",
    "sort_rating": "По рейтингу",
    "sort_votes": "По голосам",
    "sort_popular": "По популярности",
    "sort_old": "Сначала старые",
}


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    caches["default"].clear()
    caches["throttle"].clear()
    yield
    caches["default"].clear()
    caches["throttle"].clear()


def _game(technical_id: str) -> Game:
    genre, _ = Genre.objects.get_or_create(code=f"genre_{technical_id}")
    return Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=f"slug-{technical_id}",
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
    )


def _seeded_rated_game(technical_id: str = "catalog_i18n_rated") -> Game:
    game = _game(technical_id)
    GameRatingAggregate.objects.create(
        game=game,
        count=2,
        average=Decimal("4.50"),
        wr_score=4.5,
    )
    GameDailyStats.objects.create(
        game=game,
        date=timezone.now().date(),
        unique_sessions=3,
    )
    return game


def _seed_ru_translations() -> Language:
    ru = Language.objects.get(code="ru")
    for key, value in RU_TRANSLATIONS.items():
        TranslationEntry.objects.update_or_create(
            namespace="catalog",
            key=key,
            language=ru,
            defaults={"value": value, "status": TranslationEntry.STATUS_PUBLISHED},
        )
    invalidate_language(ru)
    return ru


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_english_catalog_rating_popularity_and_sort_labels_render() -> None:
    rated = _seeded_rated_game()
    _game("catalog_i18n_unrated")

    listing = Client().get("/en/games/")

    assert listing.status_code == 200
    content = listing.content.decode()
    assert 'data-testid="card-rating-count">2 votes<' in content
    assert "credits in 30 days" in content
    assert "No ratings yet." in content
    assert ">Newest<" in content
    assert ">Rating<" in content
    assert ">Most voted<" in content
    assert ">Popular<" in content
    assert ">Oldest<" in content

    detail = Client().get(f"/en/games/{rated.slug}/")

    assert detail.status_code == 200
    detail_content = detail.content.decode()
    assert "Ratings" in detail_content
    assert "Popularity (30 days)" in detail_content
    assert "/ 5" in detail_content
    assert "votes" in detail_content
    assert "credits" in detail_content


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_non_default_language_renders_published_catalog_translations() -> None:
    rated = _seeded_rated_game()
    _game("catalog_i18n_unrated_ru")
    _seed_ru_translations()

    listing = Client().get("/ru/games/")

    assert listing.status_code == 200
    content = listing.content.decode()
    assert "Сортировка" in content
    assert ">Сначала новые<" in content
    assert ">По рейтингу<" in content
    assert ">По голосам<" in content
    assert ">По популярности<" in content
    assert ">Сначала старые<" in content
    assert "кредитов за 30 дней" in content
    assert "Оценок пока нет." in content
    assert "Most voted" not in content
    assert "No ratings yet." not in content

    detail = Client().get(f"/ru/games/{rated.slug}/")

    assert detail.status_code == 200
    detail_content = detail.content.decode()
    assert "Оценки" in detail_content
    assert "из 5" in detail_content
    assert "Популярность (30 дней)" in detail_content
    assert "голосов" in detail_content
    assert "кредитов" in detail_content
    assert "Popularity (30 days)" not in detail_content


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_missing_catalog_translation_falls_back_to_english() -> None:
    rated = _seeded_rated_game()
    _game("catalog_i18n_unrated_fallback")
    # Change the seeded English value so the assertion proves the rendered text
    # comes from the i18n fallback rather than a hardcoded template string.
    TranslationEntry.objects.filter(
        namespace="catalog",
        key="rating_empty",
        language__code="en",
    ).update(value="Fallback ratings empty.")
    invalidate_language(Language.objects.get(code="en"))

    listing = Client().get("/de/games/")

    assert listing.status_code == 200
    content = listing.content.decode()
    assert "Fallback ratings empty." in content
    assert "Most voted" in content
    assert "credits in 30 days" in content
    assert "No ratings yet." not in content

    detail = Client().get(f"/de/games/{rated.slug}/")

    assert detail.status_code == 200
    detail_content = detail.content.decode()
    assert "Ratings" in detail_content
    assert "Popularity (30 days)" in detail_content
