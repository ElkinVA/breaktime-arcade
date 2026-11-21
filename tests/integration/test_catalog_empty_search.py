"""Empty search suggests popular games with a localized message (§2.8)."""

from __future__ import annotations

from datetime import datetime

import pytest
from django.core.cache import caches
from django.test import Client, override_settings
from django.utils import timezone

from apps.catalog.models import Game, GameTranslation, Genre
from apps.gameplay.models import GameDailyStats
from apps.i18n.models import Language, TranslationEntry
from apps.i18n.services import invalidate_language

LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "throttle": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}

NO_RESULTS_TEXT = "No games match your search. Try one of the popular games below."


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    caches["default"].clear()
    caches["throttle"].clear()
    yield
    caches["default"].clear()
    caches["throttle"].clear()


def _genre(code: str) -> Genre:
    genre, _ = Genre.objects.get_or_create(code=code)
    return genre


def _game(
    technical_id: str,
    genre: Genre,
    name: str,
    *,
    published_at: datetime | None = None,
) -> Game:
    game = Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=technical_id.replace("_", "-"),
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED,
        published_at=published_at or timezone.now(),
        mobile_support=True,
        estimated_play_minutes=5,
    )
    GameTranslation.objects.create(
        game=game,
        language=Language.objects.get(code="en"),
        name=name,
        slug=f"{technical_id.replace('_', '-')}-en",
        short_description=f"Short description for {name}",
        description=f"Full description for {name}",
    )
    return game


def _credits(game: Game, unique_sessions: int) -> GameDailyStats:
    return GameDailyStats.objects.create(
        game=game,
        date=timezone.now().date(),
        unique_sessions=unique_sessions,
    )


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_empty_search_renders_popular_games_with_no_results_message() -> None:
    genre = _genre("puzzle")
    popular = _game("empty_popular", genre, "Popular Gem")
    other = _game("empty_other", genre, "Quiet Game")
    _credits(popular, 7)

    response = Client().get("/en/games/", {"q": "zzzz"})

    assert response.status_code == 200
    body = response.content.decode()
    assert 'data-testid="catalog-search-fallback"' in body
    assert 'data-testid="catalog-search-empty"' in body
    assert NO_RESULTS_TEXT in body
    assert 'data-testid="catalog-search-popular-title"' in body
    assert "Popular games" in body
    assert f"/en/games/{popular.slug}/" in body
    # The fallback is a suggestion block, not the unfiltered catalog grid.
    assert f"/en/games/{other.slug}/" not in body

    # HTMX search swaps only the results fragment, which must carry the same
    # fallback markup.
    partial = Client().get("/en/games/", {"q": "zzzz"}, HTTP_HX_REQUEST="true")
    partial_body = partial.content.decode()
    assert partial.status_code == 200
    assert "<html" not in partial_body
    assert 'data-testid="catalog-search-fallback"' in partial_body
    assert NO_RESULTS_TEXT in partial_body


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_non_empty_search_does_not_show_the_fallback() -> None:
    genre = _genre("logic")
    match = _game("search_match", genre, "Findable Word")
    _credits(match, 3)

    response = Client().get("/en/games/", {"q": "Findable"})

    assert response.status_code == 200
    body = response.content.decode()
    assert f"/en/games/{match.slug}/" in body
    assert 'data-testid="catalog-search-fallback"' not in body
    assert 'data-testid="catalog-search-empty"' not in body
    assert NO_RESULTS_TEXT not in body


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_fallback_uses_the_fully_filtered_result_set() -> None:
    puzzle = _genre("puzzle_filter")
    arcade = _genre("arcade_filter")
    match = _game("filtered_match", puzzle, "Findable Word")
    popular = _game("filtered_popular", puzzle, "Popular Gem")
    _credits(match, 1)
    _credits(popular, 5)

    client = Client()
    matching = client.get(
        "/en/games/",
        {"q": "Findable", "genre": puzzle.code},
    )
    excluded_by_filter = client.get(
        "/en/games/",
        {"q": "Findable", "genre": arcade.code},
    )

    matching_body = matching.content.decode()
    assert f"/en/games/{match.slug}/" in matching_body
    assert 'data-testid="catalog-search-fallback"' not in matching_body

    # The search term matches a game, but the active genre filter leaves zero
    # results, so the empty-result fallback still applies.
    excluded_body = excluded_by_filter.content.decode()
    assert 'data-testid="catalog-search-fallback"' in excluded_body
    assert f"/en/games/{popular.slug}/" in excluded_body


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_fallback_suggestions_respect_the_other_active_filters() -> None:
    puzzle = _genre("suggestion_puzzle")
    arcade = _genre("suggestion_arcade")
    puzzle_popular = _game("suggestion_puzzle_popular", puzzle, "Puzzle Popular")
    arcade_popular = _game("suggestion_arcade_popular", arcade, "Arcade Popular")
    _credits(puzzle_popular, 10)
    _credits(arcade_popular, 4)

    response = Client().get("/en/games/", {"q": "zzzz", "genre": arcade.code})

    assert response.status_code == 200
    body = response.content.decode()
    assert 'data-testid="catalog-search-fallback"' in body
    assert f"/en/games/{arcade_popular.slug}/" in body
    assert f"/en/games/{puzzle_popular.slug}/" not in body


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_one_character_search_does_not_trigger_the_fallback() -> None:
    genre = _genre("short_query")
    _game("short_query_game", genre, "Alpha")

    response = Client().get("/en/games/", {"q": "a"})

    assert response.status_code == 200
    assert 'data-testid="catalog-search-fallback"' not in response.content.decode()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_empty_search_message_is_localized() -> None:
    genre = _genre("localized")
    popular = _game("localized_popular", genre, "Popular Gem")
    _credits(popular, 4)
    ru = Language.objects.get(code="ru")
    for key, value in {
        "search_no_results": "Игр по запросу не найдено.",
        "popular_suggestions": "Популярные игры",
    }.items():
        TranslationEntry.objects.update_or_create(
            namespace="catalog",
            key=key,
            language=ru,
            defaults={"value": value, "status": TranslationEntry.STATUS_PUBLISHED},
        )
    invalidate_language(ru)

    response = Client().get("/ru/games/", {"q": "zzzz"})

    assert response.status_code == 200
    body = response.content.decode()
    assert "Игр по запросу не найдено." in body
    assert "Популярные игры" in body
    assert NO_RESULTS_TEXT not in body
    assert f"/ru/games/{popular.slug}/" in body
