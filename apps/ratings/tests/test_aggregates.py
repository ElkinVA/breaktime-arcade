"""Bounded query plan and output of rating aggregate computation (§2.9)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Game, Genre
from apps.ratings.models import GameRatingVote
from apps.ratings.services.aggregates import _computed_values

ZERO_DISTRIBUTION = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}


def _game(technical_id: str) -> Game:
    genre, _ = Genre.objects.get_or_create(code="agg_query")
    return Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id}.games.test",
        slug=f"slug-{technical_id}",
        primary_genre=genre,
    )


def _voter(login: str) -> User:
    return User.objects.create_user(login=login, password="correct horse battery staple")


def _vote(game: Game, user: User, value: int, *, is_valid: bool = True) -> None:
    GameRatingVote.objects.create(
        game=game,
        user=user,
        value=value,
        is_valid=is_valid,
        changed_at=timezone.now(),
    )


@pytest.mark.django_db
def test_computed_values_zero_votes_keeps_all_buckets_with_two_queries() -> None:
    game = _game("agg_zero")

    with CaptureQueriesContext(connection) as captured:
        values = _computed_values(game)

    assert len(captured) == 2
    assert values["distribution"] == ZERO_DISTRIBUTION
    assert values["count"] == 0
    assert values["total"] == 0
    assert values["average"] == Decimal("0.00")


@pytest.mark.django_db
def test_computed_values_many_votes_distribution_and_query_count() -> None:
    game = _game("agg_many")
    expected = dict(ZERO_DISTRIBUTION)
    for index in range(1, 101):
        value = ((index - 1) % 5) + 1
        _vote(game, _voter(f"agg_voter_{index}"), value)
        expected[str(value)] += 1

    with CaptureQueriesContext(connection) as captured:
        values = _computed_values(game)

    assert len(captured) == 2
    assert values["distribution"] == expected
    assert values["count"] == 100
    assert values["total"] == 300
    assert values["average"] == Decimal("3.00")


@pytest.mark.django_db
def test_computed_values_distribution_ignores_invalid_and_inactive_votes() -> None:
    game = _game("agg_excluded")
    inactive = _voter("agg_inactive")
    User.objects.filter(pk=inactive.pk).update(is_active=False)

    _vote(game, _voter("agg_valid_two"), 2)
    _vote(game, _voter("agg_valid_four"), 4)
    _vote(game, _voter("agg_invalid_five"), 5, is_valid=False)
    _vote(game, inactive, 5)

    with CaptureQueriesContext(connection) as captured:
        values = _computed_values(game)

    assert len(captured) == 2
    assert values["distribution"] == {"1": 0, "2": 1, "3": 0, "4": 1, "5": 0}
    assert values["count"] == 2
    assert values["total"] == 6
