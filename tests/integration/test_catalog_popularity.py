from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from django.core.cache import caches
from django.test import Client, override_settings
from django.utils import timezone

from apps.catalog.models import Game, Genre
from apps.catalog.services.catalog import (
    SORT_POPULAR,
    card_items,
    filter_games,
    parse_filters,
    published_games,
)
from apps.catalog.services.popularity import (
    POPULARITY_CACHE_TIMEOUT,
    popularity,
    popularity_counts,
    window_bounds,
)
from apps.gameplay.models import GameDailyStats

LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "throttle": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    caches["default"].clear()
    caches["throttle"].clear()
    yield
    caches["default"].clear()
    caches["throttle"].clear()


def _game(
    *,
    technical_id: str,
    slug: str | None = None,
    published_at: datetime | None = None,
    status: str = Game.STATUS_PUBLISHED,
) -> Game:
    genre, _ = Genre.objects.get_or_create(code=f"genre_{technical_id}")
    return Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=slug or f"slug-{technical_id}",
        primary_genre=genre,
        status=status,
        published_at=published_at or timezone.now(),
    )


def _stats(game: Game, day_offset: int, unique_sessions: int) -> GameDailyStats:
    return GameDailyStats.objects.create(
        game=game,
        date=timezone.now().date() - timedelta(days=day_offset),
        unique_sessions=unique_sessions,
    )


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_popularity_sums_trailing_30_utc_days() -> None:
    game = _game(technical_id="popularity_sum")
    _stats(game, day_offset=0, unique_sessions=2)
    _stats(game, day_offset=10, unique_sessions=3)
    _stats(game, day_offset=29, unique_sessions=4)
    _stats(game, day_offset=30, unique_sessions=100)
    start, end = window_bounds()

    assert end == timezone.now().date()
    assert start == end - timedelta(days=29)
    assert popularity(game.pk) == 9

    counts = popularity_counts([game.pk])
    assert counts == {game.pk: 9}


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_popularity_cache_is_reused_then_falls_back_to_db() -> None:
    game = _game(technical_id="popularity_cache")
    stats = _stats(game, day_offset=0, unique_sessions=2)

    assert popularity(game.pk) == 2
    GameDailyStats.objects.filter(pk=stats.pk).update(unique_sessions=9)

    # Cached for 15 minutes: the changed DB row is not observed yet.
    assert popularity(game.pk) == 2
    assert POPULARITY_CACHE_TIMEOUT == 900

    cache_key = f"catalog:popularity30d:{window_bounds()[0].isoformat()}:{game.pk}"
    assert caches["default"].get(cache_key) == 2

    # A cold cache falls back to the aggregate query.
    caches["default"].clear()
    assert popularity(game.pk) == 9


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_parse_filters_and_filter_games_support_popular_sort() -> None:
    now = timezone.now()
    older = _game(technical_id="popular_older", published_at=now - timedelta(days=2))
    newer = _game(technical_id="popular_newer", published_at=now)
    low = _game(technical_id="popular_low", published_at=now + timedelta(days=1))
    stale = _game(technical_id="popular_stale", published_at=now + timedelta(days=2))
    for game, credits in ((older, 5), (newer, 5), (low, 1)):
        _stats(game, day_offset=0, unique_sessions=credits)
    _stats(stale, day_offset=40, unique_sessions=100)

    filters = parse_filters({"sort": "popular"})
    assert filters.sort == SORT_POPULAR

    ordered = list(filter_games(filters).values_list("pk", flat=True))
    assert ordered == [newer.pk, older.pk, low.pk, stale.pk]

    # Without the filter the default newest ordering still applies.
    default_order = list(filter_games(parse_filters({})).values_list("pk", flat=True))
    assert default_order == [stale.pk, low.pk, newer.pk, older.pk]


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_catalog_cards_and_detail_render_popularity_indicator() -> None:
    game = _game(technical_id="popular_render")
    _stats(game, day_offset=0, unique_sessions=7)
    client = Client()

    listing = client.get("/en/games/?sort=popular")
    assert listing.status_code == 200
    content = listing.content.decode()
    assert 'value="popular"' in content
    assert ">Popular<" in content
    assert 'data-testid="card-popularity-count">7<' in content

    detail = client.get(f"/en/games/{game.slug}/")
    assert detail.status_code == 200
    assert 'data-testid="game-popularity">7<' in detail.content.decode()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_card_popularity_lookup_is_batched(django_assert_num_queries) -> None:
    games = [_game(technical_id=f"popular_batch_{index}") for index in range(4)]
    for index, game in enumerate(games, start=1):
        _stats(game, day_offset=0, unique_sessions=index)
    queryset = published_games().filter(pk__in=[game.pk for game in games])

    with django_assert_num_queries(4):
        cards = card_items(queryset, "en")

    assert [card["popularity"] for card in cards] == [1, 2, 3, 4]
