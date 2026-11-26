"""Server-side idempotency for Live Room creation.

These tests exercise the real PostgreSQL service and API. A create key is a
client-generated intent identifier, never a room access token: replay is
accepted only for the same subject and the same create payload.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from django.core.cache import caches
from django.db import connections
from django.http import HttpResponse
from django.test import Client, RequestFactory, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Game, GameVersion, Genre
from apps.rooms.models import Room, RoomCreateRequest, RoomMember
from apps.rooms.services.rooms import RoomError, cleanup_create_requests, create_room

API = "/api/v1/rooms"
LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "throttle": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


@pytest.fixture(autouse=True)
def _local_caches():
    with override_settings(CACHES=LOCMEM_CACHES):
        caches["default"].clear()
        caches["throttle"].clear()
        yield
        caches["default"].clear()
        caches["throttle"].clear()


def _game() -> Game:
    genre = Genre.objects.create(code="live_idempotency_genre")
    game = Game.objects.create(
        technical_id="whos_undercover",
        host_label="whos-undercover-idempotency.games.test",
        slug="whos-undercover-idempotency",
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
        supported_languages=["en", "ru"],
    )
    game.current_version = version
    game.save(update_fields=["current_version"])
    return game


def _client() -> tuple[Client, str]:
    client = Client(enforce_csrf_checks=True)
    page = client.get("/en/auth/login/")
    assert page.status_code == 200
    match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.content.decode())
    assert match is not None
    return client, match.group(1)


def _post(client: Client, csrf: str, payload: dict[str, object]):
    return client.post(
        API,
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )


def _payload(**overrides: object) -> dict[str, object]:
    return {
        "game_id": "whos_undercover",
        "max_players": 4,
        "undercover_count": 1,
        "mr_white": False,
        "name": "Host",
        "requestId": str(uuid4()),
        **overrides,
    }


def _request(user: User):
    request = RequestFactory().post("/")
    request.user = user
    return request


@pytest.mark.django_db
def test_same_key_and_payload_replays_the_same_room() -> None:
    _game()
    client, csrf = _client()
    payload = _payload()

    first = _post(client, csrf, payload)
    second = _post(client, csrf, payload)

    assert first.status_code == 201, first.content
    assert second.status_code == 201, second.content
    assert first.json()["room"]["id"] == second.json()["room"]["id"]
    assert Room.objects.count() == 1
    assert RoomMember.objects.filter(role=RoomMember.ROLE_HOST).count() == 1
    assert RoomCreateRequest.objects.count() == 1


@pytest.mark.django_db
def test_same_key_with_different_payload_conflicts() -> None:
    _game()
    client, csrf = _client()
    key = str(uuid4())
    first = _post(client, csrf, _payload(requestId=key, name="First"))
    second = _post(client, csrf, _payload(requestId=key, name="Second"))

    assert first.status_code == 201, first.content
    assert second.status_code == 409
    assert second.json()["code"] == "E_IDEMPOTENCY_CONFLICT"
    assert Room.objects.count() == 1


@pytest.mark.django_db
def test_different_keys_with_same_payload_create_different_rooms() -> None:
    _game()
    client, csrf = _client()

    first = _post(client, csrf, _payload())
    second = _post(client, csrf, _payload())

    assert first.status_code == 201, first.content
    assert second.status_code == 201, second.content
    assert first.json()["room"]["id"] != second.json()["room"]["id"]
    assert Room.objects.count() == 2


@pytest.mark.django_db
def test_same_key_from_another_subject_cannot_read_or_take_the_room() -> None:
    _game()
    owner, owner_csrf = _client()
    stranger, stranger_csrf = _client()
    payload = _payload()

    created = _post(owner, owner_csrf, payload)
    assert created.status_code == 201, created.content
    room_id = created.json()["room"]["id"]

    replay = _post(stranger, stranger_csrf, payload)
    assert replay.status_code == 409
    assert replay.json()["code"] == "E_IDEMPOTENCY_CONFLICT"
    assert stranger.get(f"{API}/{room_id}").status_code == 403
    assert Room.objects.count() == 1
    assert RoomMember.objects.filter(role=RoomMember.ROLE_HOST).count() == 1


@pytest.mark.django_db
def test_lost_anonymous_cookie_does_not_duplicate_or_grant_access() -> None:
    _game()
    owner, owner_csrf = _client()
    payload = _payload()

    created = _post(owner, owner_csrf, payload)
    assert created.status_code == 201, created.content
    room_id = created.json()["room"]["id"]

    # Simulate a browser that lost the anonymous Set-Cookie and retries the
    # same intent: the key is not a bearer token, so it must not receive the
    # room or create a second one.
    lost_cookie, lost_csrf = _client()
    replay = _post(lost_cookie, lost_csrf, payload)
    assert replay.status_code == 409
    assert replay.json()["code"] == "E_IDEMPOTENCY_CONFLICT"
    assert lost_cookie.get(f"{API}/{room_id}").status_code == 403

    # The original identity still receives the committed room.
    same = _post(owner, owner_csrf, payload)
    assert same.status_code == 201, same.content
    assert same.json()["room"]["id"] == room_id
    assert Room.objects.count() == 1


@pytest.mark.django_db
def test_authenticated_user_replays_and_other_user_conflicts() -> None:
    _game()
    owner = User.objects.create_user(login="idem_owner", password="correct horse battery staple")
    other = User.objects.create_user(login="idem_other", password="correct horse battery staple")
    payload = _payload(requestId=str(uuid4()))

    owner_client, owner_csrf = _client()
    owner_client.force_login(owner)
    first = _post(owner_client, owner_csrf, payload)
    second = _post(owner_client, owner_csrf, payload)
    assert first.status_code == 201, first.content
    assert second.status_code == 201, second.content
    assert first.json()["room"]["id"] == second.json()["room"]["id"]

    other_client, other_csrf = _client()
    other_client.force_login(other)
    conflict = _post(other_client, other_csrf, payload)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "E_IDEMPOTENCY_CONFLICT"
    assert Room.objects.count() == 1


@pytest.mark.django_db
def test_expired_record_does_not_create_a_duplicate() -> None:
    _game()
    client, csrf = _client()
    payload = _payload()
    created = _post(client, csrf, payload)
    assert created.status_code == 201, created.content
    record = RoomCreateRequest.objects.get()
    record.expires_at = timezone.now() - timedelta(seconds=1)
    record.save(update_fields=["expires_at"])

    replay = _post(client, csrf, payload)
    assert replay.status_code == 409
    assert replay.json()["code"] == "E_IDEMPOTENCY_EXPIRED"
    assert Room.objects.count() == 1
    assert cleanup_create_requests() == 1
    assert not RoomCreateRequest.objects.exists()


@pytest.mark.django_db
def test_deleted_room_returns_gone_without_recreating() -> None:
    _game()
    client, csrf = _client()
    payload = _payload()
    created = _post(client, csrf, payload)
    assert created.status_code == 201, created.content
    room = Room.objects.get()
    room.delete()

    replay = _post(client, csrf, payload)
    assert replay.status_code == 410
    assert replay.json()["code"] == "E_IDEMPOTENCY_GONE"
    assert Room.objects.count() == 0


@pytest.mark.django_db
def test_failed_create_before_commit_leaves_no_idempotency_record() -> None:
    _game()
    client, csrf = _client()
    key = str(uuid4())

    failed = _post(
        client,
        csrf,
        _payload(requestId=key, game_id="missing_game"),
    )
    assert failed.status_code == 404
    assert not RoomCreateRequest.objects.exists()

    retried = _post(client, csrf, _payload(requestId=key))
    assert retried.status_code == 201, retried.content
    assert Room.objects.count() == 1
    assert RoomCreateRequest.objects.count() == 1


@pytest.mark.django_db
def test_room_code_collision_is_retried_without_orphan_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _game()
    existing_client, existing_csrf = _client()
    existing = _post(existing_client, existing_csrf, _payload())
    assert existing.status_code == 201, existing.content
    existing_code = existing.json()["room"]["code"]

    client, csrf = _client()
    key = str(uuid4())
    codes = iter([existing_code, "ZZZZZZ"])
    monkeypatch.setattr("apps.rooms.services.rooms._room_code", lambda: next(codes))

    created = _post(client, csrf, _payload(requestId=key))
    assert created.status_code == 201, created.content
    assert created.json()["room"]["code"] == "ZZZZZZ"
    assert Room.objects.count() == 2
    assert RoomCreateRequest.objects.filter(key=key).count() == 1
    assert RoomMember.objects.filter(room_id=created.json()["room"]["id"]).count() == 1


@pytest.mark.django_db(transaction=True)
def test_parallel_same_key_creates_one_room() -> None:
    _game()
    user = User.objects.create_user(login="idem_parallel", password="correct horse battery staple")
    key = uuid4()
    barrier = Barrier(2)

    def worker() -> Room | RoomError:
        barrier.wait(timeout=20)
        try:
            room, _member = create_room(
                _request(user),
                HttpResponse(),
                game_id="whos_undercover",
                max_players=4,
                request_id=key,
            )
            return room
        except RoomError as exc:
            return exc
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _index: worker(), range(2)))

    rooms = [outcome for outcome in outcomes if isinstance(outcome, Room)]
    errors = [outcome for outcome in outcomes if isinstance(outcome, RoomError)]
    assert len(rooms) == 2
    assert {room.pk for room in rooms} == {Room.objects.get().pk}
    assert errors == []
    assert Room.objects.count() == 1
    assert RoomMember.objects.filter(role=RoomMember.ROLE_HOST).count() == 1


@pytest.mark.django_db(transaction=True)
def test_parallel_same_key_with_different_payload_conflicts() -> None:
    _game()
    user = User.objects.create_user(
        login="idem_parallel_payload", password="correct horse battery staple"
    )
    key = uuid4()
    barrier = Barrier(2)

    def worker(name: str) -> tuple[str, object]:
        barrier.wait(timeout=20)
        try:
            room, _member = create_room(
                _request(user),
                HttpResponse(),
                game_id="whos_undercover",
                max_players=4,
                name=name,
                request_id=key,
            )
            return ("room", room.pk)
        except RoomError as exc:
            return ("error", exc.code)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(worker, ["One", "Two"]))

    assert sorted(status for status, _value in outcomes) == ["error", "room"]
    assert Room.objects.count() == 1
    assert RoomCreateRequest.objects.count() == 1
