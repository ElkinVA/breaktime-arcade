"""Catalog rating/votes sorts and Bayesian WR (§2.8)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.conf import settings
from django.core.cache import caches
from django.test import Client, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Game, Genre
from apps.catalog.services.catalog import (
    SORT_RATING,
    SORT_VOTES,
    filter_games,
    parse_filters,
)
from apps.ratings.models import GameRatingAggregate, GameRatingVote
from apps.ratings.services.aggregates import recalculate, weighted_rating

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


def _user(login: str) -> User:
    return User.objects.create_user(login=login, password="correct horse battery staple")


def _aggregate(
    game: Game, *, wr_score: float, count: int, average: Decimal = Decimal("4.00")
) -> GameRatingAggregate:
    return GameRatingAggregate.objects.create(
        game=game,
        wr_score=wr_score,
        count=count,
        average=average,
    )


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_recalculate_writes_bayesian_wr_score() -> None:
    game = _game("wr_math")
    first = _user("wr_math_one")
    second = _user("wr_math_two")
    GameRatingVote.objects.create(game=game, user=first, value=5, changed_at=timezone.now())
    GameRatingVote.objects.create(game=game, user=second, value=4, changed_at=timezone.now())

    aggregate = recalculate(game)

    expected = (2 / 22) * 4.5 + (20 / 22) * 3.5
    assert settings.RATING_WR_M == 20
    assert settings.RATING_WR_C == 3.5
    assert aggregate.count == 2
    assert aggregate.average == Decimal("4.50")
    assert aggregate.wr_score == pytest.approx(expected)
    assert weighted_rating(Decimal("4.5"), 2) == pytest.approx(expected)


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES, RATING_WR_M=5, RATING_WR_C=1.0)
def test_recalculate_honours_configurable_wr_settings() -> None:
    game = _game("wr_configurable")
    voter = _user("wr_configurable_voter")
    GameRatingVote.objects.create(game=game, user=voter, value=5, changed_at=timezone.now())

    aggregate = recalculate(game)

    expected = (1 / 6) * 5 + (5 / 6) * 1.0
    assert aggregate.wr_score == pytest.approx(expected)


def _sort_games() -> dict[str, Game]:
    # Creation order defines UUIDv7 id order (ascending), used as final tie-break.
    games = {name: _game(f"sort_{name}") for name in ("a", "b", "c", "d")}
    _aggregate(games["a"], wr_score=4.0, count=2)
    _aggregate(games["b"], wr_score=4.0, count=5)
    _aggregate(games["c"], wr_score=3.0, count=100)
    _aggregate(games["d"], wr_score=4.0, count=5)
    return games


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_filter_games_sort_rating_orders_by_wr_then_count_then_id() -> None:
    games = _sort_games()

    ordered = list(filter_games(parse_filters({"sort": "rating"})).values_list("pk", flat=True))

    assert parse_filters({"sort": "rating"}).sort == SORT_RATING
    assert ordered == [games["b"].pk, games["d"].pk, games["a"].pk, games["c"].pk]


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_filter_games_sort_votes_orders_by_count_then_wr_then_id() -> None:
    games = _sort_games()

    ordered = list(filter_games(parse_filters({"sort": "votes"})).values_list("pk", flat=True))

    assert parse_filters({"sort": "votes"}).sort == SORT_VOTES
    assert ordered == [games["c"].pk, games["b"].pk, games["d"].pk, games["a"].pk]


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_catalog_sort_select_offers_rating_and_votes() -> None:
    response = Client().get("/en/games/?sort=rating")

    assert response.status_code == 200
    content = response.content.decode()
    assert 'value="rating" selected' in content
    assert ">Rating<" in content
    assert 'value="votes"' in content
    assert ">Most voted<" in content


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_cards_and_detail_show_actual_average_and_count_not_wr() -> None:
    game = _game("wr_display")
    first = _user("wr_display_one")
    second = _user("wr_display_two")
    GameRatingVote.objects.create(game=game, user=first, value=5, changed_at=timezone.now())
    GameRatingVote.objects.create(game=game, user=second, value=4, changed_at=timezone.now())
    aggregate = recalculate(game)
    assert aggregate.wr_score != pytest.approx(float(aggregate.average))

    listing = Client().get("/en/games/?sort=rating")

    assert listing.status_code == 200
    listing_content = listing.content.decode()
    assert 'data-testid="card-rating-average">4.50<' in listing_content
    assert 'data-testid="card-rating-count">2 votes<' in listing_content
    assert "3.59" not in listing_content

    detail = Client().get(f"/en/games/{game.slug}/")

    assert detail.status_code == 200
    detail_content = detail.content.decode()
    assert 'data-testid="rating-average">4.50<' in detail_content
    assert 'data-testid="rating-count">2<' in detail_content
    assert "3.59" not in detail_content
