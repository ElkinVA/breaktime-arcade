from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Game, GameVersion, Genre
from apps.crm.models.backup import BackupRun
from apps.crm.services.dashboard import (
    TOP_GAMES_LIMIT,
    _utc_day_bounds,
    dashboard_stats,
)
from apps.gameplay.models import GameDailyStats, GameSession
from apps.ratings.models import GameRatingAggregate, GameRatingVote

PASSWORD = "correct horse battery staple"


def _game(
    *,
    technical_id: str,
    status: str = Game.STATUS_PUBLISHED,
    with_version: bool = False,
) -> Game:
    genre, _ = Genre.objects.get_or_create(code=f"genre_{technical_id}")
    game = Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=f"slug-{technical_id}",
        primary_genre=genre,
        status=status,
        published_at=timezone.now() if status == Game.STATUS_PUBLISHED else None,
    )
    if with_version:
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


def _user(login: str, *, is_staff: bool = False, is_active: bool = True) -> User:
    return User.objects.create_user(
        login=login,
        password=PASSWORD,
        is_staff=is_staff,
        is_active=is_active,
    )


def _session(game: Game, *, mode: str = GameSession.MODE_USER) -> GameSession:
    subject_type = (
        GameSession.SUBJECT_USER if mode != GameSession.MODE_GUEST else GameSession.SUBJECT_ANON
    )
    return GameSession.objects.create(
        game=game,
        game_version=game.current_version,
        subject_type=subject_type,
        subject_id=uuid4(),
        mode=mode,
        state=GameSession.STATE_ACTIVE,
        seed=f"seed-{uuid4()}",
        max_session_seconds=1800,
    )


def _vote(game: Game, user: User, value: int) -> GameRatingVote:
    return GameRatingVote.objects.create(game=game, user=user, value=value)


def _staff_client(login: str = "staff") -> Client:
    staff = _user(login, is_staff=True)
    User.objects.filter(pk=staff.pk).update(totp_confirmed_at=timezone.now())
    staff.refresh_from_db()
    client = Client()
    client.force_login(staff)
    session = client.session
    session["ba_2fa_verified"] = True
    session.save()
    return client


@pytest.mark.django_db
def test_zero_data_dashboard_stats() -> None:
    stats = dashboard_stats()

    assert stats.published_games == 0
    assert stats.total_accounts == 0
    assert stats.active_accounts_30d == 0
    assert stats.sessions_today == 0
    assert stats.top_games == ()
    assert stats.average_rating == 0.0
    assert stats.new_votes_today == 0
    assert stats.latest_backup is None


@pytest.mark.django_db
def test_published_games_counter_ignores_non_public_statuses() -> None:
    _game(technical_id="published_game")
    _game(technical_id="hidden_game", status=Game.STATUS_HIDDEN)
    _game(technical_id="draft_game", status=Game.STATUS_DRAFT)
    _game(technical_id="archived_game", status=Game.STATUS_ARCHIVED)

    assert dashboard_stats().published_games == 1


@pytest.mark.django_db
def test_total_and_active_accounts_counter() -> None:
    now = timezone.now()
    stale = _user("stale")
    recent = _user("recent")
    inactive = _user("inactive", is_active=False)
    never_logged_in = _user("never_logged_in")

    User.objects.filter(pk=recent.pk).update(last_login=now - timedelta(days=2))
    User.objects.filter(pk=stale.pk).update(last_login=now - timedelta(days=31))
    User.objects.filter(pk=inactive.pk).update(last_login=now - timedelta(days=1))
    User.objects.filter(pk=never_logged_in.pk).update(last_login=None)

    stats = dashboard_stats()

    assert stats.total_accounts == 4
    assert stats.active_accounts_30d == 1


@pytest.mark.django_db
def test_sessions_today_counts_user_and_guest_only() -> None:
    game = _game(technical_id="sessions_game", with_version=True)
    user_session = _session(game)
    guest_session = _session(game, mode=GameSession.MODE_GUEST)
    _session(game, mode=GameSession.MODE_PREVIEW)
    _session(game, mode=GameSession.MODE_AUTOTEST)

    day_start, _ = _utc_day_bounds()
    old_time = day_start - timedelta(minutes=1)
    GameSession.objects.filter(pk=user_session.pk).update(created_at=old_time)
    GameSession.objects.filter(pk=guest_session.pk).update(created_at=day_start)

    assert dashboard_stats().sessions_today == 1


