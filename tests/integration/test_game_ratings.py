from __future__ import annotations

import json
import re
import threading
from datetime import timedelta

import pytest
from django.core.cache import caches
from django.db import connection, connections
from django.test import Client, RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Game, GameVersion, Genre
from apps.gameplay.models import UserGamePlaytime
from apps.gameplay.services.sessions import SessionError
from apps.ratings.models import GameRatingAggregate, GameRatingVote
from apps.ratings.services.aggregates import recalculate
from apps.ratings.services.voting import remove_user_ratings, vote

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


def _game(*, technical_id: str = "rating_game") -> Game:
    genre = Genre.objects.create(code=f"genre_{technical_id}")
    game = Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=f"slug-{technical_id}",
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
        rating_min_playtime_seconds=120,
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


def _user(login: str, game: Game | None = None, *, seconds: int = 120) -> User:
    user = User.objects.create_user(login=login, password="correct horse battery staple")
    User.objects.filter(pk=user.pk).update(created_at=timezone.now() - timedelta(hours=2))
    user.refresh_from_db()
    if game is not None:
        UserGamePlaytime.objects.create(user=user, game=game, verified_seconds=seconds)
    return user


def _client(user: User) -> tuple[Client, str]:
    caches["default"].clear()
    caches["throttle"].clear()
    client = Client(enforce_csrf_checks=True)
    page = client.get("/en/auth/login/")
    assert page.status_code == 200
    match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.content.decode())
    assert match is not None
    client.force_login(user)
    return client, match.group(1)


