"""Game leaderboard page: personal best and latest attempts (§2.11 item 6)."""

from __future__ import annotations

import re
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


def _game(
    *,
    technical_id: str = "attempts_game",
    direction: str = "higher_is_better",
    leaderboard_only_verified: bool = False,
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
        leaderboard_only_verified=leaderboard_only_verified,
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


def _result(
    game: Game,
    user: User,
    value: int,
    *,
    created_at=None,
    trust_level: str = GameResult.TRUST_CLIENT_REPORTED,
    is_public: bool = True,
    is_quarantined: bool = False,
    is_test: bool = False,
) -> GameResult:
    now = timezone.now()
    version = game.current_version
    assert version is not None
    session = GameSession.objects.create(
        game=game,
        game_version=version,
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
        game_version=version,
        subject_type=GameResult.SUBJECT_USER,
        user=user,
        epoch=game.leaderboard_epoch,
        value=value,
        unit=game.score_unit,
        duration_ms=30_000,
        trust_level=trust_level,
        is_public=is_public,
        is_quarantined=is_quarantined,
        is_test=is_test,
        idempotency_key=f"key-{user.pk}-{value}",
    )
    if created_at is not None:
        GameResult.objects.filter(pk=result.pk).update(created_at=created_at)
        result.refresh_from_db()
    return result


def _entry(game: Game, user: User, result: GameResult) -> LeaderboardEntry:
    return LeaderboardEntry.objects.create(
        game=game,
        epoch=game.leaderboard_epoch,
        user=user,
        best_result=result,
        value=result.value,
        achieved_at=result.created_at,
        trust_level=result.trust_level,
    )


def _attempt_values(content: str) -> list[int]:
    return [
        int(value) for value in re.findall(r'data-testid="personal-attempt-value">(\d+)<', content)
    ]


def _url(game: Game) -> str:
    return f"/en/games/{game.slug}/leaderboard/"


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_personal_section_shows_best_rank_date_and_attempts_newest_first() -> None:
    game = _game()
    target = _user("target", "Target")
    rival = _user("rival", "Rival")
    _entry(game, rival, _result(game, rival, 100))

    base = timezone.now() - timedelta(hours=3)
    oldest = _result(game, target, 70, created_at=base)
    best_moment = base + timedelta(hours=1)
    best = _result(game, target, 90, created_at=best_moment)
    _result(game, target, 60, created_at=base + timedelta(hours=2))
    _entry(game, target, best)

    client = Client()
    client.force_login(target)
    response = client.get(_url(game))
    content = response.content.decode()

    assert response.status_code == 200
    assert 'data-testid="personal-section"' in content
    # UI strings come from the seeded translation entries (§2.15).
    assert "Your results" in content
    assert "Best result" in content
    assert 'data-testid="personal-best-value">90<' in content
    assert 'data-testid="personal-rank">2<' in content
    expected_date = timezone.localtime(best.created_at).strftime("%Y-%m-%d %H:%M")
    assert f'data-testid="personal-achieved-at">{expected_date}<' in content
    assert _attempt_values(content) == [60, 90, 70]
    assert 'data-testid="personal-empty"' not in content

    # The public board still renders the rival entry above the subject.
    assert "Rival" in content
    assert 'data-testid="personal-attempt-value">70<' in content
    oldest_date = timezone.localtime(oldest.created_at).strftime("%Y-%m-%d %H:%M")
    assert f'data-testid="personal-attempt-achieved-at">{oldest_date}<' in content


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_personal_attempts_are_limited_to_twenty_newest_first() -> None:
    game = _game(technical_id="limit_attempts_game")
    target = _user("target", "Target")
    base = timezone.now() - timedelta(hours=30)
    for value in range(1, 26):
        _result(game, target, value, created_at=base + timedelta(hours=value))

    client = Client()
    client.force_login(target)
    content = client.get(_url(game)).content.decode()

    assert content.count('data-testid="personal-attempt"') == 20
    assert _attempt_values(content) == list(range(25, 5, -1))


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_guest_sees_public_leaderboard_without_personal_section() -> None:
    game = _game(technical_id="guest_attempts_game")
    target = _user("target", "Target")
    rival = _user("rival", "Rival")
    _entry(game, rival, _result(game, rival, 100))
    _entry(game, target, _result(game, target, 40))

    response = Client().get(_url(game))
    content = response.content.decode()

    assert response.status_code == 200
    assert 'data-testid="personal-section"' not in content
    assert 'data-testid="personal-best-value"' not in content
    assert 'data-testid="personal-attempt"' not in content
    assert "Rival" in content
    assert "Target" in content


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_authenticated_user_without_results_gets_empty_personal_section() -> None:
    game = _game(technical_id="empty_attempts_game")
    rival = _user("rival", "Rival")
    _entry(game, rival, _result(game, rival, 100))
    target = _user("newcomer", "Newcomer")

    client = Client()
    client.force_login(target)
    response = client.get(_url(game))
    content = response.content.decode()

    assert response.status_code == 200
    assert 'data-testid="personal-section"' in content
    assert 'data-testid="personal-empty"' in content
    assert 'data-testid="personal-best-value"' not in content
    assert 'data-testid="personal-rank"' not in content
    assert 'data-testid="personal-attempt"' not in content


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_personal_attempts_exclude_unverified_and_hidden_results() -> None:
    game = _game(
        technical_id="verified_attempts_game",
        leaderboard_only_verified=True,
    )
    target = _user("target", "Target")
    base = timezone.now() - timedelta(hours=2)
    _result(
        game,
        target,
        5,
        created_at=base + timedelta(hours=1),
        trust_level=GameResult.TRUST_CLIENT_REPORTED,
    )
    _result(
        game,
        target,
        10,
        created_at=base,
        trust_level=GameResult.TRUST_HEURISTIC_VALIDATED,
    )
    _result(
        game,
        target,
        20,
        created_at=base + timedelta(minutes=30),
        trust_level=GameResult.TRUST_CLIENT_REPORTED,
        is_quarantined=True,
    )
    _result(
        game,
        target,
        30,
        created_at=base + timedelta(minutes=40),
        trust_level=GameResult.TRUST_CLIENT_REPORTED,
        is_public=False,
    )

    client = Client()
    client.force_login(target)
    content = client.get(_url(game)).content.decode()

    assert _attempt_values(content) == [10]
