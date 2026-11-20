from __future__ import annotations

import json
import re
import threading
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from django.core.cache import caches
from django.db import connections
from django.test import Client, RequestFactory, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Game, GameVersion, Genre
from apps.gameplay.models import GameDailyStats, GamePlayCredit, GameSession
from apps.gameplay.services.popularity import credit_session
from apps.gameplay.services.sessions import (
    SessionError,
    close_session,
    heartbeat,
)

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


def _game(*, technical_id: str = "popularity_game") -> Game:
    genre = Genre.objects.create(code=f"genre_{technical_id}")
    game = Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=f"slug-{technical_id}",
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
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


def _client(user: User | None = None) -> tuple[Client, str]:
    caches["default"].clear()
    caches["throttle"].clear()
    client = Client(enforce_csrf_checks=True)
    page = client.get("/en/auth/login/")
    assert page.status_code == 200
    match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.content.decode())
    assert match is not None
    if user is not None:
        client.force_login(user)
    return client, match.group(1)


def _session(
    game: Game,
    *,
    user: User | None = None,
    mode: str = GameSession.MODE_USER,
    credited_ms: int = 30_000,
) -> GameSession:
    now = timezone.now()
    if user is not None:
        subject_type = GameSession.SUBJECT_USER
        subject_id = user.id
    else:
        from apps.accounts.models import AnonymousIdentity

        subject_type = GameSession.SUBJECT_ANON
        identity = AnonymousIdentity.objects.create(
            token_hash=uuid4().hex,
            expires_at=now + timedelta(days=1),
        )
        subject_id = identity.id
    return GameSession.objects.create(
        game=game,
        game_version=game.current_version,
        subject_type=subject_type,
        subject_id=subject_id,
        mode=mode,
        state=GameSession.STATE_ACTIVE,
        seed=f"seed-{subject_id}",
        max_session_seconds=1800,
        credited_ms=credited_ms,
        activated_at=now - timedelta(seconds=30),
        last_heartbeat_at=now,
    )


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_close_credits_user_and_is_idempotent() -> None:
    game = _game()
    user = User.objects.create_user(login="alice", password="correct horse battery staple")
    session = _session(game, user=user)
    client, csrf = _client(user)
    response = client.post(f"/api/v1/sessions/{session.id}/close", HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code == 204
    session.refresh_from_db()
    assert session.state == GameSession.STATE_ABORTED
    assert GamePlayCredit.objects.filter(game=game, subject_type="user").exists()
    stats = GameDailyStats.objects.get(game=game, date=timezone.now().date())
    assert stats.sessions == 1
    assert stats.unique_sessions == 1

    again = client.post(f"/api/v1/sessions/{session.id}/close", HTTP_X_CSRFTOKEN=csrf)
    assert again.status_code == 204
    stats.refresh_from_db()
    assert stats.sessions == 1


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_guest_close_credits_and_preview_is_excluded() -> None:
    game = _game(technical_id="guest_popularity_game")
    guest, csrf = _client()
    created = guest.post(
        "/api/v1/sessions",
        data=json.dumps({"game_id": game.technical_id}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    ).json()
    guest.post(
        f"/api/v1/sessions/{created['session_id']}/activate",
        data=json.dumps({"ticket": created["ticket"], "binding_nonce": "n" * 32}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    GameSession.objects.filter(pk=created["session_id"]).update(credited_ms=30_000)
    closed = guest.post(f"/api/v1/sessions/{created['session_id']}/close", HTTP_X_CSRFTOKEN=csrf)
    assert closed.status_code == 204
    assert GamePlayCredit.objects.filter(game=game, subject_type="anon").exists()

    preview_user = User.objects.create_user(login="bob", password="correct horse battery staple")
    preview = _session(game, user=preview_user, mode=GameSession.MODE_PREVIEW, credited_ms=30_000)
    preview_request = RequestFactory().post("/")
    preview_request.user = preview_user
    close_session(preview_request, preview.id)
    assert not GamePlayCredit.objects.filter(subject_id=preview_user.id).exists()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_short_session_is_not_credited() -> None:
    game = _game(technical_id="short_popularity_game")
    user = User.objects.create_user(login="carol", password="correct horse battery staple")
    session = _session(game, user=user, credited_ms=10_000)
    request = RequestFactory().post("/")
    request.user = user
    close_session(request, session.id)
    assert not GamePlayCredit.objects.exists()
    assert not GameDailyStats.objects.exists()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_credit_window_counts_unique_once_per_30_minutes() -> None:
    game = _game(technical_id="window_popularity_game")
    user = User.objects.create_user(login="dave", password="correct horse battery staple")
    first = _session(game, user=user)
    second = _session(game, user=user)
    third = _session(game, user=user)
    now = timezone.now()
    assert credit_session(first, duration_ms=30_000, completed=True, now=now)
    assert not credit_session(
        second, duration_ms=30_000, completed=False, now=now + timedelta(minutes=10)
    )
    assert credit_session(
        third, duration_ms=30_000, completed=False, now=now + timedelta(minutes=31)
    )
    stats = GameDailyStats.objects.get(game=game, date=now.date())
    assert stats.sessions == 3
    assert stats.unique_sessions == 2
    assert stats.completions == 1
    assert stats.avg_duration_ms == 30_000


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_close_ownership_created_session_and_threshold() -> None:
    game = _game(technical_id="close_rules_game")
    owner = User.objects.create_user(login="hank", password="correct horse battery staple")
    stranger = User.objects.create_user(login="iris", password="correct horse battery staple")
    session = _session(game, user=owner, credited_ms=15_000)

    stranger_client, stranger_csrf = _client(stranger)
    denied = stranger_client.post(
        f"/api/v1/sessions/{session.id}/close", HTTP_X_CSRFTOKEN=stranger_csrf
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "E_OWNERSHIP"

    owner_client, owner_csrf = _client(owner)
    closed = owner_client.post(f"/api/v1/sessions/{session.id}/close", HTTP_X_CSRFTOKEN=owner_csrf)
    assert closed.status_code == 204
    assert GamePlayCredit.objects.filter(game=game, subject_id=owner.id).exists()

    created = GameSession.objects.create(
        game=game,
        game_version=game.current_version,
        subject_type=GameSession.SUBJECT_USER,
        subject_id=owner.id,
        mode=GameSession.MODE_USER,
        state=GameSession.STATE_CREATED,
        seed="created-close",
        max_session_seconds=1800,
    )
    request = RequestFactory().post("/")
    request.user = owner
    close_session(request, created.id)
    created.refresh_from_db()
    assert created.state == GameSession.STATE_ABORTED
    before = GameDailyStats.objects.get(game=game).sessions
    close_session(request, created.id)
    assert GameDailyStats.objects.get(game=game).sessions == before


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_expired_heartbeat_credits_server_duration() -> None:
    game = _game(technical_id="expired_credit_game")
    user = User.objects.create_user(login="jack", password="correct horse battery staple")
    session = _session(game, user=user, credited_ms=15_000)
    stale = timezone.now() - timedelta(seconds=2000)
    GameSession.objects.filter(pk=session.pk).update(
        activated_at=stale,
        last_heartbeat_at=stale,
    )
    request = RequestFactory().post("/")
    request.user = user
    with pytest.raises(SessionError) as exc:
        heartbeat(request, session.pk)
    assert exc.value.code == "E_SESSION_EXPIRED"
    assert GamePlayCredit.objects.filter(game=game, subject_id=user.id).exists()
    assert GameDailyStats.objects.get(game=game).unique_sessions == 1


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_daily_stats_use_utc_dates() -> None:
    game = _game(technical_id="utc_popularity_game")
    first_user = User.objects.create_user(login="erin", password="correct horse battery staple")
    second_user = User.objects.create_user(login="frank", password="correct horse battery staple")
    first = _session(game, user=first_user)
    second = _session(game, user=second_user)
    first_time = datetime(2026, 1, 1, 23, 59, tzinfo=UTC)
    second_time = datetime(2026, 1, 2, 0, 1, tzinfo=UTC)
    assert credit_session(first, duration_ms=30_000, completed=False, now=first_time)
    assert credit_session(second, duration_ms=30_000, completed=False, now=second_time)
    assert GameDailyStats.objects.filter(game=game).count() == 2


@pytest.mark.django_db(transaction=True)
@override_settings(CACHES=LOCMEM_CACHES)
def test_parallel_close_of_two_sessions_credits_once() -> None:
    game = _game(technical_id="race_popularity_game")
    user = User.objects.create_user(login="gina", password="correct horse battery staple")
    sessions = [_session(game, user=user), _session(game, user=user)]
    barrier = threading.Barrier(2)

    def worker(session_pk) -> None:
        request = RequestFactory().post("/")
        request.user = user
        try:
            barrier.wait(timeout=10)
            close_session(request, session_pk)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker, args=(session.pk,)) for session in sessions]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    stats = GameDailyStats.objects.get(game=game, date=timezone.now().date())
    assert stats.sessions == 2
    assert stats.unique_sessions == 1
