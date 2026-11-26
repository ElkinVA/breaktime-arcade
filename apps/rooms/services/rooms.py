"""Live Room lifecycle and server-authoritative commands."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.utils.translation import get_language

from apps.accounts.models import AnonymousIdentity, UserProfile
from apps.accounts.services.anonymous import (
    get_anonymous_identity,
    get_or_create_anonymous_identity,
)
from apps.catalog.models import Game
from apps.rooms.games.whos_undercover import (
    MAX_NAME_LENGTH,
    MAX_PLAYERS,
    MAX_UNDERCOVER,
    GameSetupError,
    assign_roles,
)
from apps.rooms.models import Room, RoomCommand, RoomMember

LOBBY_TTL_SECONDS = 30 * 60
ACTIVE_TTL_SECONDS = 2 * 60 * 60
IDLE_TTL_SECONDS = 30 * 60
HOST_TAKEOVER_SECONDS = 120
MEMBER_STALE_SECONDS = 5 * 60
MIN_PLAYERS = 4
LIVE_ROOM_GAMES = frozenset({"whos_undercover", "whos_undercover_live"})
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6
MAX_ROOM_ATTEMPTS = 8


class RoomError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


class RoomStale(RoomError):
    def __init__(self) -> None:
        super().__init__("E_ROOM_STALE", "Room state changed", 409)


def _now(value: datetime | None = None) -> datetime:
    current = value or timezone.now()
    if timezone.is_naive(current):
        return timezone.make_aware(current)
    return current


def _clean_name(value: str | None, fallback: str) -> str:
    name = " ".join(str(value or "").strip().split())[:MAX_NAME_LENGTH]
    return name or fallback


def _subject(request: HttpRequest, response: HttpResponse | None) -> tuple[str, UUID, str]:
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        nickname = (
            UserProfile.objects.filter(user=user).values_list("nickname", flat=True).first()
            or user.get_username()
        )
        return Room.SUBJECT_USER, user.pk, _clean_name(nickname, "Host")
    identity: AnonymousIdentity | None
    if response is None:
        identity = get_anonymous_identity(request)
    else:
        identity = get_or_create_anonymous_identity(request, response)
    if identity is None:
        raise RoomError("E_AUTH_REQUIRED", "Room membership required", 401)
    return Room.SUBJECT_ANON, identity.id, "Guest"


def _room_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def _expire_if_needed(room: Room, current: datetime) -> None:
    expired = room.status in {Room.STATUS_LOBBY, Room.STATUS_ACTIVE} and current > room.expires_at
    idle = (
        room.status == Room.STATUS_ACTIVE
        and (current - room.last_activity_at).total_seconds() > IDLE_TTL_SECONDS
    )
    if expired or idle:
        room.status = Room.STATUS_EXPIRED
        room.finished_at = room.finished_at or current
        room.version += 1
        room.save(update_fields=["status", "finished_at", "version", "updated_at"])


def _host_member(room: Room) -> RoomMember | None:
    return room.members.filter(role=RoomMember.ROLE_HOST).order_by("created_at").first()


def _member_for_subject(room: Room, subject_type: str, subject_id: UUID) -> RoomMember | None:
    return room.members.filter(subject_type=subject_type, subject_id=subject_id).first()


def _public_players(room: Room) -> list[dict[str, Any]]:
    state = room.state or {}
    game_players = {
        str(player.get("id")): player
        for player in state.get("players", [])
        if isinstance(player, dict)
    }
    finished = room.status == Room.STATUS_FINISHED
    result = []
    members = room.members.order_by("created_at")
    if not finished:
        members = members.filter(active=True)
    for member in members:
        player = game_players.get(str(member.id))
        role = None
        word = None
        alive = True
        eliminated_round = None
        if player:
            alive = bool(player.get("alive", True))
            eliminated_round = player.get("eliminated_round")
            if finished or not alive:
                role = player.get("revealed_role") or player.get("role")
            if finished:
                word = player.get("word")
        result.append(
            {
                "id": str(member.id),
                "name": member.name,
                "isHost": member.role == RoomMember.ROLE_HOST,
                "ready": member.ready,
                "alive": alive,
                "eliminatedRound": eliminated_round,
                "role": role,
                "word": word,
            }
        )
    return result


def _public_last_vote(room: Room) -> dict[str, Any] | None:
    vote = (room.state or {}).get("last_vote")
    if not isinstance(vote, dict):
        return None
    counts = vote.get("counts")
    if not isinstance(counts, dict):
        return None
    return {
        "counts": {str(key): int(value) for key, value in counts.items()},
        "eliminatedId": vote.get("eliminatedId"),
        "eliminatedRole": vote.get("eliminatedRole"),
        "tie": bool(vote.get("tie")),
        "round": vote.get("round"),
    }


def snapshot(room: Room, member: RoomMember, current: datetime | None = None) -> dict[str, Any]:
    """Return a viewer-scoped snapshot; never expose other members' secrets."""
    state = room.state or {}
    game_players = {
        str(player.get("id")): player
        for player in state.get("players", [])
        if isinstance(player, dict)
    }
    own = game_players.get(str(member.id))
    host = _host_member(room)
    finished = room.status == Room.STATUS_FINISHED
    game = {
        "phase": state.get("phase", "lobby"),
        "round": state.get("round", 1),
        "categoryId": state.get("setup", {}).get("category_id"),
        "categoryName": state.get("setup", {}).get("category_name"),
        "revealedCount": state.get("revealed_count", 0),
        "aliveCount": (
            sum(1 for player in game_players.values() if player.get("alive", True))
            if game_players
            else room.members.filter(active=True).count()
        ),
        "speakerId": _speaker_id(state),
        "votesCast": len(state.get("votes", {})),
        "winner": state.get("winner"),
        "reason": state.get("reason"),
        "lastVote": _public_last_vote(room),
        "mrWhiteGuess": state.get("mr_white_guess"),
        "civilianWord": state.get("civilian_word") if finished else None,
        "undercoverWord": state.get("undercover_word") if finished else None,
    }
    return {
        "room": {
            "id": str(room.id),
            "code": room.code,
            "status": room.status,
            "version": room.version,
            "maxPlayers": room.max_players,
            "hostMemberId": str(host.id) if host else None,
            "expiresAt": room.expires_at.isoformat(),
            "createdAt": room.created_at.isoformat(),
        },
        "you": {
            "memberId": str(member.id),
            "name": member.name,
            "isHost": member.role == RoomMember.ROLE_HOST,
            "ready": member.ready,
            "alive": bool(own.get("alive", True)) if own else True,
            "revealed": bool(own.get("revealed", False)) if own else False,
            "role": own.get("role") if own else None,
            "word": own.get("word") if own else None,
            "voteTargetId": (state.get("votes") or {}).get(str(member.id)),
        },
        "players": _public_players(room),
        "game": game,
        "setup": {
            "undercoverCount": state.get("setup", {}).get("undercover_count"),
            "mrWhite": state.get("setup", {}).get("mr_white"),
        },
    }