def _vote(client: Client, csrf: str, game: Game, value: int = 4, *, with_csrf: bool = True):
    headers = {"HTTP_X_CSRFTOKEN": csrf} if with_csrf else {}
    return client.post(
        f"/api/v1/games/{game.technical_id}/rating",
        data=json.dumps({"value": value}),
        content_type="application/json",
        **headers,
    )


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_guest_and_no_playtime_users_cannot_vote() -> None:
    game = _game()
    guest = Client(enforce_csrf_checks=True)
    page = guest.get("/en/auth/login/")
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.content.decode()).group(1)
    anonymous = guest.post(
        f"/api/v1/games/{game.technical_id}/rating",
        data=json.dumps({"value": 5}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert anonymous.status_code == 403
    assert anonymous.json()["code"] == "E_AUTH_REQUIRED"

    user = _user("alice", game=None)
    client, csrf = _client(user)
    no_playtime = _vote(client, csrf, game)
    assert no_playtime.status_code == 403
    assert no_playtime.json()["code"] == "E_PLAYTIME_REQUIRED"


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_vote_creates_and_updates_aggregate() -> None:
    game = _game(technical_id="aggregate_game")
    user = _user("bob", game)
    client, csrf = _client(user)
    created = _vote(client, csrf, game, 4)
    assert created.status_code == 200, created.content
    assert created.json() == {
        "average": 4.0,
        "count": 1,
        "distribution": {"1": 0, "2": 0, "3": 0, "4": 1, "5": 0},
        "my_vote": 4,
    }
    aggregate = GameRatingAggregate.objects.get(game=game)
    assert aggregate.count == 1

    no_op = _vote(client, csrf, game, 4)
    assert no_op.status_code == 200
    assert GameRatingVote.objects.filter(game=game, user=user).count() == 1


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_change_cooldown_and_window_limits() -> None:
    game = _game(technical_id="cooldown_game")
    user = _user("carol", game)
    client, csrf = _client(user)
    assert _vote(client, csrf, game, 4).status_code == 200
    too_soon = _vote(client, csrf, game, 5)
    assert too_soon.status_code == 429
    assert too_soon.json()["code"] == "E_RATE_LIMIT"

    GameRatingVote.objects.filter(game=game, user=user).update(
        changed_at=timezone.now() - timedelta(hours=25),
        change_count_30d=5,
        change_window_started_at=timezone.now() - timedelta(days=10),
    )
    too_many = _vote(client, csrf, game, 5)
    assert too_many.status_code == 429

    GameRatingVote.objects.filter(game=game, user=user).update(change_count_30d=0)
    changed = _vote(client, csrf, game, 5)
    assert changed.status_code == 200
    assert changed.json()["average"] == 5.0


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_invalid_value_csrf_and_daily_limit() -> None:
    game = _game(technical_id="limits_game")
    user = _user("dave", game)
    client, csrf = _client(user)
    invalid = _vote(client, csrf, game, 6)
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "E_INVALID_REQUEST"
    no_csrf = _vote(client, csrf, game, 4, with_csrf=False)
    assert no_csrf.status_code == 403

    for index in range(20):
        other = _game(technical_id=f"daily_game_{index}")
        GameRatingVote.objects.create(
            game=other,
            user=user,
            value=4,
            changed_at=timezone.now(),
        )
    limited = _vote(client, csrf, game, 4)
    assert limited.status_code == 429
    assert limited.json()["code"] == "E_RATE_LIMIT"


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_blocked_users_excluded_and_deletion_recalculates() -> None:
    game = _game(technical_id="blocked_rating_game")
    first = _user("erin", game)
    second = _user("frank", game)
    first_client, first_csrf = _client(first)
    second_client, second_csrf = _client(second)
    assert _vote(first_client, first_csrf, game, 2).status_code == 200
    assert _vote(second_client, second_csrf, game, 4).status_code == 200
    assert GameRatingAggregate.objects.get(game=game).count == 2

    User.objects.filter(pk=first.pk).update(is_active=False)
    recalculate(game)
    aggregate = GameRatingAggregate.objects.get(game=game)
    assert aggregate.count == 1
    assert aggregate.average == 4

    remove_user_ratings(second)
    assert GameRatingVote.objects.filter(game=game, user=second).count() == 0
    assert GameRatingAggregate.objects.get(game=game).count == 0


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_account_age_and_public_summary() -> None:
    game = _game(technical_id="age_rating_game")
    young = User.objects.create_user(login="grace", password="correct horse battery staple")
    UserGamePlaytime.objects.create(user=young, game=game, verified_seconds=120)
    client, csrf = _client(young)
    too_new = _vote(client, csrf, game, 5)
    assert too_new.status_code == 429

    summary = Client().get(f"/api/v1/games/{game.technical_id}/rating/summary")
    assert summary.status_code == 200
    assert summary.json()["count"] == 0
    assert summary.json()["my_vote"] is None


def _run_threads(workers: list) -> list[str]:
    outcomes: list[str] = []
    lock = threading.Lock()

    def wrap(worker) -> None:
        try:
            worker()
        except SessionError as exc:
            with lock:
                outcomes.append(exc.code)
        else:
            with lock:
                outcomes.append("ok")
        finally:
            connections.close_all()

    threads = [threading.Thread(target=wrap, args=(worker,)) for worker in workers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not any(thread.is_alive() for thread in threads)
    return outcomes


@pytest.mark.django_db(transaction=True)
@override_settings(CACHES=LOCMEM_CACHES)
def test_parallel_first_vote_has_single_row_and_no_500() -> None:
    game = _game(technical_id="rating_first_race_game")
    user = _user("xenia", game)
    barrier = threading.Barrier(2)
    values = [5, 3]

    def make_worker(value: int):
        def worker() -> None:
            request = RequestFactory().post("/")
            request.user = user
            barrier.wait(timeout=10)
            vote(request, game.technical_id, value)

        return worker

    outcomes = _run_threads([make_worker(value) for value in values])
    assert sorted(outcomes) == ["E_RATE_LIMIT", "ok"]
    assert GameRatingVote.objects.filter(game=game, user=user).count() == 1


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_playtime_threshold_is_inclusive() -> None:
    game = _game(technical_id="threshold_rating_game")
    game.rating_min_playtime_seconds = 120
    game.save(update_fields=["rating_min_playtime_seconds"])
    user = _user("yuri", game, seconds=120)
    client, csrf = _client(user)
    response = _vote(client, csrf, game, 5)
    assert response.status_code == 200
    assert response.json()["my_vote"] == 5


@pytest.mark.django_db(transaction=True)
@override_settings(CACHES=LOCMEM_CACHES)
def test_parallel_rating_change_has_single_winner() -> None:
    game = _game(technical_id="rating_race_game")
    user = _user("heidi", game)
    GameRatingVote.objects.create(
        game=game,
        user=user,
        value=4,
        changed_at=timezone.now() - timedelta(hours=25),
        change_window_started_at=timezone.now() - timedelta(days=2),
    )
    barrier = threading.Barrier(2)
    values = [5, 3]

    def make_worker(value: int):
        def worker() -> None:
            request = RequestFactory().post("/")
            request.user = user
            barrier.wait(timeout=10)
            vote(request, game.technical_id, value)

        return worker

    outcomes = _run_threads([make_worker(value) for value in values])
    assert sorted(outcomes) == ["E_RATE_LIMIT", "ok"]
    row = GameRatingVote.objects.get(game=game, user=user)
    assert row.change_count_30d == 1


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_public_detail_shows_rating_average_with_two_decimals_and_count() -> None:
    game = _game(technical_id="detail_rating_game")
    first = _user("kate")
    second = _user("liam")
    GameRatingVote.objects.create(game=game, user=first, value=5, changed_at=timezone.now())
    GameRatingVote.objects.create(game=game, user=second, value=4, changed_at=timezone.now())
    recalculate(game)

    response = Client().get(f"/en/games/{game.slug}/")

    assert response.status_code == 200
    content = response.content.decode()
    assert 'data-testid="rating-average">4.50<' in content
    assert 'data-testid="rating-count">2<' in content
    assert 'data-testid="rating-empty"' not in content


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_public_detail_shows_explicit_no_ratings_state() -> None:
    game = _game(technical_id="detail_no_rating_game")

    response = Client().get(f"/en/games/{game.slug}/")

    assert response.status_code == 200
    content = response.content.decode()
    assert 'data-testid="rating-empty"' in content
    assert "No ratings yet." in content
    assert 'data-testid="rating-average"' not in content
    assert 'data-testid="rating-count"' not in content


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_catalog_cards_show_rating_summary_and_empty_state() -> None:
    rated = _game(technical_id="catalog_rated_game")
    unrated = _game(technical_id="catalog_unrated_game")
    first = _user("catalog_rater_one")
    second = _user("catalog_rater_two")
    GameRatingVote.objects.create(game=rated, user=first, value=5, changed_at=timezone.now())
    GameRatingVote.objects.create(game=rated, user=second, value=4, changed_at=timezone.now())
    recalculate(rated)

    response = Client().get("/en/games/")

    assert response.status_code == 200
    content = response.content.decode()
    assert f"/en/games/{rated.slug}/" in content
    assert f"/en/games/{unrated.slug}/" in content
    assert content.count('data-testid="card-rating-average">4.50<') == 1
    assert content.count('data-testid="card-rating-count">2 votes<') == 1
    assert content.count('data-testid="card-rating-empty"') == 1
    assert "No ratings yet." in content


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_catalog_cards_fetch_rating_summaries_in_one_query() -> None:
    games = [_game(technical_id=f"catalog_n1_game_{index}") for index in range(3)]
    for index, game in enumerate(games):
        voter = _user(f"catalog_n1_voter_{index}")
        GameRatingVote.objects.create(game=game, user=voter, value=5, changed_at=timezone.now())
        recalculate(game)

    with CaptureQueriesContext(connection) as captured:
        response = Client().get("/en/games/")

    assert response.status_code == 200
    aggregate_queries = [
        query for query in captured.captured_queries if "ratings_aggregate" in query["sql"]
    ]
    assert len(aggregate_queries) == 1
    assert response.content.decode().count('data-testid="card-rating-average">5.00<') == 3


@pytest.mark.django_db(transaction=True)
@override_settings(CACHES=LOCMEM_CACHES)
def test_parallel_votes_keep_aggregate_consistent() -> None:
    game = _game(technical_id="rating_aggregate_race_game")
    first = _user("ivan", game)
    second = _user("judy", game)
    barrier = threading.Barrier(2)
    values = {first.pk: 5, second.pk: 3}

    def make_worker(user, value: int):
        def worker() -> None:
            request = RequestFactory().post("/")
            request.user = user
            barrier.wait(timeout=10)
            vote(request, game.technical_id, value)

        return worker

    outcomes = _run_threads([make_worker(user, values[user.pk]) for user in (first, second)])
    assert outcomes == ["ok", "ok"]
    aggregate = GameRatingAggregate.objects.get(game=game)
    assert aggregate.count == 2
    assert aggregate.total == 8
    assert aggregate.average == 4
