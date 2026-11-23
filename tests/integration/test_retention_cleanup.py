"""Retention cleanup for sessions, credits, drafts and guest storage (§2.22).

Covers the RETENTION_PROPOSAL §D horizons, the result-linked-session
exclusion (``GameResult`` PROTECT), the guest-storage TTL refresh and
at-least-once rerun idempotency (R-036).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from django.conf import settings
from django.core.cache import caches
from django.test import Client, override_settings
from django.utils import timezone

from apps.accounts.models import AnonymousIdentity, User
from apps.catalog.models import Game, GameVersion, Genre
from apps.gameplay.models import GamePlayCredit, GameResult, GameSession, GameStorage
from apps.gameplay.services.retention import (
    purge_expired_guest_storage,
    purge_play_credits,
    purge_terminal_sessions,
)
from apps.gameplay.tasks import cleanup_gameplay_retention
from apps.pipeline.models import GameImportDraft, ZipExtractionJob
from apps.pipeline.services.retention import purge_expired_import_drafts
from apps.pipeline.tasks import cleanup_pipeline_retention

LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "throttle": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


def _game(technical_id: str, *, published: bool = True) -> Game:
    genre = Genre.objects.create(code=f"genre-{technical_id}")
    game = Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=f"slug-{technical_id}",
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED if published else Game.STATUS_DRAFT,
        published_at=timezone.now() if published else None,
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


def _session(game: Game, state: str, *, updated_at: datetime) -> GameSession:
    session = GameSession.objects.create(
        game=game,
        game_version=game.current_version,
        subject_type=GameSession.SUBJECT_USER,
        subject_id=uuid4(),
        mode=GameSession.MODE_USER,
        state=state,
        seed="retention-seed",
    )
    # auto_now ignores an explicit value on create; backdate through update().
    GameSession.objects.filter(pk=session.pk).update(updated_at=updated_at)
    return session


def _result(game: Game, session: GameSession) -> GameResult:
    return GameResult.objects.create(
        session=session,
        game=game,
        game_version=game.current_version,
        subject_type=GameResult.SUBJECT_DELETED,
        user=None,
        anon=None,
        epoch=1,
        value=10,
        unit="score",
        duration_ms=1000,
        idempotency_key=f"key-{uuid4()}",
    )


def _credit(game: Game, *, last_credited_at: datetime) -> GamePlayCredit:
    return GamePlayCredit.objects.create(
        game=game,
        subject_type="user",
        subject_id=uuid4(),
        last_credited_at=last_credited_at,
    )


def _draft(*, updated_at: datetime) -> GameImportDraft:
    draft = GameImportDraft.objects.create(
        package_hash="c" * 64,
        original_filename="retention.zip",
    )
    GameImportDraft.objects.filter(pk=draft.pk).update(updated_at=updated_at)
    return draft


def _identity(suffix: str) -> AnonymousIdentity:
    return AnonymousIdentity.objects.create(
        token_hash=f"retention-identity-{suffix}",
        expires_at=timezone.now() + timedelta(days=90),
    )


def _storage(
    game: Game,
    *,
    anon: AnonymousIdentity | None = None,
    user: User | None = None,
    expires_at: datetime | None = None,
) -> GameStorage:
    return GameStorage.objects.create(
        game=game,
        subject_type=GameStorage.SUBJECT_ANON if anon is not None else GameStorage.SUBJECT_USER,
        anon=anon,
        user=user,
        data={"save": 1},
        expires_at=expires_at,
    )


@pytest.mark.django_db
def test_terminal_session_horizon_and_state_filter() -> None:
    now = timezone.now()
    game = _game("retention_sessions")
    old = now - timedelta(days=30, seconds=1)

    purged = [
        _session(game, state, updated_at=old)
        for state in (
            GameSession.STATE_FINISHED,
            GameSession.STATE_EXPIRED,
            GameSession.STATE_ABORTED,
        )
    ]
    boundary = _session(game, GameSession.STATE_FINISHED, updated_at=now - timedelta(days=30))
    fresh = _session(game, GameSession.STATE_FINISHED, updated_at=now - timedelta(days=29))
    active = _session(game, GameSession.STATE_ACTIVE, updated_at=old)
    created = _session(game, GameSession.STATE_CREATED, updated_at=old)

    assert purge_terminal_sessions(now=now) == 3
    for session in purged:
        assert not GameSession.objects.filter(pk=session.pk).exists()
    for session in (boundary, fresh, active, created):
        assert GameSession.objects.filter(pk=session.pk).exists()


@pytest.mark.django_db
def test_result_linked_sessions_are_excluded_and_results_survive() -> None:
    now = timezone.now()
    game = _game("retention_results")
    old = now - timedelta(days=31)

    finished = _session(game, GameSession.STATE_FINISHED, updated_at=old)
    finished_result = _result(game, finished)
    expired = _session(game, GameSession.STATE_EXPIRED, updated_at=old)
    expired_result = _result(game, expired)
    unreferenced = _session(game, GameSession.STATE_FINISHED, updated_at=old)

    assert purge_terminal_sessions(now=now) == 1
    assert GameSession.objects.filter(pk=finished.pk).exists()
    assert GameSession.objects.filter(pk=expired.pk).exists()
    assert not GameSession.objects.filter(pk=unreferenced.pk).exists()
    assert GameResult.objects.filter(pk=finished_result.pk).exists()
    assert GameResult.objects.filter(pk=expired_result.pk).exists()


@pytest.mark.django_db
def test_play_credit_horizon() -> None:
    now = timezone.now()
    game = _game("retention_credits")
    old = _credit(game, last_credited_at=now - timedelta(days=90, seconds=1))
    boundary = _credit(game, last_credited_at=now - timedelta(days=90))
    fresh = _credit(game, last_credited_at=now - timedelta(days=89))

    assert purge_play_credits(now=now) == 1
    assert not GamePlayCredit.objects.filter(pk=old.pk).exists()
    assert GamePlayCredit.objects.filter(pk=boundary.pk).exists()
    assert GamePlayCredit.objects.filter(pk=fresh.pk).exists()


@pytest.mark.django_db
def test_import_draft_horizon_and_cascaded_jobs() -> None:
    now = timezone.now()
    old = _draft(updated_at=now - timedelta(days=7, seconds=1))
    job = ZipExtractionJob.objects.create(draft=old, package_hash=old.package_hash)
    boundary = _draft(updated_at=now - timedelta(days=7))
    fresh = _draft(updated_at=now - timedelta(days=6))

    assert purge_expired_import_drafts(now=now) == 1
    assert not GameImportDraft.objects.filter(pk=old.pk).exists()
    assert not ZipExtractionJob.objects.filter(pk=job.pk).exists()
    assert GameImportDraft.objects.filter(pk=boundary.pk).exists()
    assert GameImportDraft.objects.filter(pk=fresh.pk).exists()


@pytest.mark.django_db
def test_guest_storage_expiry_horizon_and_user_rows() -> None:
    now = timezone.now()
    game = _game("retention_storage")
    user = User.objects.create_user(login="storage-owner", password="correct horse battery staple")
    expired = _storage(
        game,
        anon=_identity("expired"),
        expires_at=now - timedelta(seconds=1),
    )
    future = _storage(
        game,
        anon=_identity("future"),
        expires_at=now + timedelta(hours=1),
    )
    user_row = _storage(game, user=user, expires_at=None)

    assert purge_expired_guest_storage(now=now) == 1
    assert not GameStorage.objects.filter(pk=expired.pk).exists()
    assert GameStorage.objects.filter(pk=future.pk).exists()
    assert GameStorage.objects.filter(pk=user_row.pk).exists()


def _client() -> tuple[Client, str]:
    client = Client(enforce_csrf_checks=True)
    page = client.get("/en/auth/login/")
    assert page.status_code == 200
    match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.content.decode())
    assert match is not None
    return client, match.group(1)


def _guest_client(game: Game) -> tuple[Client, str]:
    client, csrf = _client()
    created = client.post(
        "/api/v1/sessions",
        data=json.dumps({"game_id": game.technical_id}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert created.status_code == 201, created.content
    payload = created.json()
    activated = client.post(
        f"/api/v1/sessions/{payload['session_id']}/activate",
        data=json.dumps({"ticket": payload["ticket"], "binding_nonce": "n" * 32}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert activated.status_code == 200, activated.content
    return client, csrf


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_guest_storage_ttl_refresh_prevents_cleanup() -> None:
    caches["default"].clear()
    caches["throttle"].clear()
    game = _game("retention_storage_ttl")
    client, csrf = _guest_client(game)
    response = client.put(
        f"/api/v1/games/{game.technical_id}/storage",
        data=json.dumps({"save": 1}),
        content_type="application/json",
        HTTP_IF_MATCH="*",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 200, response.content
    row = GameStorage.objects.get(game=game, subject_type=GameStorage.SUBJECT_ANON)

    # Access refresh: the 90-day TTL restarts from the current request.
    GameStorage.objects.filter(pk=row.pk).update(expires_at=timezone.now() + timedelta(hours=1))
    fetched = client.get(f"/api/v1/games/{game.technical_id}/storage")
    assert fetched.status_code == 200, fetched.content
    row.refresh_from_db()
    assert row.expires_at is not None
    assert row.expires_at > timezone.now() + timedelta(days=89)

    assert purge_expired_guest_storage() == 0
    assert GameStorage.objects.filter(pk=row.pk).exists()


@pytest.mark.django_db
def test_tasks_return_counts_and_rerun_is_idempotent() -> None:
    now = timezone.now()
    game = _game("retention_rerun")
    _session(game, GameSession.STATE_FINISHED, updated_at=now - timedelta(days=31))
    _credit(game, last_credited_at=now - timedelta(days=91))
    _storage(
        game,
        anon=_identity("rerun"),
        expires_at=now - timedelta(minutes=1),
    )
    _draft(updated_at=now - timedelta(days=8))

    assert cleanup_gameplay_retention() == {
        "game_sessions": 1,
        "game_play_credits": 1,
        "guest_game_storage": 1,
    }
    assert cleanup_pipeline_retention() == {"game_import_drafts": 1}

    assert cleanup_gameplay_retention() == {
        "game_sessions": 0,
        "game_play_credits": 0,
        "guest_game_storage": 0,
    }
    assert cleanup_pipeline_retention() == {"game_import_drafts": 0}


def test_retention_tasks_registered_in_beat_schedule() -> None:
    schedule = settings.CELERY_BEAT_SCHEDULE
    gameplay = schedule["gameplay-cleanup-retention"]
    pipeline = schedule["pipeline-cleanup-retention"]
    assert gameplay["task"] == "apps.gameplay.tasks.cleanup_gameplay_retention"
    assert pipeline["task"] == "apps.pipeline.tasks.cleanup_pipeline_retention"
    assert gameplay["schedule"] == 60 * 60 * 24
    assert pipeline["schedule"] == 60 * 60 * 24
    assert cleanup_gameplay_retention.name == gameplay["task"]
    assert cleanup_pipeline_retention.name == pipeline["task"]