def _speaker_id(state: dict[str, Any]) -> str | None:
    if state.get("phase") != "clues":
        return None
    alive = [player for player in state.get("players", []) if player.get("alive", True)]
    if not alive:
        return None
    index = int(state.get("speaker_index", 0)) % len(alive)
    return str(alive[index].get("id"))


def create_room(
    request: HttpRequest,
    response: HttpResponse,
    *,
    game_id: str,
    max_players: int = MAX_PLAYERS,
    undercover_count: int = 1,
    mr_white: bool = False,
    category_id: str | None = None,
    name: str | None = None,
) -> tuple[Room, RoomMember]:
    if not MIN_PLAYERS <= max_players <= MAX_PLAYERS:
        raise RoomError("E_PLAYERS", "Room size is invalid")
    if not 1 <= undercover_count <= MAX_UNDERCOVER:
        raise RoomError("E_UNDERCOVER", "Infiltrator count is invalid")
    infiltrators = undercover_count + (1 if mr_white else 0)
    if max_players - infiltrators <= infiltrators:
        raise RoomError("E_BALANCE", "Too many infiltrators for this room size")
    game = (
        Game.objects.select_related("current_version")
        .filter(
            technical_id=game_id,
            technical_id__in=LIVE_ROOM_GAMES,
            status=Game.STATUS_PUBLISHED,
        )
        .first()
    )
    if game is None or game.current_version is None:
        raise RoomError("E_GAME_INVALID", "Game is not available", 404)
    subject_type, subject_id, fallback_name = _subject(request, response)
    display_name = _clean_name(name, fallback_name)
    current = _now()
    language = get_language() or game.default_language
    last_error: IntegrityError | None = None
    for _ in range(MAX_ROOM_ATTEMPTS):
        try:
            with transaction.atomic():
                room = Room.objects.create(
                    code=_room_code(),
                    game=game,
                    game_version=game.current_version,
                    host_subject_type=subject_type,
                    host_subject_id=subject_id,
                    status=Room.STATUS_LOBBY,
                    max_players=max_players,
                    state={
                        "phase": "lobby",
                        "setup": {
                            "undercover_count": undercover_count,
                            "mr_white": mr_white,
                            "category_id": category_id,
                            "language": language,
                        },
                    },
                    version=1,
                    expires_at=current + timedelta(seconds=LOBBY_TTL_SECONDS),
                    last_activity_at=current,
                )
                member = RoomMember.objects.create(
                    room=room,
                    subject_type=subject_type,
                    subject_id=subject_id,
                    name=display_name,
                    role=RoomMember.ROLE_HOST,
                    ready=True,
                    last_seen_at=current,
                )
            return room, member
        except IntegrityError as exc:
            last_error = exc
    raise RoomError("E_ROOM_CREATE", "Could not allocate a room code", 503) from last_error


