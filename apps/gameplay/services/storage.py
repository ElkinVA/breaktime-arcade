"""Game storage document (§2.22): revision/If-Match, 64 KiB, guest TTL."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from uuid import UUID

from django.db import DatabaseError, IntegrityError, connection, transaction

from apps.accounts.models import AnonymousIdentity, User
from apps.accounts.services.anonymous import get_anonymous_identity
from apps.catalog.models import Game
from apps.gameplay.models import GameSession, GameStorage
from apps.gameplay.services.sessions import SessionError, _now

MAX_BYTES = 65_536
MAX_KEYS = 256
MAX_DEPTH = 8
MAX_KEY_LENGTH = 128
GUEST_TTL_DAYS = 90


def _subject(request) -> tuple[str, User | None, AnonymousIdentity | None]:
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return GameStorage.SUBJECT_USER, user, None
    identity = get_anonymous_identity(request)
    if identity is None:
        raise SessionError("E_AUTH_REQUIRED", "Authentication required", 403)
    return GameStorage.SUBJECT_ANON, None, identity


def _active_session(subject_type: str, user, identity, game: Game) -> GameSession:
    if subject_type == GameStorage.SUBJECT_USER:
        session = (
            GameSession.objects.filter(
                game=game,
                subject_type=GameSession.SUBJECT_USER,
                subject_id=user.id,
                state=GameSession.STATE_ACTIVE,
            )
            .order_by("-activated_at")
            .first()
        )
    else:
        session = (
            GameSession.objects.filter(
                game=game,
                subject_type=GameSession.SUBJECT_ANON,
                subject_id=identity.id,
                state=GameSession.STATE_ACTIVE,
            )
            .order_by("-activated_at")
            .first()
        )
    if session is None:
        raise SessionError("E_SESSION_INVALID", "Session is not active", 403)
    return session


def _lock_storage(subject_type: str, subject_id: UUID, game_id: UUID) -> None:
    raw = f"storage:{subject_type}:{subject_id}:{game_id}".encode()
    key = int.from_bytes(hashlib.blake2b(raw, digest_size=8).digest(), "big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])


def _published_game(game_id: str) -> Game:
    game = Game.objects.filter(technical_id=game_id, status=Game.STATUS_PUBLISHED).first()
    if game is None:
        raise SessionError("E_SESSION_INVALID", "Game is not available", 404)
    return game


def _validate(value: object, *, depth: int = 0, counter: list[int] | None = None) -> None:
    if counter is None:
        counter = [0]
    if depth > MAX_DEPTH:
        raise SessionError("E_INVALID_REQUEST", "Storage depth is too large", 400)
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > MAX_KEY_LENGTH:
                raise SessionError("E_INVALID_REQUEST", "Storage key is invalid", 400)
            counter[0] += 1
            if counter[0] > MAX_KEYS:
                raise SessionError("E_STORAGE_QUOTA", "Storage has too many keys", 413)
            _validate(item, depth=depth + 1, counter=counter)
    elif isinstance(value, list):
        for item in value:
            _validate(item, depth=depth + 1, counter=counter)


def _serialized_bytes(data: dict[str, object]) -> int:
    try:
        encoded = json.dumps(
            data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError) as exc:
        raise SessionError("E_INVALID_REQUEST", "Storage data is invalid", 400) from exc
    return len(encoded)


def validate_document(data: object) -> dict[str, object]:
    if not isinstance(data, dict):
        raise SessionError("E_INVALID_REQUEST", "Storage data must be an object", 400)
    _validate(data)
    if _serialized_bytes(data) > MAX_BYTES:
        raise SessionError("E_STORAGE_QUOTA", "Storage quota exceeded", 413)
    return data


def _row(subject_type: str, user, identity, game: Game):
    if subject_type == GameStorage.SUBJECT_USER:
        return GameStorage.objects.filter(game=game, subject_type=subject_type, user=user).first()
    return GameStorage.objects.filter(game=game, subject_type=subject_type, anon=identity).first()


def _expired(row: GameStorage, now: datetime) -> bool:
    return row.expires_at is not None and row.expires_at <= now


def _quota_violation(exc: DatabaseError) -> bool:
    cause = exc.__cause__
    return getattr(cause, "sqlstate", None) == "23514" or "23514" in str(exc)


def get_storage(request, game_id: str) -> dict[str, object]:
    current = _now(None)
    game = _published_game(game_id)
    subject_type, user, identity = _subject(request)
    _active_session(subject_type, user, identity, game)
    row = _row(subject_type, user, identity, game)
    if row is not None and _expired(row, current):
        row.delete()
        row = None
    if row is None:
        return {"data": {}, "revision": 0}
    if subject_type == GameStorage.SUBJECT_ANON:
        expires_at = current + timedelta(days=GUEST_TTL_DAYS)
        GameStorage.objects.filter(pk=row.pk).update(expires_at=expires_at, updated_at=current)
    return {"data": row.data, "revision": row.revision}


def _parse_if_match(if_match: str) -> str:
    cleaned = if_match.strip()
    if cleaned == "*":
        return cleaned
    cleaned = cleaned.strip('"')
    if not cleaned.isdigit():
        raise SessionError("E_INVALID_REQUEST", "Invalid If-Match", 400)
    return cleaned


def put_storage(
    request,
    game_id: str,
    *,
    data: object,
    if_match: str,
    now: datetime | None = None,
) -> dict[str, object]:
    current = _now(now)
    if not if_match:
        raise SessionError("E_STORAGE_CONFLICT", "If-Match is required", 409)
    expected = _parse_if_match(if_match)
    document = validate_document(data)
    game = _published_game(game_id)
    subject_type, user, identity = _subject(request)
    session = _active_session(subject_type, user, identity, game)

    with transaction.atomic():
        _lock_storage(subject_type, session.subject_id, game.id)
        if subject_type == GameStorage.SUBJECT_USER:
            row = (
                GameStorage.objects.select_for_update()
                .filter(game=game, subject_type=subject_type, user=user)
                .first()
            )
        else:
            row = (
                GameStorage.objects.select_for_update()
                .filter(game=game, subject_type=subject_type, anon=identity)
                .first()
            )
        if row is not None and _expired(row, current):
            row.delete()
            row = None

        if row is None:
            if expected != "*":
                raise SessionError("E_STORAGE_CONFLICT", "Storage does not exist", 409)
            try:
                with transaction.atomic():
                    row = GameStorage.objects.create(
                        game=game,
                        subject_type=subject_type,
                        user=user if subject_type == GameStorage.SUBJECT_USER else None,
                        anon=identity if subject_type == GameStorage.SUBJECT_ANON else None,
                        data=document,
                        revision=1,
                        expires_at=(
                            current + timedelta(days=GUEST_TTL_DAYS)
                            if subject_type == GameStorage.SUBJECT_ANON
                            else None
                        ),
                    )
            except IntegrityError as exc:
                if _quota_violation(exc):
                    raise SessionError("E_STORAGE_QUOTA", "Storage quota exceeded", 413) from exc
                raise SessionError(
                    "E_STORAGE_CONFLICT", "Storage was created concurrently", 409
                ) from exc
            except DatabaseError as exc:
                if _quota_violation(exc):
                    raise SessionError("E_STORAGE_QUOTA", "Storage quota exceeded", 413) from exc
                raise
        else:
            if expected == "*" or int(expected) != row.revision:
                raise SessionError("E_STORAGE_CONFLICT", "Revision conflict", 409)
            row.data = document
            row.revision += 1
            if subject_type == GameStorage.SUBJECT_ANON:
                row.expires_at = current + timedelta(days=GUEST_TTL_DAYS)
            try:
                row.save(update_fields=["data", "revision", "expires_at", "updated_at"])
            except DatabaseError as exc:
                if _quota_violation(exc):
                    raise SessionError("E_STORAGE_QUOTA", "Storage quota exceeded", 413) from exc
                raise
    return {"data": row.data, "revision": row.revision}


def delete_user_storage(user) -> None:
    """§2.10.5: account deletion removes the user's game storage."""
    GameStorage.objects.filter(user=user).delete()
