"""Recovery checks for Live Room after repeats and connection restarts."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.cache import caches
from django.db import connections
from django.http import HttpResponse
from django.test import RequestFactory, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Game, GameVersion, Genre
from apps.rooms.models import Room, RoomCommand, RoomCreateRequest, RoomMember
from apps.rooms.services.rooms import (
    RoomError,
    create_room,
    execute_command,
    join_room,
    read_room,
)
from apps.rooms.tasks import expire_rooms_task

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
    genre = Genre.objects.create(code="live_recovery_genre")
    game = Game.objects.create(
        technical_id="whos_undercover",
        host_label="whos-undercover-recovery.games.test",
        slug="whos-undercover-recovery",
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


def _user(login: str) -> User:
    return User.objects.create_user(login=login, password="correct horse battery staple")


def _request(user: User):
    request = RequestFactory().post("/")
    request.user = user
    return request


def _active_game() -> tuple[Room, list[User]]:
    _game()
    users = [_user(f"recovery_{index}") for index in range(4)]
    room, _member = create_room(
        _request(users[0]),
        HttpResponse(),
        game_id="whos_undercover",
        max_players=4,
        name="Host",
    )
    for user in users[1:]:
        join_room(_request(user), HttpResponse(), code=room.code, name=user.login)
        execute_command(
            _request(user),
            room.id,
            command="ready",
            payload={"ready": True},
            request_id=None,
            expected_version=None,
        )
    execute_command(
        _request(users[0]),
        room.id,
        command="start",
        payload={},
        request_id=None,
        expected_version=None,
    )
    return room, users


@pytest.mark.django_db
def test_repeated_expiry_and_cleanup_are_idempotent() -> None:
    room, _users = _active_game()
    Room.objects.filter(pk=room.pk).update(
        expires_at=timezone.now() - timedelta(seconds=1),
        last_activity_at=timezone.now() - timedelta(seconds=1),
    )
    RoomCreateRequest.objects.create(
        key=__import__("uuid").UUID("018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c20"),
        subject_type=Room.SUBJECT_USER,
        subject_id=_users[0].pk,
        payload_hash="a" * 64,
        room=room,
        expires_at=timezone.now() - timedelta(seconds=1),
    )

    first = expire_rooms_task.run()
    second = expire_rooms_task.run()

    assert first["expired"] >= 1
    assert second["expired"] == 0
    assert second["cleaned"] == 0
    assert not RoomCreateRequest.objects.exists()
    current = Room.objects.get(pk=room.pk)
    assert current.status == Room.STATUS_EXPIRED
    assert RoomMember.objects.filter(room=current, role=RoomMember.ROLE_HOST).count() == 1


@pytest.mark.django_db
def test_failed_command_does_not_leave_partial_state() -> None:
    _game()
    users = [_user(f"recovery_failure_{index}") for index in range(3)]
    room, _member = create_room(
        _request(users[0]),
        HttpResponse(),
        game_id="whos_undercover",
        max_players=4,
        name="Host",
    )
    original_version = room.version
    original_state = dict(room.state)

    with pytest.raises(RoomError):
        execute_command(
            _request(users[0]),
            room.id,
            command="start",
            payload={},
            request_id=__import__("uuid").UUID("018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c21"),
            expected_version=original_version,
        )

    room.refresh_from_db()
    assert room.version == original_version
    assert room.state == original_state
    assert not RoomCommand.objects.filter(room=room).exists()


@pytest.mark.django_db(transaction=True)
def test_room_state_survives_a_database_connection_restart() -> None:
    room, users = _active_game()
    current = Room.objects.get(pk=room.pk)
    roles_before = {
        str(player["id"]): (player["role"], player["word"]) for player in current.state["players"]
    }
    version_before = current.version

    connections.close_all()

    restored = Room.objects.get(pk=room.pk)
    assert restored.version == version_before
    assert {
        str(player["id"]): (player["role"], player["word"]) for player in restored.state["players"]
    } == roles_before
    snapshot = read_room(_request(users[0]), room.id)
    assert snapshot["you"]["role"] == next(
        player["role"]
        for player in restored.state["players"]
        if player["id"] == snapshot["you"]["memberId"]
    )
    assert snapshot["room"]["id"] == str(room.id)
