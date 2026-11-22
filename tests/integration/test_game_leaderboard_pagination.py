"""Game leaderboard page: TOP-100 pagination and the current-user row (§2.11)."""

from __future__ import annotations

import re
from datetime import timedelta

import pytest
from django.core.cache import caches
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.models import User, UserProfile
from apps.catalog.models import Game, GameVersion, Genre
from apps.gameplay.models import GameResult, GameSession, LeaderboardEntry

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


def _game(*, technical_id: str = "paged_board_game") -> Game:
    genre = Genre.objects.create(code=f"genre_{technical_id}")
    game = Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=f"slug-{technical_id}",
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
        score_direction="higher_is_better",
    )
    version = GameVersion.objects.create(
        game=game,
        semver="1.0.0",
        package_hash="a" * 64,
        runtime_hash="b" * 64,
        sdk_version="1.1.0",
        size_bytes=1000,
        manifest={},
        supported_languages=["en"],
    )
    game.current_version = version
    game.save(update_fields=["current_version"])
    return game


def _user(login: str, nickname: str) -> User:
    user = User.objects.create_user(login=login, password="correct horse battery staple")
    UserProfile.objects.create(
        user=user,
        nickname=nickname,
        nickname_skeleton=nickname.lower(),
    )
    return user


def _entry(game: Game, user: User, value: int, *, achieved_at=None) -> LeaderboardEntry:
    now = timezone.now()
    session = GameSession.objects.create(
        game=game,
        game_version=game.current_version,
        subject_type=GameSession.SUBJECT_USER,
        subject_id=user.id,
        mode=GameSession.MODE_USER,
        state=GameSession.STATE_FINISHED,
        seed=f"seed-{user.pk}-{value}",
        max_session_seconds=1800,
        activated_at=now - timedelta(seconds=30),
        last_heartbeat_at=now,
        finished_at=now,
    )
    result = GameResult.objects.create(
        session=session,
        game=game,
        game_version=game.current_version,
        subject_type=GameResult.SUBJECT_USER,
        user=user,
        epoch=game.leaderboard_epoch,
        value=value,
        unit=game.score_unit,
        duration_ms=30_000,
        idempotency_key=f"key-{user.pk}-{value}",
    )
    reached = achieved_at or now
    GameResult.objects.filter(pk=result.pk).update(created_at=reached)
    result.refresh_from_db()
    return LeaderboardEntry.objects.create(
        game=game,
        epoch=game.leaderboard_epoch,
        user=user,
        best_result=result,
        value=value,
        achieved_at=result.created_at,
        trust_level=GameResult.TRUST_CLIENT_REPORTED,
    )


def _seed_entries(game: Game, count: int) -> list[User]:
    """Seed ``count`` players with monotonically decreasing (worse) scores."""
    base = timezone.now() - timedelta(days=1)
    users: list[User] = []
    for index in range(count):
        user = _user(f"player_{index}", f"Player {index}")
        _entry(
            game,
            user,
            10_000 - index,
            achieved_at=base + timedelta(seconds=index),
        )
        users.append(user)
    return users


def _url(game: Game) -> str:
    return f"/en/games/{game.slug}/leaderboard/"