def join_room(
    request: HttpRequest,
    response: HttpResponse,
    *,
    code: str,
    name: str | None = None,
) -> tuple[Room, RoomMember]:
    subject_type, subject_id, fallback_name = _subject(request, response)
    current = _now()
    with transaction.atomic():
        room = Room.objects.select_for_update().filter(code=code.strip().upper()).first()
        if room is None:
            raise RoomError("E_ROOM_NOT_FOUND", "Room not found", 404)
        _expire_if_needed(room, current)
        if room.status not in {Room.STATUS_LOBBY, Room.STATUS_ACTIVE}:
            raise RoomError("E_ROOM_CLOSED", "Room is closed", 410)
        member = _member_for_subject(room, subject_type, subject_id)
        if member is not None:
            reactivated = not member.active
            member.active = True
            member.last_seen_at = current
            renamed = False
            if name:
                new_name = _clean_name(name, member.name)
                renamed = new_name != member.name
                member.name = new_name
            member.save(update_fields=["active", "last_seen_at", "name", "updated_at"])
            if reactivated or renamed:
                room.version += 1
            room.last_activity_at = current
            if room.status == Room.STATUS_LOBBY:
                room.expires_at = current + timedelta(seconds=LOBBY_TTL_SECONDS)
            room.save(update_fields=["version", "last_activity_at", "expires_at", "updated_at"])
            return room, member
        if room.status == Room.STATUS_ACTIVE:
            raise RoomError("E_ROOM_STARTED", "Room has already started", 409)
        if room.members.filter(active=True).count() >= room.max_players:
            raise RoomError("E_ROOM_FULL", "Room is full", 409)
        display_name = _clean_name(name, fallback_name)
        member = RoomMember.objects.create(
            room=room,
            subject_type=subject_type,
            subject_id=subject_id,
            name=display_name,
            role=RoomMember.ROLE_PLAYER,
            last_seen_at=current,
        )
        room.version += 1
        room.last_activity_at = current
        if room.status == Room.STATUS_LOBBY:
            room.expires_at = current + timedelta(seconds=LOBBY_TTL_SECONDS)
        room.save(update_fields=["version", "last_activity_at", "expires_at", "updated_at"])
    return room, member


def get_membership(request: HttpRequest, room_id: UUID) -> tuple[Room, RoomMember]:
    subject_type, subject_id, _ = _subject(request, None)
    room = Room.objects.filter(pk=room_id).first()
    if room is None:
        raise RoomError("E_ROOM_NOT_FOUND", "Room not found", 404)
    member = _member_for_subject(room, subject_type, subject_id)
    if member is None or not member.active:
        raise RoomError("E_NOT_MEMBER", "Not a room member", 403)
    return room, member


def read_room(request: HttpRequest, room_id: UUID) -> dict[str, Any]:
    room, member = get_membership(request, room_id)
    current = _now()
    with transaction.atomic():
        locked = Room.objects.select_for_update().get(pk=room.pk)
        _expire_if_needed(locked, current)
        if member.active and (current - member.last_seen_at).total_seconds() >= 10:
            member.last_seen_at = current
            member.save(update_fields=["last_seen_at", "updated_at"])
        changed = _sweep_stale_members(locked, current)
        if changed:
            member.refresh_from_db()
            locked.version += 1
        if changed or (current - locked.last_activity_at).total_seconds() >= 60:
            locked.last_activity_at = current
            locked.save(
                update_fields=[
                    "state",
                    "status",
                    "finished_at",
                    "version",
                    "last_activity_at",
                    "host_subject_type",
                    "host_subject_id",
                    "updated_at",
                ]
            )
        return snapshot(locked, member, current)


def set_ready(request: HttpRequest, room_id: UUID, *, ready: bool) -> dict[str, Any]:
    return execute_command(
        request,
        room_id,
        command="ready",
        payload={"ready": bool(ready)},
        request_id=None,
        expected_version=None,
    )


