"""Concurrent Live Room state transitions on PostgreSQL.

Each worker opens its own database connection and starts behind a barrier.
The tests assert final database state, not only HTTP/service return values.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import timedelta
from uuid import uuid4

import pytest
from django.core.cache import caches
from django.db import connections
from django.http import HttpResponse
from django.test import RequestFactory, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Game, GameVersion, Genre
from apps.rooms.models import Room, RoomCommand, RoomMember
from apps.rooms.services.rooms import (
    RoomError,
    create_room,
    execute_command,
    join_room,
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
    genre = Genre.objects.create(code="live_race_genre")
    game = Game.objects.create(
        technical_id="whos_undercover",
        host_label="whos-undercover-race.games.test",
        slug="whos-undercover-race",
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


def _create_host(max_players: int = 4) -> tuple[Room, User, RoomMember]:
    _game()
    host = _user("race_host")
    room, member = create_room(
        _request(host),
        HttpResponse(),
        game_id="whos_undercover",
        max_players=max_players,
        name="Host",
    )
    return room, host, member


def _join(room: Room, user: User) -> RoomMember:
    _room, member = join_room(
        _request(user),
        HttpResponse(),
        code=room.code,
        name=user.login,
    )
    return member


def _ready(room: Room, user: User) -> None:
    execute_command(
        _request(user),
        room.id,
        command="ready",
        payload={"ready": True},
        request_id=None,
        expected_version=None,
    )


def _start(room: Room, host: User) -> dict[str, object]:
    current = Room.objects.get(pk=room.pk).version
    return execute_command(
        _request(host),
        room.id,
        command="start",
        payload={},
        request_id=uuid4(),
        expected_version=current,
    )


def _reveal_and_clues(room: Room, users: list[User]) -> Room:
    for user in users:
        execute_command(
            _request(user),
            room.id,
            command="reveal_ack",
            payload={},
            request_id=uuid4(),
            expected_version=None,
        )
    current = Room.objects.get(pk=room.pk)
    for _ in range(len(current.state["players"])):
        execute_command(
            _request(users[0]),
            room.id,
            command="advance_clue",
            payload={},
            request_id=uuid4(),
            expected_version=None,
        )
    current.refresh_from_db()
    assert current.state["phase"] == "vote"
    return current


def _run_workers(
    workers: list[Callable[[], tuple[str, object]]],
    timeout: float = 30,
) -> list[tuple[str, object]]:
    barrier = threading.Barrier(len(workers))
    outcomes: list[tuple[str, object]] = []
    failures: list[BaseException] = []
    lock = threading.Lock()

    def wrap(worker: Callable[[], tuple[str, object]]) -> None:
        try:
            barrier.wait(timeout=timeout)
            outcome = worker()
        except RoomError as exc:
            outcome = ("error", exc.code)
        except BaseException as exc:  # noqa: BLE001 - re-raised on the test thread
            with lock:
                failures.append(exc)
            return
        finally:
            connections.close_all()
        with lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=wrap, args=(worker,)) for worker in workers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=timeout)
    assert not any(thread.is_alive() for thread in threads)
    if failures:
        raise failures[0]
    return outcomes


def _host_count(room_id: object) -> int:
    return RoomMember.objects.filter(room_id=room_id, role=RoomMember.ROLE_HOST).count()


@pytest.mark.django_db(transaction=True)
def test_two_players_race_for_the_last_slot() -> None:
    room, _host, _member = _create_host(max_players=4)
    _join(room, _user("race_fill_1"))
    _join(room, _user("race_fill_2"))
    first = _user("race_fill_3")
    second = _user("race_fill_4")

    outcomes = _run_workers(
        [
            lambda: ("ok", _join(room, first).id),
            lambda: ("ok", _join(room, second).id),
        ]
    )

    assert sum(status == "ok" for status, _value in outcomes) == 1
    errors = [value for status, value in outcomes if status == "error"]
    assert errors == ["E_ROOM_FULL"]
    assert RoomMember.objects.filter(room=room, active=True).count() == 4
    assert _host_count(room.pk) == 1


@pytest.mark.django_db(transaction=True)
def test_parallel_ready_then_parallel_start_has_one_game() -> None:
    room, host, _member = _create_host(max_players=4)
    guests = [_user(f"race_ready_{index}") for index in range(3)]
    for guest in guests:
        _join(room, guest)

    ready_outcomes = _run_workers(
        [
            lambda guest=guest: (
                "ok",
                execute_command(
                    _request(guest),
                    room.id,
                    command="ready",
                    payload={"ready": True},
                    request_id=uuid4(),
                    expected_version=None,
                ),
            )
            for guest in guests
        ]
    )
    assert all(status == "ok" for status, _value in ready_outcomes)
    assert RoomMember.objects.filter(room=room, active=True, ready=True).count() == 4

    current = Room.objects.get(pk=room.pk)
    start_version = current.version

    def start_worker() -> tuple[str, object]:
        return (
            "ok",
            execute_command(
                _request(host),
                room.id,
                command="start",
                payload={},
                request_id=uuid4(),
                expected_version=start_version,
            ),
        )

    start_outcomes = _run_workers([start_worker, start_worker])
    assert sum(status == "ok" for status, _value in start_outcomes) == 1
    assert [value for status, value in start_outcomes if status == "error"] == ["E_ROOM_STALE"]
    current.refresh_from_db()
    assert current.status == Room.STATUS_ACTIVE
    assert current.state["phase"] == "reveal"
    assert len(current.state["players"]) == 4
    assert _host_count(room.pk) == 1


@pytest.mark.django_db(transaction=True)
def test_same_request_id_executes_once() -> None:
    room, _host, _member = _create_host(max_players=4)
    guest = _user("race_same_request")
    _join(room, guest)
    request_id = uuid4()

    def ready_worker() -> tuple[str, object]:
        return (
            "ok",
            execute_command(
                _request(guest),
                room.id,
                command="ready",
                payload={"ready": True},
                request_id=request_id,
                expected_version=None,
            ),
        )

    outcomes = _run_workers([ready_worker, ready_worker])

    assert all(status == "ok" for status, _value in outcomes)
    assert RoomCommand.objects.filter(room=room, request_id=request_id).count() == 1
    assert RoomMember.objects.get(room=room, subject_id=guest.pk).ready is True


@pytest.mark.django_db(transaction=True)
def test_same_expected_version_allows_one_command() -> None:
    room, _host, _member = _create_host(max_players=4)
    first = _user("race_version_1")
    second = _user("race_version_2")
    _join(room, first)
    _join(room, second)
    version = Room.objects.get(pk=room.pk).version

    def ready_worker(user: User) -> tuple[str, object]:
        return (
            "ok",
            execute_command(
                _request(user),
                room.id,
                command="ready",
                payload={"ready": True},
                request_id=uuid4(),
                expected_version=version,
            ),
        )

    outcomes = _run_workers([lambda: ready_worker(first), lambda: ready_worker(second)])

    assert sum(status == "ok" for status, _value in outcomes) == 1
    assert [value for status, value in outcomes if status == "error"] == ["E_ROOM_STALE"]
    assert (
        RoomMember.objects.filter(room=room, role=RoomMember.ROLE_PLAYER, ready=True).count() == 1
    )


@pytest.mark.django_db(transaction=True)
def test_parallel_votes_are_all_counted_once() -> None:
    room, host, _member = _create_host(max_players=4)
    guests = [_user(f"race_vote_{index}") for index in range(3)]
    for guest in guests:
        _join(room, guest)
        _ready(room, guest)
    _start(room, host)
    current = _reveal_and_clues(room, [host, *guests])

    member_ids = [player["id"] for player in current.state["players"]]
    users = [host, *guests]
    targets = {}
    for index, user in enumerate(users):
        member_id = next(
            str(member.id)
            for member in current.members.all()
            if member.subject_type == Room.SUBJECT_USER and member.subject_id == user.pk
        )
        assert member_id in member_ids
        target_index = (index + 1) % len(users)
        targets[user.pk] = str(
            next(
                member.id
                for member in current.members.all()
                if member.subject_type == Room.SUBJECT_USER
                and member.subject_id == users[target_index].pk
            )
        )

    def vote_worker(user: User) -> tuple[str, object]:
        return (
            "ok",
            execute_command(
                _request(user),
                room.id,
                command="vote",
                payload={"targetId": targets[user.pk]},
                request_id=uuid4(),
                expected_version=None,
            ),
        )

    outcomes = _run_workers([lambda user=user: vote_worker(user) for user in users])

    assert all(status == "ok" for status, _value in outcomes)
    current.refresh_from_db()
    assert current.state["votes"] == {}
    assert sum(current.state["last_vote"]["counts"].values()) == 4
    assert current.state["phase"] in {"vote_result", "game_over"}
    assert _host_count(room.pk) == 1


@pytest.mark.django_db(transaction=True)
def test_parallel_host_claim_leaves_exactly_one_host() -> None:
    room, _host, host_member = _create_host(max_players=4)
    first = _user("race_claim_1")
    second = _user("race_claim_2")
    _join(room, first)
    _join(room, second)
    RoomMember.objects.filter(pk=host_member.pk).update(
        last_seen_at=timezone.now() - timedelta(seconds=121)
    )

    def claim_worker(user: User) -> tuple[str, object]:
        return (
            "ok",
            execute_command(
                _request(user),
                room.id,
                command="claim_host",
                payload={},
                request_id=uuid4(),
                expected_version=None,
            ),
        )

    outcomes = _run_workers([lambda: claim_worker(first), lambda: claim_worker(second)])

    assert sum(status == "ok" for status, _value in outcomes) == 1
    errors = [value for status, value in outcomes if status == "error"]
    assert errors == ["E_HOST_ACTIVE"]
    current = Room.objects.get(pk=room.pk)
    assert current.status == Room.STATUS_LOBBY
    assert _host_count(room.pk) == 1
    claimant = current.members.get(role=RoomMember.ROLE_HOST)
    assert (current.host_subject_type, current.host_subject_id) == (
        claimant.subject_type,
        claimant.subject_id,
    )


@pytest.mark.django_db(transaction=True)
def test_tie_resolution_is_consistent() -> None:
    room, host, _member = _create_host(max_players=4)
    guests = [_user(f"race_tie_{index}") for index in range(3)]
    for guest in guests:
        _join(room, guest)
        _ready(room, guest)
    _start(room, host)
    current = _reveal_and_clues(room, [host, *guests])
    users = [host, *guests]
    members = {
        member.subject_id: member
        for member in current.members.filter(subject_type=Room.SUBJECT_USER)
    }
    # Each voter targets the next member, producing a four-way 1:1:1:1 tie.
    targets = {
        user.pk: str(members[users[(index + 1) % len(users)].pk].id)
        for index, user in enumerate(users)
    }

    def vote_worker(user: User) -> tuple[str, object]:
        return (
            "ok",
            execute_command(
                _request(user),
                room.id,
                command="vote",
                payload={"targetId": targets[user.pk]},
                request_id=uuid4(),
                expected_version=None,
            ),
        )

    outcomes = _run_workers([lambda user=user: vote_worker(user) for user in users])
    assert all(status == "ok" for status, _value in outcomes)
    current.refresh_from_db()
    assert current.state["phase"] == "vote_result"
    assert current.state["last_vote"]["tie"] is True
    assert current.state["last_vote"]["eliminatedId"] is None
    assert sum(current.state["last_vote"]["counts"].values()) == 4
    assert all(player["alive"] for player in current.state["players"])


@pytest.mark.django_db(transaction=True)
def test_expiry_and_read_do_not_corrupt_the_room() -> None:
    from apps.rooms.services.rooms import expire_rooms

    room, _host, _member = _create_host(max_players=4)
    Room.objects.filter(pk=room.pk).update(
        expires_at=timezone.now() - timedelta(seconds=1),
        last_activity_at=timezone.now() - timedelta(seconds=1),
    )

    def read_worker() -> tuple[str, object]:
        try:
            read_room(_request(_host), room.id)
            return ("ok", "read")
        except RoomError as exc:
            return ("error", exc.code)

    def expire_worker() -> tuple[str, object]:
        return ("ok", expire_rooms())

    outcomes = _run_workers([read_worker, expire_worker])
    current = Room.objects.get(pk=room.pk)
    assert current.status == Room.STATUS_EXPIRED
    assert _host_count(room.pk) == 1
    assert len(outcomes) == 2


@pytest.mark.django_db(transaction=True)
def test_stale_sweep_and_vote_do_not_corrupt_roles() -> None:
    room, host, _member = _create_host(max_players=4)
    guests = [_user(f"race_sweep_{index}") for index in range(3)]
    for guest in guests:
        _join(room, guest)
        _ready(room, guest)
    _start(room, host)
    current = _reveal_and_clues(room, [host, *guests])
    stale = current.members.get(subject_id=guests[0].pk)
    RoomMember.objects.filter(pk=stale.pk).update(
        last_seen_at=timezone.now() - timedelta(seconds=301)
    )
    active_voter = guests[1]
    target = current.members.get(subject_id=guests[2].pk)

    def read_worker() -> tuple[str, object]:
        try:
            read_room(_request(host), room.id)
            return ("ok", "read")
        except RoomError as exc:
            return ("error", exc.code)

    def vote_worker() -> tuple[str, object]:
        try:
            execute_command(
                _request(active_voter),
                room.id,
                command="vote",
                payload={"targetId": str(target.id)},
                request_id=uuid4(),
                expected_version=None,
            )
            return ("ok", "vote")
        except RoomError as exc:
            return ("error", exc.code)

    outcomes = _run_workers([read_worker, vote_worker])

    current = Room.objects.get(pk=room.pk)
    assert _host_count(room.pk) == 1
    assert current.state["phase"] in {"vote", "vote_result", "game_over", "mr_white"}
    assert len(outcomes) == 2


@pytest.mark.django_db(transaction=True)
def test_host_start_and_guest_claim_have_one_host() -> None:
    room, host, _member = _create_host(max_players=4)
    guests = [_user(f"race_claim_start_{index}") for index in range(3)]
    for guest in guests:
        _join(room, guest)
        _ready(room, guest)
    current = Room.objects.get(pk=room.pk)
    old_version = current.version
    host_member = current.members.get(role=RoomMember.ROLE_HOST)
    RoomMember.objects.filter(pk=host_member.pk).update(
        last_seen_at=timezone.now() - timedelta(seconds=121)
    )
    claimant = guests[0]

    def start_worker() -> tuple[str, object]:
        try:
            execute_command(
                _request(host),
                room.id,
                command="start",
                payload={},
                request_id=uuid4(),
                expected_version=old_version,
            )
            return ("ok", "start")
        except RoomError as exc:
            return ("error", exc.code)

    def claim_worker() -> tuple[str, object]:
        try:
            execute_command(
                _request(claimant),
                room.id,
                command="claim_host",
                payload={},
                request_id=uuid4(),
                expected_version=None,
            )
            return ("ok", "claim")
        except RoomError as exc:
            return ("error", exc.code)

    outcomes = _run_workers([start_worker, claim_worker])

    current = Room.objects.get(pk=room.pk)
    assert _host_count(room.pk) == 1
    assert current.status in {Room.STATUS_LOBBY, Room.STATUS_ACTIVE}
    assert len(outcomes) == 2


@pytest.mark.django_db(transaction=True)
def test_expiry_and_join_are_serialized() -> None:
    from apps.rooms.services.rooms import expire_rooms

    room, _host, _member = _create_host(max_players=4)
    newcomer = _user("race_expiry_join")
    Room.objects.filter(pk=room.pk).update(
        expires_at=timezone.now() - timedelta(seconds=1),
        last_activity_at=timezone.now() - timedelta(seconds=1),
    )

    def join_worker() -> tuple[str, object]:
        try:
            join_room(_request(newcomer), HttpResponse(), code=room.code)
            return ("ok", "join")
        except RoomError as exc:
            return ("error", exc.code)

    def expire_worker() -> tuple[str, object]:
        return ("ok", expire_rooms())

    outcomes = _run_workers([join_worker, expire_worker])
    current = Room.objects.get(pk=room.pk)
    assert current.status == Room.STATUS_EXPIRED
    assert _host_count(room.pk) == 1
    assert len(outcomes) == 2


@pytest.mark.django_db(transaction=True)
def test_cleanup_and_read_are_safe() -> None:
    from apps.rooms.services.rooms import cleanup_rooms

    room, host, _member = _create_host(max_players=4)
    Room.objects.filter(pk=room.pk).update(
        status=Room.STATUS_FINISHED,
        finished_at=timezone.now() - timedelta(hours=25),
    )

    def read_worker() -> tuple[str, object]:
        try:
            read_room(_request(host), room.id)
            return ("ok", "read")
        except RoomError as exc:
            return ("error", exc.code)

    def cleanup_worker() -> tuple[str, object]:
        return ("ok", cleanup_rooms())

    outcomes = _run_workers([read_worker, cleanup_worker])
    assert not Room.objects.filter(pk=room.pk).exists()
    assert len(outcomes) == 2
