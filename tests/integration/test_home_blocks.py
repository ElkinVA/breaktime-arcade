"""Home page Popular and Top-rated blocks (§2.6, §2.8, §2.9)."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.core.cache import caches
from django.test import Client, override_settings
from django.utils import timezone

from apps.catalog.models import Game, Genre
from apps.gameplay.models import GameDailyStats
from apps.ratings.models import GameRatingAggregate

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
    technical_id: str,
    *,
    published_at: datetime | None = None,
    status: str = Game.STATUS_PUBLISHED,
) -> Game:
    genre, _ = Genre.objects.get_or_create(code=f"genre_{technical_id}")
    return Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=f"slug-{technical_id}",
        primary_genre=genre,
        status=status,
        published_at=published_at or timezone.now(),
    )


def _stats(game: Game, unique_sessions: int, day_offset: int = 0) -> GameDailyStats:
    return GameDailyStats.objects.create(
        game=game,
        date=timezone.now().date() - timedelta(days=day_offset),
        unique_sessions=unique_sessions,
    )


def _aggregate(
    game: Game,
    *,
    wr_score: float,
    count: int,
    average: Decimal = Decimal("4.00"),
) -> GameRatingAggregate:
    return GameRatingAggregate.objects.create(
        game=game,
        wr_score=wr_score,
        count=count,
        average=average,
    )


def _section(content: str, start_marker: str, end_marker: str) -> str:
    start = content.index(start_marker)
    return content[start : content.index(end_marker, start)]


def _order(block: str, games: list[Game]) -> list[int]:
    return [block.index(f"/en/games/{game.slug}/") for game in games]


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_home_popular_block_renders_top_30d_games_in_popularity_order() -> None:
    now = timezone.now()
    low = _game("home_popular_low", published_at=now - timedelta(days=1))
    high = _game("home_popular_high", published_at=now - timedelta(days=2))
    middle = _game("home_popular_middle", published_at=now - timedelta(days=3))
    idle = _game("home_popular_idle", published_at=now - timedelta(days=4))
    _stats(low, 2)
    _stats(middle, 7)
    _stats(high, 9)

    response = Client().get("/en/")

    assert response.status_code == 200
    content = response.content.decode()
    block = _section(content, 'data-testid="home-popular"', 'data-testid="home-rated"')
    positions = _order(block, [high, middle, low])
    assert positions == sorted(positions)
    assert idle.slug not in block
    assert 'data-testid="card-popularity-count">9<' in block


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_home_rated_block_applies_minimum_vote_threshold_and_wr_order() -> None:
    best = _game("home_rated_best")
    runner_up = _game("home_rated_runner_up")
    too_few_votes = _game("home_rated_too_few_votes")
    _aggregate(best, wr_score=4.7, count=25, average=Decimal("4.80"))
    _aggregate(runner_up, wr_score=4.1, count=20, average=Decimal("4.10"))
    _aggregate(too_few_votes, wr_score=4.9, count=19, average=Decimal("4.90"))

    response = Client().get("/en/")

    assert response.status_code == 200
    content = response.content.decode()
    block = _section(content, 'data-testid="home-rated"', 'data-testid="home-new"')
    positions = _order(block, [best, runner_up])
    assert positions == sorted(positions)
    assert too_few_votes.slug not in block
    assert 'data-testid="card-rating-count">25 votes<' in block
    assert 'data-testid="card-rating-average">4.80<' in block


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_home_blocks_show_empty_states_when_no_game_qualifies() -> None:
    game = _game("home_blocks_empty")
    # Published game in the catalog, but no 30-day credit and below the vote floor.
    _aggregate(game, wr_score=4.9, count=19, average=Decimal("4.90"))

    response = Client().get("/en/")

    assert response.status_code == 200
    content = response.content.decode()
    assert 'data-testid="home-popular-empty"' in content
    assert 'data-testid="home-rated-empty"' in content
    assert "No popular games yet." in content
    assert "No highly rated games yet." in content
    # The static hints are gone.
    assert "What everyone is playing this week." not in content
    assert "Games with the highest player ratings." not in content
    # The catalog is not empty: the game still appears in the New block.
    assert f"/en/games/{game.slug}/" in content