def leave_room(request: HttpRequest, room_id: UUID) -> None:
    subject_type, subject_id, _ = _subject(request, None)
    current = _now()
    with transaction.atomic():
        locked = Room.objects.select_for_update().filter(pk=room_id).first()
        if locked is None:
            raise RoomError("E_ROOM_NOT_FOUND", "Room not found", 404)
        current_member = _member_for_subject(locked, subject_type, subject_id)
        if current_member is None:
            raise RoomError("E_NOT_MEMBER", "Not a room member", 403)
        if not current_member.active:
            return
        if current_member.role != RoomMember.ROLE_HOST and locked.status == Room.STATUS_ACTIVE:
            _forfeit_player(locked, current_member)
        current_member.active = False
        current_member.last_seen_at = current
        promoted: RoomMember | None = None
        if current_member.role == RoomMember.ROLE_HOST and locked.status in {
            Room.STATUS_LOBBY,
            Room.STATUS_ACTIVE,
        }:
            promoted = (
                locked.members.filter(active=True)
                .exclude(pk=current_member.pk)
                .order_by("created_at")
                .first()
            )
            if promoted is None:
                locked.status = Room.STATUS_ABANDONED
                locked.finished_at = current
            else:
                if locked.status == Room.STATUS_ACTIVE:
                    _forfeit_player(locked, current_member)
                promoted.role = RoomMember.ROLE_HOST
                promoted.save(update_fields=["role", "updated_at"])
                current_member.role = RoomMember.ROLE_PLAYER
                locked.host_subject_type = promoted.subject_type
                locked.host_subject_id = promoted.subject_id
        current_member.save(update_fields=["active", "last_seen_at", "role", "updated_at"])
        if locked.state.get("phase") == "game_over":
            locked.status = Room.STATUS_FINISHED
            locked.finished_at = locked.finished_at or current
        locked.version += 1
        locked.last_activity_at = current
        locked.save(
            update_fields=[
                "state",
                "status",
                "finished_at",
                "version",
                "last_activity_at",
                "host_subject_type",
                "host_subject_id",
                "updated_at",
            ]
        )


def execute_command(
    request: HttpRequest,
    room_id: UUID,
    *,
    command: str,
    payload: dict[str, Any],
    request_id: UUID | None,
    expected_version: int | None,
) -> dict[str, Any]:
    subject_type, subject_id, _ = _subject(request, None)
    current = _now()
    with transaction.atomic():
        room = Room.objects.select_for_update().filter(pk=room_id).first()
        if room is None:
            raise RoomError("E_ROOM_NOT_FOUND", "Room not found", 404)
        member = _member_for_subject(room, subject_type, subject_id)
        if member is None or not member.active:
            raise RoomError("E_NOT_MEMBER", "Not a room member", 403)
        _expire_if_needed(room, current)
        if (
            request_id is not None
            and RoomCommand.objects.filter(room=room, request_id=request_id).exists()
        ):
            return snapshot(room, member, current)
        allowed_status = {Room.STATUS_LOBBY, Room.STATUS_ACTIVE}
        restart_after_finish = command == "restart" and room.status == Room.STATUS_FINISHED
        if room.status not in allowed_status and not restart_after_finish:
            raise RoomError("E_ROOM_CLOSED", "Room is closed", 410)
        if expected_version is not None and expected_version != room.version:
            raise RoomStale()
        member.last_seen_at = current
        member.save(update_fields=["last_seen_at", "updated_at"])
        if command == "ready":
            _command_ready(room, member, payload)
        elif command == "start":
            _command_start(room, member, current)
        elif command == "reveal_ack":
            _command_reveal_ack(room, member)
        elif command == "advance_clue":
            _command_advance_clue(room, member)
        elif command == "vote":
            _command_vote(room, member, payload)
        elif command == "advance":
            _command_advance(room, member)
        elif command == "mrwhite_guess":
            _command_mrwhite_guess(room, member, payload)
        elif command == "restart":
            _command_restart(room, member, current)
        elif command == "claim_host":
            _command_claim_host(room, member, current)
        else:
            raise RoomError("E_COMMAND_INVALID", "Unknown command")
        if room.state.get("phase") == "game_over":
            room.status = Room.STATUS_FINISHED
            room.finished_at = room.finished_at or current
        room.version += 1
        room.last_activity_at = current
        room.save(
            update_fields=[
                "state",
                "version",
                "status",
                "started_at",
                "finished_at",
                "expires_at",
                "last_activity_at",
                "host_subject_type",
                "host_subject_id",
                "updated_at",
            ]
        )
        if request_id is not None:
            RoomCommand.objects.create(
                room=room,
                member=member,
                request_id=request_id,
                command=command,
            )
        return snapshot(room, member, current)


