"""Live Room LR-0: lobby, private roles and server-authoritative commands."""

from __future__ import annotations

import json
import re
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from django.core.cache import caches
from django.test import Client, override_settings
from django.utils import timezone

from apps.catalog.models import Game, GameVersion, Genre
from apps.rooms.models import Room, RoomMember
from apps.rooms.services.rooms import anonymize_subject, cleanup_rooms, expire_rooms

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
    genre = Genre.objects.create(code="live_room_genre")
    game = Game.objects.create(
        technical_id="whos_undercover",
        host_label="whos-undercover-room.games.test",
        slug="whos-undercover-room",
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
    )
    version = GameVersion.objects.create(
        game=game,
        semver="1.0.0",
        package_hash="c" * 64,
        runtime_hash="d" * 64,
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


def _post(client: Client, csrf: str, path: str, payload: dict[str, object]):
    return client.post(
        path,
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )


def _command(
    client: Client,
    csrf: str,
    room_id: str,
    *,
    command: str,
    payload: dict[str, object],
    version: int,
    request_id: str | None = None,
):
    return _post(
        client,
        csrf,
        f"{API}/{room_id}/commands",
        {
            "command": command,
            "payload": payload,
            "requestId": request_id or str(uuid4()),
            "expectedVersion": version,
        },
    )


def _start_room(
    *,
    player_count: int = 4,
    undercover_count: int = 1,
    mr_white: bool = False,
) -> dict[str, object]:
    game = _game()
    host_client, host_csrf = _client()
    created = _post(
        host_client,
        host_csrf,
        API,
        {
            "game_id": game.technical_id,
            "max_players": player_count,
            "undercover_count": undercover_count,
            "mr_white": mr_white,
            "name": "Host",
        },
    )
    assert created.status_code == 201, created.content
    created_payload = created.json()
    room_id = created_payload["room"]["id"]
    code = created_payload["room"]["code"]
    actors = [(host_client, host_csrf, created_payload["you"]["memberId"])]
    for index in range(player_count - 1):
        client, csrf = _client()
        joined = _post(client, csrf, f"{API}/join", {"code": code, "name": f"P{index}"})
        assert joined.status_code == 200, joined.content
        member_id = joined.json()["you"]["memberId"]
        snapshot = client.get(f"{API}/{room_id}").json()
        ready = _command(
            client,
            csrf,
            room_id,
            command="ready",
            payload={"ready": True},
            version=snapshot["room"]["version"],
        )
        assert ready.status_code == 200, ready.content
        actors.append((client, csrf, member_id))
    version = host_client.get(f"{API}/{room_id}").json()["room"]["version"]
    started = _command(
        host_client,
        host_csrf,
        room_id,
        command="start",
        payload={},
        version=version,
    )
    assert started.status_code == 200, started.content
    return {
        "room_id": room_id,
        "host": (host_client, host_csrf, created_payload["you"]["memberId"]),
        "actors": actors,
        "version": started.json()["room"]["version"],
    }


def _act(
    ctx: dict[str, object],
    actor: tuple[Client, str, str],
    command: str,
    payload: dict[str, object] | None = None,
):
    client, csrf, _ = actor
    response = _command(
        client,
        csrf,
        str(ctx["room_id"]),
        command=command,
        payload=payload or {},
        version=int(ctx["version"]),
    )
    if response.status_code == 200:
        ctx["version"] = response.json()["room"]["version"]
    return response


def _reveal_and_clue(ctx: dict[str, object]) -> None:
    for actor in ctx["actors"]:
        response = _act(ctx, actor, "reveal_ack")
        assert response.status_code == 200, response.content
    room = Room.objects.get(pk=ctx["room_id"])
    assert room.state["phase"] == "clues"
    for _ in room.state["players"]:
        response = _act(ctx, ctx["host"], "advance_clue")
        assert response.status_code == 200, response.content
    room.refresh_from_db()
    assert room.state["phase"] == "vote"


def _role_ids(room_id: str) -> dict[str, str]:
    room = Room.objects.get(pk=room_id)
    return {player["role"]: player["id"] for player in room.state["players"]}


def test_server_word_decks_match_the_cartridge_locales() -> None:
    root = Path(__file__).resolve().parents[2]
    for language in ("en", "ru"):
        server = root / "apps" / "rooms" / "data" / f"whos_undercover_{language}.json"
        cartridge = root / "games-src" / "whos_undercover" / "locales" / f"{language}.json"
        assert json.loads(server.read_text(encoding="utf-8")) == json.loads(
            cartridge.read_text(encoding="utf-8")
        )


@pytest.mark.django_db
def test_lobby_join_ready_start_and_private_roles() -> None:
    game = _game()
    host_client, host_csrf = _client()
    created = _post(
        host_client,
        host_csrf,
        API,
        {"game_id": game.technical_id, "max_players": 4, "name": "Maya"},
    )
    assert created.status_code == 201, created.content
    room_payload = created.json()
    room_id = room_payload["room"]["id"]
    code = room_payload["room"]["code"]
    assert room_payload["you"]["isHost"] is True
    assert room_payload["you"]["role"] is None
    assert room_payload["game"]["phase"] == "lobby"

    guests = []
    for name in ("Jonas", "Priya", "Leo"):
        client, csrf = _client()
        joined = _post(client, csrf, f"{API}/join", {"code": code, "name": name})
        assert joined.status_code == 200, joined.content
        guests.append((client, csrf, joined.json()["you"]["memberId"]))

    host_snapshot = host_client.get(f"{API}/{room_id}").json()
    assert len(host_snapshot["players"]) == 4
    assert all(player["role"] is None for player in host_snapshot["players"])
    assert host_snapshot["you"]["role"] is None

    # Start is rejected until every non-host player is ready.
    version = host_snapshot["room"]["version"]
    not_ready = _command(
        host_client,
        host_csrf,
        room_id,
        command="start",
        payload={},
        version=version,
    )
    assert not_ready.status_code == 409
    assert not_ready.json()["code"] == "E_NOT_READY"

    for client, csrf, _ in guests:
        snapshot = client.get(f"{API}/{room_id}").json()
        ready = _command(
            client,
            csrf,
            room_id,
            command="ready",
            payload={"ready": True},
            version=snapshot["room"]["version"],
        )
        assert ready.status_code == 200, ready.content
        version = ready.json()["room"]["version"]

    started = _command(
        host_client,
        host_csrf,
        room_id,
        command="start",
        payload={},
        version=version,
    )
    assert started.status_code == 200, started.content
    started_payload = started.json()
    assert started_payload["room"]["status"] == "active"
    assert started_payload["game"]["phase"] == "reveal"
    assert started_payload["you"]["role"] in {"civilian", "undercover", "mr_white"}
    assert started_payload["you"]["word"]
    assert started_payload["game"]["civilianWord"] is None
    assert started_payload["game"]["undercoverWord"] is None
    assert all(player["role"] is None for player in started_payload["players"])

    # Every guest gets only their own role/word, never the host's.
    roles = set()
    for client, _, member_id in guests:
        snapshot = client.get(f"{API}/{room_id}").json()
        assert snapshot["you"]["memberId"] == member_id
        assert snapshot["you"]["role"] in {"civilian", "undercover", "mr_white"}
        assert snapshot["you"]["word"]
        roles.add(snapshot["you"]["role"])
        assert all(player["role"] is None for player in snapshot["players"])
        assert snapshot["game"]["civilianWord"] is None
    assert "civilian" in roles or "undercover" in roles or "mr_white" in roles


@pytest.mark.django_db
def test_commands_are_idempotent_and_stale_versions_are_rejected() -> None:
    game = _game()
    client, csrf = _client()
    created = _post(client, csrf, API, {"game_id": game.technical_id, "max_players": 4})
    assert created.status_code == 201
    room_id = created.json()["room"]["id"]
    version = created.json()["room"]["version"]

    request_id = str(uuid4())
    first = _command(
        client,
        csrf,
        room_id,
        command="ready",
        payload={"ready": True},
        version=version,
        request_id=request_id,
    )
    assert first.status_code == 409, first.content  # host is always ready

    player_client, player_csrf = _client()
    joined = _post(
        player_client,
        player_csrf,
        f"{API}/join",
        {"code": created.json()["room"]["code"], "name": "Guest"},
    )
    assert joined.status_code == 200
    player_version = joined.json()["room"]["version"]
    command_id = str(uuid4())
    ready = _command(
        player_client,
        player_csrf,
        room_id,
        command="ready",
        payload={"ready": True},
        version=player_version,
        request_id=command_id,
    )
    assert ready.status_code == 200
    after = ready.json()["room"]["version"]
    repeated = _command(
        player_client,
        player_csrf,
        room_id,
        command="ready",
        payload={"ready": False},
        version=player_version,
        request_id=command_id,
    )
    assert repeated.status_code == 200
    assert repeated.json()["room"]["version"] == after
    stale = _command(
        player_client,
        player_csrf,
        room_id,
        command="ready",
        payload={"ready": True},
        version=player_version,
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "E_ROOM_STALE"
    assert stale.json()["snapshot"]["room"]["version"] == after
    missing_version = _post(
        player_client,
        player_csrf,
        f"{API}/{room_id}/commands",
        {"command": "ready", "payload": {}, "requestId": str(uuid4())},
    )
    assert missing_version.status_code == 400
    assert missing_version.json()["code"] == "E_INVALID_REQUEST"
    oversized = _command(
        player_client,
        player_csrf,
        room_id,
        command="ready",
        payload={"blob": "x" * 3000},
        version=after,
    )
    assert oversized.status_code == 400
    assert oversized.json()["code"] == "E_INVALID_REQUEST"
    surrogate = (
        '{"command":"ready","payload":{"x":"\\ud800"},"requestId":"'
        + str(uuid4())
        + '","expectedVersion":'
        + str(after)
        + "}"
    )
    invalid_utf8 = player_client.post(
        f"{API}/{room_id}/commands",
        data=surrogate,
        content_type="application/json",
        HTTP_X_CSRFTOKEN=player_csrf,
    )
    assert invalid_utf8.status_code == 400
    assert invalid_utf8.json()["code"] == "E_INVALID_REQUEST"


@pytest.mark.django_db
def test_join_after_start_and_expired_room_are_blocked() -> None:
    game = _game()
    host_client, host_csrf = _client()
    created = _post(host_client, host_csrf, API, {"game_id": game.technical_id, "max_players": 4})
    room_id = created.json()["room"]["id"]
    code = created.json()["room"]["code"]
    for name in ("B", "C", "D"):
        client, csrf = _client()
        joined = _post(client, csrf, f"{API}/join", {"code": code, "name": name})
        assert joined.status_code == 200
        snapshot = client.get(f"{API}/{room_id}").json()
        _command(
            client,
            csrf,
            room_id,
            command="ready",
            payload={"ready": True},
            version=snapshot["room"]["version"],
        )
    version = host_client.get(f"{API}/{room_id}").json()["room"]["version"]
    started = _command(
        host_client,
        host_csrf,
        room_id,
        command="start",
        payload={},
        version=version,
    )
    assert started.status_code == 200

    late_client, late_csrf = _client()
    late = _post(late_client, late_csrf, f"{API}/join", {"code": code, "name": "Late"})
    assert late.status_code == 409
    assert late.json()["code"] == "E_ROOM_STARTED"

    room = Room.objects.get(pk=room_id)
    room.expires_at = timezone.now() - timedelta(seconds=1)
    room.save(update_fields=["expires_at"])
    expired = host_client.get(f"{API}/{room_id}")
    assert expired.status_code == 200
    assert expired.json()["room"]["status"] == "expired"
    command = _command(
        host_client,
        host_csrf,
        room_id,
        command="start",
        payload={},
        version=expired.json()["room"]["version"],
    )
    assert command.status_code == 410


@pytest.mark.django_db
def test_host_leave_abandons_the_room() -> None:
    game = _game()
    client, csrf = _client()
    created = _post(client, csrf, API, {"game_id": game.technical_id, "max_players": 4})
    room_id = created.json()["room"]["id"]
    left = _post(client, csrf, f"{API}/{room_id}/leave", {})
    assert left.status_code == 204
    room = Room.objects.get(pk=room_id)
    assert room.status == Room.STATUS_ABANDONED
    assert RoomMember.objects.get(room=room, role=RoomMember.ROLE_HOST).active is False


@pytest.mark.django_db
def test_host_leave_transfers_host_to_another_active_member() -> None:
    game = _game()
    host_client, host_csrf = _client()
    created = _post(host_client, host_csrf, API, {"game_id": game.technical_id, "max_players": 4})
    assert created.status_code == 201
    room_id = created.json()["room"]["id"]
    code = created.json()["room"]["code"]
    guest_client, guest_csrf = _client()
    joined = _post(guest_client, guest_csrf, f"{API}/join", {"code": code, "name": "Next"})
    assert joined.status_code == 200
    guest_id = joined.json()["you"]["memberId"]

    left = _post(host_client, host_csrf, f"{API}/{room_id}/leave", {})
    assert left.status_code == 204
    room = Room.objects.get(pk=room_id)
    assert room.status == Room.STATUS_LOBBY
    new_host = RoomMember.objects.get(pk=guest_id)
    assert new_host.role == RoomMember.ROLE_HOST
    assert room.host_subject_id == new_host.subject_id
    snapshot = guest_client.get(f"{API}/{room_id}").json()
    assert snapshot["you"]["isHost"] is True
    assert snapshot["room"]["hostMemberId"] == guest_id


@pytest.mark.django_db
def test_cleanup_removes_only_stale_closed_rooms() -> None:
    game = _game()
    client, csrf = _client()
    created = _post(client, csrf, API, {"game_id": game.technical_id, "max_players": 4})
    assert created.status_code == 201
    room_id = created.json()["room"]["id"]
    Room.objects.filter(pk=room_id).update(
        status=Room.STATUS_FINISHED,
        finished_at=timezone.now() - timedelta(hours=25),
    )

    fresh_client, fresh_csrf = _client()
    fresh = _post(
        fresh_client,
        fresh_csrf,
        API,
        {"game_id": game.technical_id, "max_players": 4},
    )
    assert fresh.status_code == 201
    fresh_id = fresh.json()["room"]["id"]
    Room.objects.filter(pk=fresh_id).update(status=Room.STATUS_FINISHED)

    assert cleanup_rooms() == 1
    assert not Room.objects.filter(pk=room_id).exists()
    assert Room.objects.filter(pk=fresh_id).exists()


@pytest.mark.django_db
def test_member_reconnects_with_same_private_role() -> None:
    ctx = _start_room()
    room_id = str(ctx["room_id"])
    civilians = {
        player["id"]
        for player in Room.objects.get(pk=room_id).state["players"]
        if player["role"] == "civilian"
    }
    guest_client, guest_csrf, guest_id = next(
        actor for actor in ctx["actors"][1:] if actor[2] in civilians
    )
    before = guest_client.get(f"{API}/{room_id}").json()
    assert before["you"]["memberId"] == guest_id
    role = before["you"]["role"]
    word = before["you"]["word"]

    left = _post(guest_client, guest_csrf, f"{API}/{room_id}/leave", {})
    assert left.status_code == 204
    repeated = _post(guest_client, guest_csrf, f"{API}/{room_id}/leave", {})
    assert repeated.status_code == 204
    denied = guest_client.get(f"{API}/{room_id}")
    assert denied.status_code == 403
    assert denied.json()["code"] == "E_NOT_MEMBER"
    blocked = _command(
        guest_client,
        guest_csrf,
        room_id,
        command="reveal_ack",
        payload={},
        version=Room.objects.get(pk=room_id).version,
    )
    assert blocked.status_code == 403
    code = Room.objects.get(pk=room_id).code
    rejoined = _post(guest_client, guest_csrf, f"{API}/join", {"code": code, "name": "Again"})
    assert rejoined.status_code == 200, rejoined.content
    payload = rejoined.json()
    assert payload["you"]["memberId"] == guest_id
    assert payload["you"]["role"] == role
    assert payload["you"]["word"] == word
    assert any(player["id"] == guest_id for player in payload["players"])


@pytest.mark.django_db
def test_live_room_rejects_a_game_without_room_support() -> None:
    genre = Genre.objects.create(code="unsupported_room_genre")
    game = Game.objects.create(
        technical_id="archer",
        host_label="archer-room.games.test",
        slug="archer-room",
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
    )
    version = GameVersion.objects.create(
        game=game,
        semver="1.0.0",
        package_hash="e" * 64,
        runtime_hash="f" * 64,
        sdk_version="1.1.0",
        size_bytes=1000,
        manifest={},
        supported_languages=["en"],
    )
    game.current_version = version
    game.save(update_fields=["current_version"])

    client, csrf = _client()
    created = _post(client, csrf, API, {"game_id": game.technical_id, "max_players": 4})
    assert created.status_code == 404
    assert created.json()["code"] == "E_GAME_INVALID"


@pytest.mark.django_db
def test_account_deletion_scrubs_room_identity_and_abandons_room() -> None:
    ctx = _start_room()
    room_id = str(ctx["room_id"])
    host_member = RoomMember.objects.get(pk=ctx["host"][2])
    subject_type = host_member.subject_type
    subject_id = host_member.subject_id
    old_host_subject = Room.objects.get(pk=room_id).host_subject_id
    old_name = host_member.name

    assert anonymize_subject(subject_type, subject_id) == 1
    room = Room.objects.get(pk=room_id)
    host_member.refresh_from_db()
    assert room.status == Room.STATUS_ABANDONED
    assert room.finished_at is not None
    assert room.host_subject_id != old_host_subject
    assert host_member.name == "Player"
    assert host_member.subject_id != subject_id
    assert host_member.active is False
    assert all(
        player["name"] == "Player"
        for player in room.state["players"]
        if player["id"] == str(host_member.id)
    )
    assert old_name != "Player"
    assert anonymize_subject(subject_type, subject_id) == 0


@pytest.mark.django_db
def test_leave_during_reveal_does_not_stall_the_room() -> None:
    ctx = _start_room()
    room_id = str(ctx["room_id"])
    role_ids = _role_ids(room_id)
    by_member = {str(actor[2]): actor for actor in ctx["actors"]}
    civilian_actor = by_member[role_ids["civilian"]]
    left = _post(civilian_actor[0], civilian_actor[1], f"{API}/{room_id}/leave", {})
    assert left.status_code == 204
    ctx["version"] = Room.objects.get(pk=room_id).version

    for actor in ctx["actors"]:
        if actor is civilian_actor:
            continue
        response = _act(ctx, actor, "reveal_ack")
        assert response.status_code == 200, response.content
    snapshot = ctx["host"][0].get(f"{API}/{room_id}").json()
    assert snapshot["game"]["phase"] == "clues"
    assert snapshot["game"]["aliveCount"] == 3
    assert all(player["id"] != civilian_actor[2] for player in snapshot["players"])


@pytest.mark.django_db
def test_leave_during_vote_still_resolves_the_vote() -> None:
    ctx = _start_room()
    room_id = str(ctx["room_id"])
    _reveal_and_clue(ctx)
    role_ids = _role_ids(room_id)
    by_member = {str(actor[2]): actor for actor in ctx["actors"]}
    civilian_actor = by_member[role_ids["civilian"]]
    left = _post(civilian_actor[0], civilian_actor[1], f"{API}/{room_id}/leave", {})
    assert left.status_code == 204
    ctx["version"] = Room.objects.get(pk=room_id).version
    state = Room.objects.get(pk=room_id).state
    alive_civilian = next(
        player["id"]
        for player in state["players"]
        if player["role"] == "civilian" and player["alive"]
    )

    for member_id, actor in by_member.items():
        if actor is civilian_actor:
            continue
        target = role_ids["undercover"] if member_id != role_ids["undercover"] else alive_civilian
        voted = _act(ctx, actor, "vote", {"targetId": target})
        assert voted.status_code == 200, voted.content
    final = ctx["host"][0].get(f"{API}/{room_id}").json()
    assert final["room"]["status"] == "finished"
    assert final["game"]["winner"] == "civilians"
    assert final["game"]["aliveCount"] == 2


@pytest.mark.django_db
def test_member_can_claim_a_stale_host() -> None:
    game = _game()
    host_client, host_csrf = _client()
    created = _post(host_client, host_csrf, API, {"game_id": game.technical_id, "max_players": 4})
    assert created.status_code == 201
    room_id = created.json()["room"]["id"]
    host_member_id = created.json()["you"]["memberId"]
    code = created.json()["room"]["code"]
    guest_client, guest_csrf = _client()
    joined = _post(guest_client, guest_csrf, f"{API}/join", {"code": code, "name": "Next"})
    assert joined.status_code == 200
    guest_id = joined.json()["you"]["memberId"]

    version = guest_client.get(f"{API}/{room_id}").json()["room"]["version"]
    denied = _command(
        guest_client,
        guest_csrf,
        room_id,
        command="claim_host",
        payload={},
        version=version,
    )
    assert denied.status_code == 409
    assert denied.json()["code"] == "E_HOST_ACTIVE"

    stale = timezone.now() - timedelta(minutes=3)
    RoomMember.objects.filter(pk=host_member_id).update(last_seen_at=stale)
    claimed = _command(
        guest_client,
        guest_csrf,
        room_id,
        command="claim_host",
        payload={},
        version=version,
    )
    assert claimed.status_code == 200, claimed.content
    assert claimed.json()["you"]["isHost"] is True
    assert claimed.json()["room"]["hostMemberId"] == guest_id
    assert RoomMember.objects.get(pk=host_member_id).role == RoomMember.ROLE_PLAYER
    claimed_room = Room.objects.get(pk=room_id)
    claimed_host = RoomMember.objects.get(pk=guest_id)
    assert claimed_room.host_subject_type == claimed_host.subject_type
    assert claimed_room.host_subject_id == claimed_host.subject_id


@pytest.mark.django_db
def test_expire_rooms_enforces_active_idle_ttl() -> None:
    ctx = _start_room()
    room_id = str(ctx["room_id"])
    room = Room.objects.get(pk=room_id)
    room.last_activity_at = timezone.now() - timedelta(minutes=31)
    room.save(update_fields=["last_activity_at"])
    assert expire_rooms() == 1
    room.refresh_from_db()
    assert room.status == Room.STATUS_EXPIRED
    assert room.finished_at is not None


@pytest.mark.django_db
def test_stale_player_is_forfeited_when_others_poll() -> None:
    ctx = _start_room()
    room_id = str(ctx["room_id"])
    _reveal_and_clue(ctx)
    role_ids = _role_ids(room_id)
    by_member = {str(actor[2]): actor for actor in ctx["actors"]}
    civilian_actor = by_member[role_ids["civilian"]]
    RoomMember.objects.filter(pk=civilian_actor[2]).update(
        last_seen_at=timezone.now() - timedelta(minutes=6)
    )
    snapshot = ctx["host"][0].get(f"{API}/{room_id}").json()
    assert snapshot["game"]["aliveCount"] == 3
    assert all(player["id"] != civilian_actor[2] for player in snapshot["players"])
    assert RoomMember.objects.get(pk=civilian_actor[2]).active is False


@pytest.mark.django_db
def test_stale_host_is_replaced_when_others_poll() -> None:
    ctx = _start_room()
    room_id = str(ctx["room_id"])
    host_member_id = ctx["host"][2]
    guest_actor = ctx["actors"][1]
    RoomMember.objects.filter(pk=host_member_id).update(
        last_seen_at=timezone.now() - timedelta(minutes=6)
    )
    snapshot = guest_actor[0].get(f"{API}/{room_id}").json()
    assert snapshot["you"]["isHost"] is True
    assert snapshot["room"]["hostMemberId"] == guest_actor[2]
    assert RoomMember.objects.get(pk=host_member_id).role == RoomMember.ROLE_PLAYER
    assert RoomMember.objects.get(pk=host_member_id).active is False


@pytest.mark.django_db
def test_phase_flow_elimination_and_private_words() -> None:
    ctx = _start_room()
    room_id = str(ctx["room_id"])
    actors = ctx["actors"]
    assert isinstance(actors, list)

    # Roles and words are delivered only to their owner until the game is over.
    for actor in actors:
        client, _, member_id = actor
        snapshot = client.get(f"{API}/{room_id}").json()
        assert snapshot["you"]["memberId"] == member_id
        assert snapshot["you"]["role"] in {"civilian", "undercover", "mr_white"}
        assert snapshot["you"]["word"]
        assert all(player["role"] is None for player in snapshot["players"])
        assert all(player["word"] is None for player in snapshot["players"])
        assert snapshot["game"]["civilianWord"] is None
        assert snapshot["game"]["undercoverWord"] is None

    _reveal_and_clue(ctx)
    room = Room.objects.get(pk=room_id)
    assert room.started_at is not None
    assert room.expires_at >= room.started_at + timedelta(hours=1)
    response = ctx["host"][0].get(f"{API}/{room_id}")
    assert response["Cache-Control"] == "private, no-store"
    snapshot = response.json()
    assert snapshot["game"]["phase"] == "vote"
    assert snapshot["game"]["speakerId"] is None
    assert snapshot["game"]["votesCast"] == 0

    guest = actors[1]
    denied = _act(ctx, guest, "advance_clue")
    assert denied.status_code == 403
    assert denied.json()["code"] == "E_HOST_ONLY"

    role_ids = _role_ids(room_id)
    undercover_id = role_ids["undercover"]
    by_member = {str(actor[2]): actor for actor in actors}
    voter = by_member[undercover_id]
    self_vote = _act(ctx, voter, "vote", {"targetId": undercover_id})
    assert self_vote.status_code == 422
    assert self_vote.json()["code"] == "E_SELF_VOTE"

    for actor in actors:
        member_id = str(actor[2])
        target = undercover_id if member_id != undercover_id else role_ids["civilian"]
        voted = _act(ctx, actor, "vote", {"targetId": target})
        assert voted.status_code == 200, voted.content

    final = ctx["host"][0].get(f"{API}/{room_id}").json()
    assert final["room"]["status"] == "finished"
    assert Room.objects.get(pk=room_id).finished_at is not None
    assert final["game"]["phase"] == "game_over"
    assert final["game"]["winner"] == "civilians"
    assert final["game"]["reason"] == "all_infiltrators_out"
    assert final["game"]["civilianWord"]
    assert final["game"]["undercoverWord"]
    assert final["game"]["lastVote"]["eliminatedRole"] == "undercover"
    assert final["game"]["aliveCount"] == 3
    assert all(player["role"] is not None for player in final["players"])
    assert all(player["word"] is not None for player in final["players"])

    # A finished room refuses further gameplay but accepts host restart.
    closed = _act(ctx, ctx["host"], "advance")
    assert closed.status_code == 410


@pytest.mark.django_db
def test_tied_vote_advances_to_next_round() -> None:
    ctx = _start_room()
    room_id = str(ctx["room_id"])
    _reveal_and_clue(ctx)
    role_ids = _role_ids(room_id)
    room = Room.objects.get(pk=room_id)
    civilians = [player["id"] for player in room.state["players"] if player["role"] == "civilian"]
    by_member = {str(actor[2]): actor for actor in ctx["actors"]}
    targets = {
        role_ids["undercover"]: civilians[0],
        civilians[0]: role_ids["undercover"],
        civilians[1]: role_ids["undercover"],
        civilians[2]: civilians[0],
    }
    for member_id, target_id in targets.items():
        voted = _act(ctx, by_member[member_id], "vote", {"targetId": target_id})
        assert voted.status_code == 200, voted.content

    snapshot = ctx["host"][0].get(f"{API}/{room_id}").json()
    assert snapshot["game"]["phase"] == "vote_result"
    assert snapshot["game"]["lastVote"]["tie"] is True
    assert snapshot["game"]["lastVote"]["eliminatedId"] is None
    assert snapshot["game"]["aliveCount"] == 4
    assert snapshot["room"]["status"] == "active"

    advanced = _act(ctx, ctx["host"], "advance")
    assert advanced.status_code == 200, advanced.content
    payload = advanced.json()
    assert payload["game"]["round"] == 2
    assert payload["game"]["phase"] == "clues"
    assert payload["game"]["lastVote"] is None
    assert payload["game"]["speakerId"] == Room.objects.get(pk=room_id).state["players"][1]["id"]


@pytest.mark.django_db
def test_mr_white_guess_and_restart() -> None:
    ctx = _start_room(player_count=5, mr_white=True)
    room_id = str(ctx["room_id"])
    _reveal_and_clue(ctx)
    role_ids = _role_ids(room_id)
    mr_white_id = role_ids["mr_white"]
    by_member = {str(actor[2]): actor for actor in ctx["actors"]}
    for member_id, actor in by_member.items():
        target = mr_white_id if member_id != mr_white_id else role_ids["civilian"]
        voted = _act(ctx, actor, "vote", {"targetId": target})
        assert voted.status_code == 200, voted.content

    snapshot = ctx["host"][0].get(f"{API}/{room_id}").json()
    assert snapshot["game"]["phase"] == "mr_white"
    assert snapshot["room"]["status"] == "active"
    assert snapshot["game"]["civilianWord"] is None
    mr_white_player = next(player for player in snapshot["players"] if player["id"] == mr_white_id)
    assert mr_white_player["alive"] is False
    assert mr_white_player["role"] == "mr_white"
    assert mr_white_player["word"] is None

    word = Room.objects.get(pk=room_id).state["civilian_word"]
    guessed = _act(ctx, by_member[mr_white_id], "mrwhite_guess", {"guess": word.upper()})
    assert guessed.status_code == 200, guessed.content
    payload = guessed.json()
    assert payload["game"]["phase"] == "game_over"
    assert payload["game"]["winner"] == "mr_white"
    assert payload["game"]["mrWhiteGuess"]["correct"] is True
    assert payload["room"]["status"] == "finished"
    assert payload["game"]["civilianWord"] == word
    assert payload["game"]["undercoverWord"]

    non_host = _act(ctx, ctx["actors"][1], "restart")
    assert non_host.status_code == 403
    restarted = _act(ctx, ctx["host"], "restart")
    assert restarted.status_code == 200, restarted.content
    fresh = restarted.json()
    assert fresh["room"]["status"] == "active"
    assert fresh["game"]["phase"] == "reveal"
    assert fresh["game"]["civilianWord"] is None
    assert fresh["game"]["winner"] is None
    assert fresh["you"]["role"] in {"civilian", "undercover", "mr_white"}
    assert Room.objects.get(pk=room_id).finished_at is None


@pytest.mark.django_db
def test_wrong_mr_white_guess_continues_when_undercover_remains() -> None:
    ctx = _start_room(player_count=5, mr_white=True)
    room_id = str(ctx["room_id"])
    _reveal_and_clue(ctx)
    role_ids = _role_ids(room_id)
    mr_white_id = role_ids["mr_white"]
    by_member = {str(actor[2]): actor for actor in ctx["actors"]}
    for member_id, actor in by_member.items():
        target = mr_white_id if member_id != mr_white_id else role_ids["civilian"]
        voted = _act(ctx, actor, "vote", {"targetId": target})
        assert voted.status_code == 200, voted.content

    wrong = _act(ctx, by_member[mr_white_id], "mrwhite_guess", {"guess": "not-the-word"})
    assert wrong.status_code == 200, wrong.content
    payload = wrong.json()
    assert payload["room"]["status"] == "active"
    assert payload["game"]["phase"] == "vote_result"
    assert payload["game"]["winner"] is None
    assert payload["game"]["mrWhiteGuess"]["correct"] is False
    assert payload["game"]["aliveCount"] == 4

    advanced = _act(ctx, ctx["host"], "advance")
    assert advanced.status_code == 200
    assert advanced.json()["game"]["round"] == 2
    assert advanced.json()["game"]["phase"] == "clues"