def _ranks(content: str) -> list[int]:
    """Ranks from both paginated rows and the always-visible user row."""
    return [
        int(value)
        for value in re.findall(
            r'data-testid="(?:leaderboard-row|current-user-row)"[^>]*>\s*<td[^>]*>(\d+)<',
            content,
        )
    ]


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_top_100_is_paginated_with_absolute_ranks() -> None:
    game = _game(technical_id="top_100_game")
    _seed_entries(game, 105)

    first = Client().get(_url(game))
    assert first.status_code == 200
    assert _ranks(first.content.decode()) == list(range(1, 11))
    assert 'data-testid="pagination"' in first.content.decode()
    assert first.context["page_obj"].paginator.count == 100
    assert first.context["page_obj"].paginator.num_pages == 10

    last = Client().get(f"{_url(game)}?page=10")
    assert _ranks(last.content.decode()) == list(range(91, 101))

    beyond = Client().get(f"{_url(game)}?page=11")
    assert _ranks(beyond.content.decode()) == list(range(91, 101))


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_page_boundaries_are_clamped() -> None:
    game = _game(technical_id="page_boundaries_game")
    _seed_entries(game, 25)

    for query in ("?page=0", "?page=-1", "?page=abc", "?page="):
        response = Client().get(f"{_url(game)}{query}")
        assert response.status_code == 200
        assert _ranks(response.content.decode()) == list(range(1, 11))

    last = Client().get(f"{_url(game)}?page=99")
    assert _ranks(last.content.decode()) == list(range(21, 26))
    assert 'data-testid="pagination"' in last.content.decode()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_current_user_row_is_always_visible() -> None:
    game = _game(technical_id="current_row_game")
    users = _seed_entries(game, 105)
    in_top = users[54]  # rank 55
    outside_top = users[104]  # rank 105, beyond TOP-100

    client = Client()
    client.force_login(in_top)

    first = client.get(_url(game)).content.decode()
    assert _ranks(first)[:10] == list(range(1, 11))
    assert _ranks(first)[-1] == 55
    assert first.count('data-testid="current-user-row"') == 1
    assert 'data-testid="current-user-section"' in first
    assert 'data-testid="personal-section"' in first
    assert 'data-testid="personal-best-value">9946<' in first

    sixth = client.get(f"{_url(game)}?page=6").content.decode()
    assert _ranks(sixth) == list(range(51, 61))
    assert sixth.count('data-testid="current-user-row"') == 1
    assert 'data-testid="current-user-section"' not in sixth
    assert 'data-testid="current-user-rank">55<' in sixth
    assert 'data-testid="personal-section"' in sixth

    client = Client()
    client.force_login(outside_top)
    outside_first = client.get(_url(game)).content.decode()
    assert 'data-testid="current-user-rank">105<' in outside_first
    assert outside_first.count('data-testid="current-user-row"') == 1
    assert 'data-testid="current-user-section"' in outside_first

    tenth = client.get(f"{_url(game)}?page=10").content.decode()
    assert _ranks(tenth)[:10] == list(range(91, 101))
    assert 'data-testid="current-user-rank">105<' in tenth
    assert 'data-testid="current-user-section"' in tenth

    guest = Client().get(_url(game)).content.decode()
    assert 'data-testid="current-user-row"' not in guest
    assert 'data-testid="current-user-section"' not in guest
    assert 'data-testid="personal-section"' not in guest


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_empty_board_has_no_pagination_or_user_row() -> None:
    game = _game(technical_id="empty_board_game")

    guest = Client().get(_url(game))
    content = guest.content.decode()
    assert guest.status_code == 200
    assert 'data-testid="leaderboard-empty"' in content
    assert 'data-testid="pagination"' not in content
    assert 'data-testid="current-user-row"' not in content

    user = _user("empty_board_user", "Empty Board")
    client = Client()
    client.force_login(user)
    own = client.get(_url(game)).content.decode()
    assert 'data-testid="personal-section"' in own
    assert 'data-testid="personal-empty"' in own
    assert 'data-testid="current-user-row"' not in own


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_leaderboard_page_does_not_scale_queries_with_rows() -> None:
    game = _game(technical_id="n_plus_one_game")
    first_user = _user("n1_first", "N1 First")
    _entry(game, first_user, 10)

    # Warm the language/translation caches so both measurements are comparable.
    Client().get(_url(game))

    with CaptureQueriesContext(connection) as one_row:
        response = Client().get(_url(game))
    assert response.status_code == 200

    _seed_entries(game, 9)

    with CaptureQueriesContext(connection) as ten_rows:
        response = Client().get(_url(game))
    assert response.status_code == 200

    assert len(ten_rows) == len(one_row)