def _command_ready(room: Room, member: RoomMember, payload: dict[str, Any]) -> None:
    if room.status != Room.STATUS_LOBBY:
        raise RoomError("E_PHASE", "Room is not in the lobby", 409)
    if member.role == RoomMember.ROLE_HOST:
        raise RoomError("E_HOST_READY", "Host is always ready", 409)
    member.ready = bool(payload.get("ready", True))
    member.save(update_fields=["ready", "updated_at"])


def _command_start(room: Room, member: RoomMember, current: datetime) -> None:
    if member.role != RoomMember.ROLE_HOST:
        raise RoomError("E_HOST_ONLY", "Only the host can start", 403)
    if room.status != Room.STATUS_LOBBY:
        raise RoomError("E_PHASE", "Room is not in the lobby", 409)
    players = list(room.members.filter(active=True).order_by("created_at"))
    if len(players) < MIN_PLAYERS:
        raise RoomError("E_NOT_ENOUGH_PLAYERS", f"At least {MIN_PLAYERS} players are required", 409)
    if any(not player.ready for player in players if player.role != RoomMember.ROLE_HOST):
        raise RoomError("E_NOT_READY", "All players must be ready", 409)
    setup = room.state.get("setup", {})
    try:
        state = assign_roles(
            [{"id": player.id, "name": player.name} for player in players],
            undercover_count=int(setup.get("undercover_count", 1)),
            mr_white=bool(setup.get("mr_white", False)),
            category_id=setup.get("category_id"),
            language=setup.get("language"),
        )
    except GameSetupError as exc:
        raise RoomError(exc.code, "Game setup is invalid", 409) from exc
    room.state = state
    room.status = Room.STATUS_ACTIVE
    room.started_at = current
    room.expires_at = current + timedelta(seconds=ACTIVE_TTL_SECONDS)
    room.last_activity_at = current
    for player in players:
        player.ready = True
        player.save(update_fields=["ready", "updated_at"])


def _command_claim_host(room: Room, member: RoomMember, current: datetime) -> None:
    if room.status not in {Room.STATUS_LOBBY, Room.STATUS_ACTIVE}:
        raise RoomError("E_PHASE", "Host cannot be claimed in this phase", 409)
    if room.status == Room.STATUS_ACTIVE:
        player = _player(room.state, member)
        if player is None or not player.get("alive", True):
            raise RoomError("E_PLAYER_OUT", "Only an active player can claim host", 409)
    host = _host_member(room)
    if host is not None and host.pk == member.pk:
        raise RoomError("E_ALREADY_HOST", "You are already the host", 409)
    if host is not None and (current - host.last_seen_at).total_seconds() < HOST_TAKEOVER_SECONDS:
        raise RoomError("E_HOST_ACTIVE", "Host is still active", 409)
    if host is not None:
        host.role = RoomMember.ROLE_PLAYER
        host.save(update_fields=["role", "updated_at"])
    member.role = RoomMember.ROLE_HOST
    member.save(update_fields=["role", "updated_at"])
    room.host_subject_type = member.subject_type
    room.host_subject_id = member.subject_id


def _player(state: dict[str, Any], member: RoomMember) -> dict[str, Any] | None:
    for player in state.get("players", []):
        if str(player.get("id")) == str(member.id):
            return cast(dict[str, Any], player)
    return None


