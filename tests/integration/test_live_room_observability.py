"""Observability and log-redaction checks for Live Room."""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from uuid import UUID

import pytest
from django.core.cache import caches
from django.http import HttpResponse
from django.test import RequestFactory, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Game, GameVersion, Genre
from apps.core.logging import JsonFormatter, set_request_id
from apps.rooms.models import Room, RoomMember
from apps.rooms.services.rooms import (
    RoomError,
    create_room,
    execute_command,
    join_room,
    leave_room,
    read_room,
)

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
    genre = Genre.objects.create(code="live_observability_genre")
    game = Game.objects.create(
        technical_id="whos_undercover",
        host_label="whos-undercover-observability.games.test",
        slug="whos-undercover-observability",
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


def _room_with_guest() -> tuple[Room, User, User, RoomMember]:
    _game()
    host = _user("observability_host")
    guest = _user("observability_guest")
    room, host_member = create_room(
        _request(host),
        HttpResponse(),
        game_id="whos_undercover",
        max_players=4,
        name="Sensitive Host",
    )
    _room, guest_member = join_room(
        _request(guest),
        HttpResponse(),
        code=room.code,
        name="Sensitive Guest",
    )
    return room, host, guest, guest_member


def _forbidden_values(room) -> set[str]:
    values: set[str] = set()
    for player in room.state.get("players", []):
        for key in ("role", "word", "revealed_role"):
            value = player.get(key)
            if value:
                values.add(str(value))
    values.update(room.state.get("votes", {}).keys())
    values.update(room.state.get("votes", {}).values())
    return values


@pytest.mark.django_db
def test_room_logs_do_not_contain_names_roles_words_votes_or_keys(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="apps.rooms")
    room, host, guest, _guest_member = _room_with_guest()
    for index in range(2):
        extra = _user(f"observability_extra_{index}")
        join_room(_request(extra), HttpResponse(), code=room.code)
        execute_command(
            _request(extra),
            room.id,
            command="ready",
            payload={"ready": True},
            request_id=None,
            expected_version=None,
        )
    key = "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c15"
    keyed_room, _keyed_member = create_room(
        _request(host),
        HttpResponse(),
        game_id="whos_undercover",
        max_players=4,
        name="Sensitive Host",
        request_id=UUID(key),
    )
    replay = create_room(
        _request(host),
        HttpResponse(),
        game_id="whos_undercover",
        max_players=4,
        name="Sensitive Host",
        request_id=UUID(key),
    )
    assert replay[0].id == keyed_room.id

    execute_command(
        _request(guest),
        room.id,
        command="ready",
        payload={"ready": True},
        request_id=None,
        expected_version=None,
    )
    execute_command(
        _request(host),
        room.id,
        command="start",
        payload={},
        request_id=None,
        expected_version=None,
    )
    # A rejected command still logs only the command/error, never its payload.
    with pytest.raises(RoomError):
        execute_command(
            _request(guest),
            room.id,
            command="vote",
            payload={"targetId": "private-target"},
            request_id=None,
            expected_version=None,
        )
    read_room(_request(host), room.id)
    leave_room(_request(guest), room.id)

    room.refresh_from_db()
    forbidden = _forbidden_values(room)
    combined = " ".join(
        record.getMessage() + json.dumps(record.__dict__, default=str) for record in caplog.records
    )
    record_values = {
        str(value)
        for record in caplog.records
        for value in record.__dict__.values()
        if isinstance(value, str)
    }
    for value in forbidden:
        if len(value) >= 3:
            assert value not in record_values
    for value in (
        "Sensitive Host",
        "Sensitive Guest",
        key,
        "private-target",
        "ba_anon",
        "csrftoken",
    ):
        assert value not in combined


@pytest.mark.django_db
@override_settings(ROOM_SLOW_LOG_MS=0)
def test_slow_read_and_command_events_are_structured(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="apps.rooms")
    room, host, guest, _guest_member = _room_with_guest()

    read_room(_request(host), room.id)
    execute_command(
        _request(guest),
        room.id,
        command="ready",
        payload={"ready": True},
        request_id=None,
        expected_version=None,
    )

    events = [record.event for record in caplog.records if hasattr(record, "event")]
    assert "room.read.slow" in events
    assert "room.command" in events
    for record in caplog.records:
        if record.event == "room.command":
            assert record.command == "ready"
            assert record.duration_ms >= 0
            assert record.room_id == str(room.id)
            assert not hasattr(record, "payload")
            assert not hasattr(record, "request_id")


@pytest.mark.django_db
def test_host_claim_and_forfeit_events_are_recorded(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="apps.rooms")
    room, _host, guest, _guest_member = _room_with_guest()
    host_member = room.members.get(role=RoomMember.ROLE_HOST)
    RoomMember.objects.filter(pk=host_member.pk).update(
        last_seen_at=timezone.now() - timedelta(seconds=121)
    )

    execute_command(
        _request(guest),
        room.id,
        command="claim_host",
        payload={},
        request_id=None,
        expected_version=None,
    )
    leave_room(_request(guest), room.id)
    events = [record.event for record in caplog.records if hasattr(record, "event")]
    assert "room.host.claim" in events
    assert "room.leave" in events


def test_json_formatter_has_a_safe_field_whitelist() -> None:
    record = logging.LogRecord(
        name="apps.rooms",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="room.test",
        args=(),
        exc_info=None,
    )
    record.event = "room.test"
    record.room_id = "room-safe-id"
    record.word = "secret-word"
    record.role = "undercover"
    record.vote = "secret-vote"
    record.cookie = "session-cookie"
    record.request_id = "secret-request"
    set_request_id("-")

    payload = json.loads(JsonFormatter().format(record))

    assert payload["event"] == "room.test"
    assert payload["room_id"] == "room-safe-id"
    for key in ("word", "role", "vote", "cookie"):
        assert key not in payload
    assert payload["request_id"] == "-"
