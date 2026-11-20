from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import Client, override_settings
from django.utils import timezone

from apps.accounts.models import User, UserProfile
from apps.catalog.models import Game, GameVersion, Genre
from apps.gameplay.models import GameResult, GameSession, LeaderboardEntry

LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "throttle": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}
API = "/api/v1/games"


def _game(*, technical_id: str = "leaderboard_game", direction: str = "higher_is_better") -> Game:
    genre = Genre.objects.create(code=f"genre_{technical_id}")
    game = Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=f"slug-{technical_id}",
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
        score_direction=direction,
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
    if achieved_at is not None:
        GameResult.objects.filter(pk=result.pk).update(created_at=achieved_at)
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


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_top_entries_are_ordered_by_direction() -> None:
    game = _game()
    _entry(game, _user("alice", "Alice"), 10)
    _entry(game, _user("bob", "Bob"), 30)
    _entry(game, _user("carol", "Carol"), 20)
    response = Client().get(f"{API}/{game.technical_id}/leaderboard")
    assert response.status_code == 200
    payload = response.json()
    assert [item["value"] for item in payload["entries"]] == [30, 20, 10]
    assert [item["rank"] for item in payload["entries"]] == [1, 2, 3]
    assert payload["entries"][0]["nickname"] == "Bob"
    assert payload["me"] is None


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_lower_is_better_and_tie_break() -> None:
    game = _game(technical_id="lower_board_game", direction="lower_is_better")
    _entry(game, _user("dave", "Dave"), 50, achieved_at=timezone.now() - timedelta(hours=1))
    _entry(game, _user("erin", "Erin"), 50)
    _entry(game, _user("frank", "Frank"), 10)
    entries = Client().get(f"{API}/{game.technical_id}/leaderboard?limit=10").json()["entries"]
    assert [item["value"] for item in entries] == [10, 50, 50]
    assert entries[1]["nickname"] == "Dave"
    assert entries[2]["nickname"] == "Erin"


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_me_row_and_personal_best() -> None:
    game = _game(technical_id="me_board_game")
    user = _user("grace", "Grace")
    _entry(game, _user("heidi", "Heidi"), 100)
    _entry(game, user, 40)
    client = Client()
    client.force_login(user)

    board = client.get(f"{API}/{game.technical_id}/leaderboard").json()
    assert board["me"]["value"] == 40
    assert board["me"]["rank"] == 2
    assert board["me"]["nickname"] == "Grace"

    best = client.get(f"{API}/{game.technical_id}/me/best")
    assert best.status_code == 200
    assert best.json() == {
        "value": 40,
        "achieved_at": board["me"]["achieved_at"],
        "rank": 2,
    }


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_personal_best_requires_authentication_and_game_is_published() -> None:
    game = _game(technical_id="auth_board_game")
    anonymous = Client().get(f"{API}/{game.technical_id}/me/best")
    assert anonymous.status_code == 403
    assert anonymous.json()["code"] == "E_AUTH_REQUIRED"

    missing = Client().get(f"{API}/missing_game/leaderboard")
    assert missing.status_code == 404
    assert missing.json()["code"] == "E_SESSION_INVALID"

    game.status = Game.STATUS_DRAFT
    game.save(update_fields=["status"])
    hidden = Client().get(f"{API}/{game.technical_id}/leaderboard")
    assert hidden.status_code == 404


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_guest_reads_board_without_me_and_empty_board_shape() -> None:
    game = _game(technical_id="guest_board_game")
    empty = Client().get(f"{API}/{game.technical_id}/leaderboard")
    assert empty.status_code == 200
    assert empty.json()["entries"] == []
    assert empty.json()["me"] is None

    _entry(game, _user("nina", "Nina"), 10)
    guest = Client().get(f"{API}/{game.technical_id}/leaderboard")
    assert guest.status_code == 200
    payload = guest.json()
    assert payload["me"] is None
    assert payload["entries"][0]["trust_level"] == GameResult.TRUST_CLIENT_REPORTED


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_me_rank_matches_top_entry() -> None:
    game = _game(technical_id="match_board_game")
    user = _user("olga", "Olga")
    _entry(game, _user("peter", "Peter"), 100)
    _entry(game, user, 60)
    client = Client()
    client.force_login(user)
    payload = client.get(f"{API}/{game.technical_id}/leaderboard").json()
    own_in_top = next(item for item in payload["entries"] if item["nickname"] == "Olga")
    assert payload["me"]["rank"] == own_in_top["rank"] == 2


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_limit_validation_and_epoch_filter() -> None:
    game = _game(technical_id="limit_board_game")
    _entry(game, _user("ivan", "Ivan"), 10)
    assert Client().get(f"{API}/{game.technical_id}/leaderboard?limit=100").status_code == 200
    assert Client().get(f"{API}/{game.technical_id}/leaderboard?limit=5").status_code == 400
    assert Client().get(f"{API}/{game.technical_id}/leaderboard?limit=abc").status_code == 400

    game.leaderboard_epoch = 2
    game.save(update_fields=["leaderboard_epoch"])
    payload = Client().get(f"{API}/{game.technical_id}/leaderboard").json()
    assert payload["entries"] == []
    assert payload["epoch"] == 2