def _alive(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [player for player in state.get("players", []) if player.get("alive", True)]


def _require_phase(room: Room, *phases: str) -> None:
    if (room.state or {}).get("phase") not in phases:
        raise RoomError("E_PHASE", "Command is not valid in this phase", 409)


def _require_active(room: Room) -> None:
    if room.status != Room.STATUS_ACTIVE:
        raise RoomError("E_PHASE", "Command is not valid in this phase", 409)


def _require_host(member: RoomMember) -> None:
    if member.role != RoomMember.ROLE_HOST:
        raise RoomError("E_HOST_ONLY", "Only the host can do that", 403)


def _require_player(state: dict[str, Any], member: RoomMember) -> dict[str, Any]:
    player = _player(state, member)
    if player is None or not player.get("alive", True):
        raise RoomError("E_PLAYER_OUT", "Player is not active", 409)
    return player


def _normalize_guess(value: str) -> str:
    return " ".join(str(value or "").strip().split()).lower().rstrip(".!?,;:")


def _command_reveal_ack(room: Room, member: RoomMember) -> None:
    _require_active(room)
    _require_phase(room, "reveal")
    player = _require_player(room.state, member)
    if not player.get("revealed"):
        player["revealed"] = True
        room.state["revealed_count"] = int(room.state.get("revealed_count", 0)) + 1
    players = room.state.get("players", [])
    if all(item.get("revealed") for item in players):
        room.state["phase"] = "clues"
        room.state["speaker_index"] = 0
        room.state["spoken_count"] = 0


def _command_advance_clue(room: Room, member: RoomMember) -> None:
    _require_active(room)
    _require_host(member)
    _require_phase(room, "clues")
    alive = _alive(room.state)
    spoken = int(room.state.get("spoken_count", 0)) + 1
    if spoken >= len(alive):
        room.state["phase"] = "vote"
        room.state["votes"] = {}
        room.state["spoken_count"] = 0
    else:
        room.state["spoken_count"] = spoken
        room.state["speaker_index"] = spoken % max(1, len(alive))


def _command_vote(room: Room, member: RoomMember, payload: dict[str, Any]) -> None:
    _require_active(room)
    _require_phase(room, "vote")
    player = _require_player(room.state, member)
    target_id = str(payload.get("targetId") or "")
    target = next((item for item in _alive(room.state) if str(item.get("id")) == target_id), None)
    if target is None:
        raise RoomError("E_TARGET", "Target is not active", 422)
    if str(target["id"]) == str(player["id"]):
        raise RoomError("E_SELF_VOTE", "You cannot vote for yourself", 422)
    votes = room.state.setdefault("votes", {})
    if str(member.id) in votes:
        raise RoomError("E_ALREADY_VOTED", "Vote already cast", 409)
    votes[str(member.id)] = str(target["id"])
    if len(votes) >= len(_alive(room.state)):
        _resolve_vote(room.state)


def _resolve_vote(state: dict[str, Any]) -> None:
    votes = state.get("votes", {})
    counts: dict[str, int] = {}
    for target_id in votes.values():
        counts[str(target_id)] = counts.get(str(target_id), 0) + 1
    best = 0
    leaders: list[str] = []
    for target_id, count in counts.items():
        if count > best:
            best = count
            leaders = [target_id]
        elif count == best:
            leaders.append(target_id)
    tie = len(leaders) != 1
    eliminated_id = None if tie else leaders[0]
    eliminated_role = None
    eliminated = None
    if eliminated_id is not None:
        eliminated = next(
            (
                player
                for player in state.get("players", [])
                if str(player.get("id")) == eliminated_id
            ),
            None,
        )
        if eliminated is not None:
            eliminated["alive"] = False
            eliminated["eliminated_round"] = state.get("round", 1)
            eliminated["revealed_role"] = eliminated["role"]
            eliminated_role = eliminated["role"]
    state["last_vote"] = {
        "counts": counts,
        "eliminatedId": eliminated_id,
        "eliminatedRole": eliminated_role,
        "tie": tie,
        "round": state.get("round", 1),
    }
    state.setdefault("history", []).append(
        {
            "type": "vote",
            "round": state.get("round", 1),
            "counts": counts,
            "eliminatedId": eliminated_id,
            "tie": tie,
        }
    )
    state["votes"] = {}
    if eliminated is not None and eliminated["role"] == "mr_white":
        state["phase"] = "mr_white"
        return
    state["phase"] = "vote_result"
    _evaluate_winner(state)


def _evaluate_winner(state: dict[str, Any]) -> None:
    if state.get("winner"):
        state["phase"] = "game_over"
        return
    alive = _alive(state)
    undercover = sum(1 for player in alive if player.get("role") == "undercover")
    mr_white = sum(1 for player in alive if player.get("role") == "mr_white")
    civilians = sum(1 for player in alive if player.get("role") == "civilian")
    if undercover + mr_white == 0:
        state["winner"] = "civilians"
        state["reason"] = "all_infiltrators_out"
        state["phase"] = "game_over"
    elif undercover + mr_white >= civilians:
        state["winner"] = "undercover"
        state["reason"] = "infiltrators_equal"
        state["phase"] = "game_over"


def _forfeit_player(room: Room, member: RoomMember) -> bool:
    """Remove a player who explicitly left an active game without stalling it."""
    state = room.state or {}
    room.state = state
    phase = state.get("phase")
    if room.status != Room.STATUS_ACTIVE or phase == "game_over":
        return False
    player = _player(state, member)
    if player is None:
        return False
    member_id = str(member.id)
    if phase == "mr_white" and player.get("role") == "mr_white":
        state["mr_white_guess"] = {"guess": "", "correct": False}
        state.setdefault("history", []).append(
            {"type": "mr_white_guess", "round": state.get("round", 1), "correct": False}
        )
        state["phase"] = "vote_result"
        _evaluate_winner(state)
        return True
    if not player.get("alive", True):
        return False
    player["alive"] = False
    player["eliminated_round"] = state.get("round", 1)
    player["revealed_role"] = player.get("role")
    if not player.get("revealed"):
        player["revealed"] = True
        state["revealed_count"] = int(state.get("revealed_count", 0)) + 1
    phase = state.get("phase")
    if phase == "reveal":
        if all(item.get("revealed") for item in state.get("players", [])):
            state["phase"] = "clues"
            state["speaker_index"] = 0
            state["spoken_count"] = 0
    elif phase == "clues":
        alive = _alive(state)
        if not alive:
            state["phase"] = "vote_result"
            _evaluate_winner(state)
        else:
            state["speaker_index"] = int(state.get("speaker_index", 0)) % len(alive)
            if int(state.get("spoken_count", 0)) >= len(alive):
                state["phase"] = "vote"
                state["votes"] = {}
                state["spoken_count"] = 0
    elif phase == "vote":
        votes = state.setdefault("votes", {})
        for voter, target in list(votes.items()):
            if voter == member_id or str(target) == member_id:
                votes.pop(voter, None)
        alive = _alive(state)
        if not alive:
            state["phase"] = "vote_result"
            _evaluate_winner(state)
        elif len(votes) >= len(alive):
            _resolve_vote(state)
    elif phase in {"vote_result", "mr_white"}:
        _evaluate_winner(state)
    _evaluate_winner(state)
    return True


def _sweep_stale_members(room: Room, current: datetime) -> bool:
    """Forfeit members that stopped polling; keeps an active game moving."""
    if room.status != Room.STATUS_ACTIVE:
        return False
    room.state = room.state or {}
    cutoff = current - timedelta(seconds=MEMBER_STALE_SECONDS)
    stale = list(room.members.filter(active=True, last_seen_at__lt=cutoff).order_by("created_at"))
    if not stale:
        return False
    changed = False
    for member in stale:
        if member.role == RoomMember.ROLE_HOST:
            successor = (
                room.members.filter(active=True)
                .exclude(pk=member.pk)
                .exclude(last_seen_at__lt=cutoff)
                .order_by("created_at")
                .first()
            )
            if successor is None:
                room.status = Room.STATUS_ABANDONED
                room.finished_at = room.finished_at or current
                member.active = False
                member.save(update_fields=["active", "updated_at"])
                changed = True
                continue
            successor.role = RoomMember.ROLE_HOST
            successor.save(update_fields=["role", "updated_at"])
            member.role = RoomMember.ROLE_PLAYER
            room.host_subject_type = successor.subject_type
            room.host_subject_id = successor.subject_id
        _forfeit_player(room, member)
        member.active = False
        member.save(update_fields=["active", "role", "updated_at"])
        changed = True
    if room.state.get("phase") == "game_over":
        room.status = Room.STATUS_FINISHED
        room.finished_at = room.finished_at or current
    return changed


def _command_advance(room: Room, member: RoomMember) -> None:
    _require_active(room)
    _require_host(member)
    _require_phase(room, "vote_result")
    round_number = int(room.state.get("round", 1)) + 1
    alive = _alive(room.state)
    room.state["round"] = round_number
    room.state["phase"] = "clues"
    room.state["votes"] = {}
    room.state["spoken_count"] = 0
    room.state["speaker_index"] = (round_number - 1) % max(1, len(alive))
    room.state["last_vote"] = None
    room.state["mr_white_guess"] = None


def _command_mrwhite_guess(room: Room, member: RoomMember, payload: dict[str, Any]) -> None:
    _require_active(room)
    _require_phase(room, "mr_white")
    player = _player(room.state, member)
    if player is None:
        raise RoomError("E_PLAYER_OUT", "Player is not in this game", 409)
    if player.get("role") != "mr_white":
        raise RoomError("E_FORBIDDEN", "Only Mr. White can guess", 403)
    guess = _normalize_guess(str(payload.get("guess") or ""))
    correct = bool(guess) and guess == _normalize_guess(str(room.state.get("civilian_word", "")))
    room.state["mr_white_guess"] = {
        "guess": str(payload.get("guess") or "")[:40],
        "correct": correct,
    }
    room.state.setdefault("history", []).append(
        {"type": "mr_white_guess", "round": room.state.get("round", 1), "correct": correct}
    )
    if correct:
        room.state["winner"] = "mr_white"
        room.state["reason"] = "mr_white_guessed"
        room.state["phase"] = "game_over"
    else:
        room.state["phase"] = "vote_result"
        _evaluate_winner(room.state)


def _command_restart(room: Room, member: RoomMember, current: datetime) -> None:
    _require_host(member)
    _require_phase(room, "game_over")
    players = list(room.members.filter(active=True).order_by("created_at"))
    setup = room.state.get("setup", {})
    try:
        room.state = assign_roles(
            [{"id": player.id, "name": player.name} for player in players],
            undercover_count=int(setup.get("undercover_count", 1)),
            mr_white=bool(setup.get("mr_white", False)),
            category_id=setup.get("category_id"),
            language=setup.get("language"),
        )
    except GameSetupError as exc:
        raise RoomError(exc.code, "Game setup is invalid", 409) from exc
    room.status = Room.STATUS_ACTIVE
    room.started_at = current
    room.finished_at = None
    room.expires_at = current + timedelta(seconds=ACTIVE_TTL_SECONDS)
    room.last_activity_at = current


def _anonymize_subject_pass(subject_type: str, subject_id: UUID, current: datetime) -> int:
    room_ids = list(
        RoomMember.objects.filter(subject_type=subject_type, subject_id=subject_id)
        .values_list("room_id", flat=True)
        .distinct()
    )
    if not room_ids:
        return 0
    rooms = list(Room.objects.select_for_update().filter(pk__in=room_ids).order_by("pk"))
    members = list(RoomMember.objects.select_for_update().filter(room__in=rooms).order_by("pk"))
    changed_rooms: set[UUID] = set()
    for room in rooms:
        if room.status in {Room.STATUS_LOBBY, Room.STATUS_ACTIVE}:
            room.status = Room.STATUS_ABANDONED
            room.finished_at = current
            room.version += 1
            room.save(update_fields=["status", "finished_at", "version", "updated_at"])
        if room.host_subject_type == subject_type and room.host_subject_id == subject_id:
            room.host_subject_id = uuid4()
            room.save(update_fields=["host_subject_id", "updated_at"])
    for member in members:
        if member.subject_type != subject_type or member.subject_id != subject_id:
            continue
        old_id = str(member.id)
        member.subject_id = uuid4()
        member.name = "Player"
        member.active = False
        member.ready = False
        member.save(update_fields=["subject_id", "name", "active", "ready", "updated_at"])
        room = next(item for item in rooms if item.pk == member.room_id)
        for player in room.state.get("players", []):
            if str(player.get("id")) == old_id:
                player["name"] = "Player"
                changed_rooms.add(room.pk)
    for room in rooms:
        if room.pk in changed_rooms:
            room.save(update_fields=["state", "updated_at"])
    return len(rooms)


def anonymize_subject(subject_type: str, subject_id: UUID) -> int:
    """Scrub a deleted account's room identity and close affected rooms.

    Rooms are short-lived, but an account deletion must not leave a nickname
    or a stable subject identifier in room membership/state for the retention
    window. Other participants keep the finished room snapshot. A second pass
    catches memberships committed concurrently with the first scan.
    """
    current = _now()
    total = 0
    with transaction.atomic():
        for _ in range(2):
            processed = _anonymize_subject_pass(subject_type, subject_id, current)
            if processed == 0:
                break
            total += processed
    return total


def expire_rooms(*, now: datetime | None = None) -> int:
    current = _now(now)
    idle_cutoff = current - timedelta(seconds=IDLE_TTL_SECONDS)
    with transaction.atomic():
        rooms = list(
            Room.objects.select_for_update()
            .filter(status__in=[Room.STATUS_LOBBY, Room.STATUS_ACTIVE])
            .filter(
                Q(expires_at__lt=current)
                | Q(status=Room.STATUS_ACTIVE, last_activity_at__lt=idle_cutoff)
            )
        )
        for room in rooms:
            _expire_if_needed(room, current)
    return len(rooms)


def cleanup_rooms(*, now: datetime | None = None, retention_hours: int = 24) -> int:
    current = _now(now)
    cutoff = current - timedelta(hours=retention_hours)
    with transaction.atomic():
        room_ids = list(
            Room.objects.select_for_update(skip_locked=True)
            .filter(
                status__in=[Room.STATUS_FINISHED, Room.STATUS_ABANDONED, Room.STATUS_EXPIRED],
                finished_at__lt=cutoff,
            )
            .values_list("pk", flat=True)
        )
        if room_ids:
            Room.objects.filter(pk__in=room_ids).delete()
    return len(room_ids)
