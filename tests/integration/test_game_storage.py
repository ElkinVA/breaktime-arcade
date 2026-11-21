from __future__ import annotations

import json
import re
import threading
import time
from datetime import timedelta

import pytest
from django.core.cache import caches
from django.db import connections
from django.test import Client, RequestFactory, override_settings
from django.utils import timezone

from apps.accounts.models import AnonymousIdentity, User
from apps.accounts.services.anonymous import COOKIE_NAME
from apps.accounts.tasks import cleanup_expired_account_records
from apps.catalog.models import Game, GameVersion, Genre
from apps.gameplay.models import GameStorage
from apps.gameplay.services.sessions import SessionError
from apps.gameplay.services.storage import delete_user_storage, put_storage

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


def _game(*, technical_id: str = "storage_game", published: bool = True) -> Game:
    genre = Genre.objects.create(code=f"genre_{technical_id}")
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


def _url(game: Game) -> str:
    return f"/api/v1/games/{game.technical_id}/storage"


def _put(client: Client, csrf: str, game: Game, data: object, *, if_match: str = "*"):
    return client.put(
        _url(game),
        data=json.dumps(data),
        content_type="application/json",
        HTTP_IF_MATCH=if_match,
        HTTP_X_CSRFTOKEN=csrf,
    )


def _open_session(client: Client, csrf: str, game: Game) -> str:
    response = client.post(
        "/api/v1/sessions",
        data=json.dumps({"game_id": game.technical_id}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 201, response.content
    created = response.json()
    activated = client.post(
        f"/api/v1/sessions/{created['session_id']}/activate",
        data=json.dumps({"ticket": created["ticket"], "binding_nonce": "n" * 32}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert activated.status_code == 200, activated.content
    return str(created["session_id"])


def _guest_with_identity(game: Game) -> tuple[Client, str]:
    client, csrf = _client()
    _open_session(client, csrf, game)
    assert COOKIE_NAME in client.cookies
    return client, csrf


@pytest.mark.django_db
def test_storage_bytes_trigger_recomputes_forged_value() -> None:
    game = _game(technical_id="bytes_trigger_game")
    user = User.objects.create_user(login="bytes-user", password="correct horse battery staple")
    row = GameStorage.objects.create(
        game=game,
        subject_type=GameStorage.SUBJECT_USER,
        user=user,
        data={"save": {"level": 1}},
        bytes=0,
    )
    row.refresh_from_db()
    assert row.bytes > 0

    GameStorage.objects.filter(pk=row.pk).update(bytes=0)
    row.refresh_from_db()
    assert row.bytes > 0


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_user_document_revision_and_etag() -> None:
    game = _game()
    user = User.objects.create_user(login="alice", password="correct horse battery staple")
    client, csrf = _client(user)
    _open_session(client, csrf, game)
    created = _put(client, csrf, game, {"save": {"level": 1}})
    assert created.status_code == 200, created.content
    assert created.json() == {"data": {"save": {"level": 1}}, "revision": 1}
    assert created["ETag"] == '"1"'
    row = GameStorage.objects.get(game=game, user=user)
    assert row.bytes > 0
    assert row.bytes <= 65536

    fetched = client.get(_url(game))
    assert fetched.status_code == 200
    assert fetched.json()["data"] == {"save": {"level": 1}}
    assert fetched["ETag"] == '"1"'

    updated = _put(client, csrf, game, {"save": {"level": 2}}, if_match='"1"')
    assert updated.status_code == 200
    assert updated.json()["revision"] == 2
    assert updated["ETag"] == '"2"'

    conflict = _put(client, csrf, game, {"save": {"level": 3}}, if_match='"1"')
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "E_STORAGE_CONFLICT"

    wildcard = _put(client, csrf, game, {"save": {"level": 3}}, if_match="*")
    assert wildcard.status_code == 409
    assert wildcard.json()["code"] == "E_STORAGE_CONFLICT"

    nan = _put(client, csrf, game, {"value": float("nan")}, if_match='"2"')
    assert nan.status_code == 400
    assert nan.json()["code"] == "E_INVALID_REQUEST"


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_put_requires_if_match_and_csrf() -> None:
    game = _game(technical_id="ifmatch_game")
    user = User.objects.create_user(login="bob", password="correct horse battery staple")
    client, csrf = _client(user)
    missing = client.put(
        _url(game),
        data=json.dumps({"a": 1}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert missing.status_code == 409
    no_csrf = client.put(
        _url(game),
        data=json.dumps({"a": 1}),
        content_type="application/json",
        HTTP_IF_MATCH="*",
    )
    assert no_csrf.status_code == 403


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_storage_requires_active_session_and_session_throttle() -> None:
    game = _game(technical_id="session_bound_storage_game")
    user = User.objects.create_user(login="nora", password="correct horse battery staple")
    client, csrf = _client(user)
    without_session = _put(client, csrf, game, {"a": 1})
    assert without_session.status_code == 403
    assert without_session.json()["code"] == "E_SESSION_INVALID"

    session_id = _open_session(client, csrf, game)
    key = f"throttle_storage_session:{session_id}"
    try:
        caches["throttle"].set(key, [time.time()] * 60, timeout=60)
        throttled = _put(client, csrf, game, {"a": 1})
    finally:
        caches["throttle"].delete(key)
    assert throttled.status_code == 429
    assert throttled.json()["code"] == "E_RATE_LIMIT"


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_quota_and_structure_limits() -> None:
    game = _game(technical_id="quota_game")
    user = User.objects.create_user(login="carol", password="correct horse battery staple")
    client, csrf = _client(user)
    too_big = _put(client, csrf, game, {"blob": "x" * 70_000})
    assert too_big.status_code == 413
    assert too_big.json()["code"] == "E_STORAGE_QUOTA"

    too_many_keys = _put(client, csrf, game, {f"k{i}": 1 for i in range(257)})
    assert too_many_keys.status_code == 413

    deep: dict[str, object] = {}
    cursor = deep
    for _ in range(10):
        cursor["n"] = {}
        cursor = cursor["n"]  # type: ignore[assignment]
    assert _put(client, csrf, game, deep).status_code == 400

    long_key = _put(client, csrf, game, {"k" * 129: 1})
    assert long_key.status_code == 400


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_guest_ttl_expiry_resets_document() -> None:
    game = _game(technical_id="guest_storage_game")
    client, csrf = _guest_with_identity(game)
    created = _put(client, csrf, game, {"save": 1})
    assert created.status_code == 200
    row = GameStorage.objects.get(game=game, subject_type=GameStorage.SUBJECT_ANON)
    assert row.expires_at is not None
    GameStorage.objects.filter(pk=row.pk).update(expires_at=timezone.now() - timedelta(seconds=1))

    fetched = client.get(_url(game))
    assert fetched.status_code == 200
    assert fetched.json() == {"data": {}, "revision": 0}
    assert not GameStorage.objects.filter(pk=row.pk).exists()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_storage_is_isolated_per_subject_and_game() -> None:
    game = _game(technical_id="isolation_game")
    other_game = _game(technical_id="isolation_other_game")
    first = User.objects.create_user(login="dave", password="correct horse battery staple")
    second = User.objects.create_user(login="erin", password="correct horse battery staple")
    first_client, first_csrf = _client(first)
    second_client, second_csrf = _client(second)
    _open_session(first_client, first_csrf, game)
    _open_session(second_client, second_csrf, game)
    _open_session(first_client, first_csrf, other_game)
    assert _put(first_client, first_csrf, game, {"owner": 1}).status_code == 200
    assert _put(second_client, second_csrf, game, {"owner": 2}).status_code == 200
    assert _put(first_client, first_csrf, other_game, {"game": 2}).status_code == 200

    assert first_client.get(_url(game)).json()["data"] == {"owner": 1}
    assert second_client.get(_url(game)).json()["data"] == {"owner": 2}
    assert first_client.get(_url(other_game)).json()["data"] == {"game": 2}


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_unpublished_game_and_missing_identity() -> None:
    draft = _game(technical_id="draft_storage_game", published=False)
    user = User.objects.create_user(login="frank", password="correct horse battery staple")
    client, csrf = _client(user)
    assert _put(client, csrf, draft, {"a": 1}).status_code == 404

    anonymous = Client(enforce_csrf_checks=True)
    response = anonymous.get(_url(draft))
    assert response.status_code == 404


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_anonymous_without_identity_is_rejected() -> None:
    game = _game(technical_id="anonymous_storage_game")
    anonymous = Client(enforce_csrf_checks=True)
    response = anonymous.get(_url(game))
    assert response.status_code == 403
    assert response.json()["code"] == "E_AUTH_REQUIRED"


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_expired_guest_cleanup_removes_storage() -> None:
    game = _game(technical_id="cleanup_storage_game")
    client, csrf = _guest_with_identity(game)
    assert _put(client, csrf, game, {"save": 1}).status_code == 200
    identity = AnonymousIdentity.objects.filter(game_storage__game=game).distinct().get()
    AnonymousIdentity.objects.filter(pk=identity.pk).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    result = cleanup_expired_account_records()
    assert result["game_storage"] >= 1
    assert not GameStorage.objects.filter(anon_id=identity.pk).exists()
    assert not AnonymousIdentity.objects.filter(pk=identity.pk).exists()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_unquoted_if_match_is_accepted() -> None:
    game = _game(technical_id="unquoted_storage_game")
    user = User.objects.create_user(login="olga", password="correct horse battery staple")
    client, csrf = _client(user)
    _open_session(client, csrf, game)
    assert _put(client, csrf, game, {"a": 1}).status_code == 200
    response = _put(client, csrf, game, {"a": 2}, if_match="1")
    assert response.status_code == 200
    assert response.json()["revision"] == 2


@pytest.mark.django_db(transaction=True)
@override_settings(CACHES=LOCMEM_CACHES)
def test_concurrent_create_has_single_winner() -> None:
    game = _game(technical_id="race_storage_game")
    user = User.objects.create_user(login="pavel", password="correct horse battery staple")
    client, csrf = _client(user)
    _open_session(client, csrf, game)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        request = RequestFactory().post("/")
        request.user = user
        try:
            barrier.wait(timeout=10)
            put_storage(request, game.technical_id, data={"a": 1}, if_match="*")
        except SessionError as exc:
            with lock:
                outcomes.append(exc.code)
        else:
            with lock:
                outcomes.append("ok")
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert sorted(outcomes) == ["E_STORAGE_CONFLICT", "ok"]
    assert GameStorage.objects.filter(game=game, user=user).count() == 1


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_account_deletion_removes_storage() -> None:
    game = _game(technical_id="delete_storage_game")
    user = User.objects.create_user(login="grace", password="correct horse battery staple")
    client, csrf = _client(user)
    _open_session(client, csrf, game)
    assert _put(client, csrf, game, {"save": 1}).status_code == 200
    assert GameStorage.objects.filter(user=user).exists()
    delete_user_storage(user)
    assert not GameStorage.objects.filter(user=user).exists()