@pytest.mark.django_db
def test_top_popular_games_is_bounded_published_and_ordered() -> None:
    day = timezone.now().date()
    games = [_game(technical_id=f"top_game_{index}") for index in range(TOP_GAMES_LIMIT + 2)]
    for index, game in enumerate(games):
        GameDailyStats.objects.create(
            game=game,
            date=day,
            unique_sessions=(index + 1) * 10,
        )
    hidden = _game(technical_id="hidden_popular", status=Game.STATUS_HIDDEN)
    GameDailyStats.objects.create(game=hidden, date=day, unique_sessions=10_000)

    top = dashboard_stats().top_games

    assert len(top) == TOP_GAMES_LIMIT
    assert [entry.technical_id for entry in top] == [
        f"top_game_{index}" for index in reversed(range(2, TOP_GAMES_LIMIT + 2))
    ]
    assert [entry.sessions for entry in top] == [70, 60, 50, 40, 30]


@pytest.mark.django_db
def test_average_rating_is_vote_weighted_and_published_only() -> None:
    now = timezone.now()
    first = _game(technical_id="rating_first")
    second = _game(technical_id="rating_second")
    hidden = _game(technical_id="rating_hidden", status=Game.STATUS_HIDDEN)

    GameRatingAggregate.objects.create(
        game=first, total=10, count=2, average=5, recalculated_at=now
    )
    GameRatingAggregate.objects.create(
        game=second, total=12, count=4, average=3, recalculated_at=now
    )
    GameRatingAggregate.objects.create(
        game=hidden, total=100, count=1, average=1, recalculated_at=now
    )

    assert dashboard_stats().average_rating == 3.67


@pytest.mark.django_db
def test_new_votes_counter_uses_todays_votes_only() -> None:
    game = _game(technical_id="votes_game")
    first = _user("vote_first")
    second = _user("vote_second")
    today_vote = _vote(game, first, 5)
    _vote(game, second, 4)

    day_start, _ = _utc_day_bounds()
    GameRatingVote.objects.filter(pk=today_vote.pk).update(
        created_at=day_start - timedelta(minutes=1)
    )

    assert dashboard_stats().new_votes_today == 1


@pytest.mark.django_db
def test_latest_backup_counter_returns_most_recent_run() -> None:
    older = BackupRun.objects.create(type=BackupRun.TYPE_FULL, status=BackupRun.STATUS_SUCCESS)
    BackupRun.objects.filter(pk=older.pk).update(started_at=timezone.now() - timedelta(hours=2))
    newer = BackupRun.objects.create(
        type=BackupRun.TYPE_RESTORE_CHECK,
        status=BackupRun.STATUS_FAILED,
    )

    latest = dashboard_stats().latest_backup

    assert latest is not None
    assert latest.pk == newer.pk
    assert latest.status == BackupRun.STATUS_FAILED


@pytest.mark.django_db
def test_dashboard_stats_uses_bounded_queries(django_assert_num_queries) -> None:
    now = timezone.now()
    game = _game(technical_id="query_game", with_version=True)
    _session(game)
    user = _user("query_user")
    _vote(game, user, 5)
    GameDailyStats.objects.create(game=game, date=now.date(), unique_sessions=1)
    GameRatingAggregate.objects.create(game=game, total=5, count=1, average=5, recalculated_at=now)
    BackupRun.objects.create(type=BackupRun.TYPE_FULL, status=BackupRun.STATUS_SUCCESS)

    with django_assert_num_queries(8):
        dashboard_stats()


@pytest.mark.django_db
def test_dashboard_requires_staff() -> None:
    anonymous = Client()
    response = anonymous.get(reverse("crm:dashboard"))
    assert response.status_code == 302
    assert response.url == reverse("crm:login")

    user = _user("plain_user")
    client = Client()
    client.force_login(user)
    response = client.get(reverse("crm:dashboard"))
    assert response.status_code == 302
    assert response.url == reverse("crm:login")


@pytest.mark.django_db
def test_dashboard_renders_operational_counters() -> None:
    now = timezone.now()
    game = _game(technical_id="dashboard_game", with_version=True)
    _session(game)
    user = _user("dashboard_voter")
    _vote(game, user, 5)
    GameDailyStats.objects.create(game=game, date=now.date(), unique_sessions=42)
    GameRatingAggregate.objects.create(game=game, total=5, count=1, average=5, recalculated_at=now)
    BackupRun.objects.create(type=BackupRun.TYPE_FULL, status=BackupRun.STATUS_SUCCESS)

    response = _staff_client().get(reverse("crm:dashboard"))

    assert response.status_code == 200
    content = response.content.decode()
    assert 'data-testid="dashboard-published-games">1<' in content
    assert 'data-testid="dashboard-total-accounts">2<' in content
    assert 'data-testid="dashboard-active-accounts">1<' in content
    assert 'data-testid="dashboard-sessions-today">1<' in content
    assert 'data-testid="dashboard-average-rating">5.0<' in content
    assert 'data-testid="dashboard-new-votes">1<' in content
    assert 'data-testid="dashboard-latest-backup-status">' in content
    assert 'data-testid="dashboard-top-game"' in content
    assert "dashboard_game" in content
