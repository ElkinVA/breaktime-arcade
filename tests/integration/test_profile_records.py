"""Account cabinet: personal records, ranks and verified playtime (§2.10.4)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.models import User, UserProfile
from apps.catalog.models import Game, GameTranslation, GameVersion, Genre
from apps.gameplay.models import GameResult, GameSession, LeaderboardEntry, UserGamePlaytime
from apps.i18n.models import Language
from apps.leaderboards.services.queries import get_leaderboard, get_personal_best

LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


def _user(login: str, nickname: str) -> User:
    user = User.objects.create_user(login=login, password="correct horse battery staple")
    UserProfile.objects.create(
        user=user,
        nickname=nickname,
        nickname_skeleton=nickname.lower(),
    )
    return user


def _game(
    technical_id: str,
    *,
    name: str | None = None,
    direction: str = "higher_is_better",
    leaderboard_enabled: bool = True,
) -> Game:
    genre = Genre.objects.create(code=f"genre_{technical_id}")
    game = Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=f"slug-{technical_id}",
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
        score_direction=direction,
        leaderboard_enabled=leaderboard_enabled,
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
    if name is not None:
        GameTranslation.objects.create(
            game=game,
            language=Language.objects.get(code="en"),
            name=name,
            slug=f"tr-{technical_id}",
            short_description="Short description",
            description="Description",
        )
    return game


def _entry(game: Game, user: User, value: int, *, achieved_at=None) -> LeaderboardEntry:
    now = timezone.now()
    session = GameSession.objects.create(
        game=game,
        game_version=game.current_version,
        subject_type=GameSession.SUBJECT_USER,
        subject_id=user.id,
        mode=GameSession.MODE_USER,
        state=GameSession.STATE_FINISHED,
        seed="seed",
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
        idempotency_key=f"key-{user.pk}-{game.pk}-{value}",
    )
    moment = achieved_at or result.created_at
    if achieved_at is not None:
        GameResult.objects.filter(pk=result.pk).update(created_at=achieved_at)
        result.refresh_from_db()
        moment = result.created_at
    return LeaderboardEntry.objects.create(
        game=game,
        epoch=game.leaderboard_epoch,
        user=user,
        best_result=result,
        value=value,
        achieved_at=moment,
        trust_level=GameResult.TRUST_CLIENT_REPORTED,
    )


def _playtime(user: User, game: Game, seconds: int) -> UserGamePlaytime:
    return UserGamePlaytime.objects.create(
        user=user,
        game=game,
        verified_seconds=seconds,
    )


def _records(response) -> dict[str, dict]:
    return {item["game"].technical_id: item for item in response.context["my_games"]}


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_profile_lists_best_result_rank_playtime_and_links() -> None:
    target = _user("target", "Target")
    higher = _game("alpha_game", name="Alpha Game")
    lower = _game("beta_game", name="Beta Game", direction="lower_is_better")
    detail_only = _game("gamma_game", name="Gamma Game", leaderboard_enabled=False)

    _entry(higher, _user("rival_one", "Rival One"), 100)
    _entry(higher, target, 50)
    _entry(lower, _user("rival_two", "Rival Two"), 5)
    _entry(lower, target, 10)

    _playtime(target, higher, 125)
    _playtime(target, lower, 60)
    _playtime(target, detail_only, 15)

    client = Client()
    client.force_login(target)
    response = client.get("/en/account/")

    assert response.status_code == 200
    records = _records(response)
    assert set(records) == {"alpha_game", "beta_game", "gamma_game"}

    alpha = records["alpha_game"]
    assert alpha["name"] == "Alpha Game"
    assert alpha["best_value"] == 50
    assert alpha["rank"] == 2
    assert alpha["playtime_seconds"] == 125

    beta = records["beta_game"]
    assert beta["name"] == "Beta Game"
    assert beta["best_value"] == 10
    assert beta["rank"] == 2
    assert beta["playtime_seconds"] == 60

    gamma = records["gamma_game"]
    assert gamma["best_value"] is None
    assert gamma["rank"] is None
    assert gamma["playtime_seconds"] == 15

    content = response.content.decode()
    assert "My games" in content
    assert "Alpha Game" in content
    assert "Beta Game" in content
    assert "Gamma Game" in content
    assert 'href="/en/games/slug-alpha_game/leaderboard/"' in content
    assert 'href="/en/games/slug-gamma_game/"' in content
    assert "125 s" in content


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_profile_rank_matches_existing_leaderboard_tie_break() -> None:
    target = _user("target", "Target")
    rival = _user("rival", "Rival")
    game = _game("rank_tie_game", name="Rank Tie Game")
    early = timezone.now() - timedelta(hours=1)

    _entry(game, rival, 50, achieved_at=early)
    _entry(game, target, 50)

    client = Client()
    client.force_login(target)
    record = _records(client.get("/en/account/"))["rank_tie_game"]

    expected = get_personal_best(game, target)["rank"]
    assert expected == 2
    assert record["rank"] == expected
    assert get_leaderboard(game, limit=10, user=target)["me"]["rank"] == expected


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_profile_playtime_only_and_record_only_games_are_both_listed() -> None:
    target = _user("target", "Target")
    played = _game("played_only_game", name="Played Only")
    recorded = _game("recorded_only_game", name="Recorded Only")

    _playtime(target, played, 90)
    _entry(recorded, target, 7)

    client = Client()
    client.force_login(target)
    records = _records(client.get("/en/account/"))

    assert records["played_only_game"]["best_value"] is None
    assert records["played_only_game"]["rank"] is None
    assert records["played_only_game"]["playtime_seconds"] == 90
    assert records["recorded_only_game"]["best_value"] == 7
    assert records["recorded_only_game"]["rank"] == 1
    assert records["recorded_only_game"]["playtime_seconds"] is None


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_profile_empty_state_is_friendly() -> None:
    user = _user("empty_user", "Empty User")
    client = Client()
    client.force_login(user)

    response = client.get("/en/account/")

    assert response.status_code == 200
    assert response.context["my_games"] == []
    assert 'data-testid="my-games-empty"' in response.content.decode()
    assert "You have no game records yet." in response.content.decode()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_profile_requires_authentication() -> None:
    response = Client().get("/en/account/")

    assert response.status_code == 302
    assert "/en/auth/login/" in response["Location"]


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_profile_record_queries_do_not_grow_with_game_count() -> None:
    target = _user("query_user", "Query User")
    first = _game("query_game_0", name="Query Game 0")
    _entry(first, target, 10)
    _playtime(target, first, 20)

    client = Client()
    client.force_login(target)
    client.get("/en/account/")  # warm the i18n dictionary cache

    with CaptureQueriesContext(connection) as baseline:
        assert client.get("/en/account/").status_code == 200

    for index in range(1, 5):
        game = _game(f"query_game_{index}", name=f"Query Game {index}")
        _entry(game, target, index)
        _playtime(target, game, index * 10)

    with CaptureQueriesContext(connection) as many:
        assert client.get("/en/account/").status_code == 200

    assert len(many) == len(baseline)
