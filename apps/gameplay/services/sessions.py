"""Server-side game session, launch ticket and heartbeat (§2.12.1–2.12.4).

The SDK/iframe and result/leaderboard/storage pipeline are deliberately out of
scope. Subject is stored as (subject_type, subject_id) without a FK until
DB-001 is resolved; mode is assigned by the server.

Time boundaries are inclusive: a ticket is accepted at exactly
``ticket_expires_at`` and rejected after it; the 5-minute activation window
and the idle/max-duration limits likewise expire only strictly after their
deadline.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from uuid import UUID

from django.db import IntegrityError, connection, transaction
from django.db.models import F
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.utils.translation import get_language

from apps.accounts.models import AnonymousIdentity, User, UserProfile
from apps.accounts.services.anonymous import (
    get_anonymous_identity,
    get_or_create_anonymous_identity,
)
from apps.catalog.models import Game
from apps.gameplay.models import GameSession, UserGamePlaytime

TICKET_TTL_SECONDS = 60
ACTIVATION_WINDOW_SECONDS = 300
IDLE_TIMEOUT_SECONDS = 30 * 60
MAX_ACTIVE_SESSIONS = 3
MAX_SESSION_SECONDS = 7200
MAX_HEARTBEAT_DELTA_MS = 45_000


class SessionError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _now(value: datetime | None) -> datetime:
    current = value or timezone.now()
    if timezone.is_naive(current):
        return timezone.make_aware(current)
    return current


def _advisory_key(subject_type: str, subject_id: UUID, game_id: UUID) -> int:
    raw = f"{subject_type}:{subject_id}:{game_id}".encode()
    return int.from_bytes(hashlib.blake2b(raw, digest_size=8).digest(), "big", signed=True)


def _lock_subject_game(subject_type: str, subject_id: UUID, game_id: UUID) -> None:
    key = _advisory_key(subject_type, subject_id, game_id)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])


def _lock_account(subject_type: str, subject_id: UUID) -> User | None:
    """Lock the account row before any ``GameSession`` row (R-051).

    ``anonymize_user`` and block take the ``User`` row lock first and then
    lock the subject's sessions. Write paths that lock a session first and
    afterwards insert a row with a ``User`` FK (which needs ``FOR KEY SHARE``
    on the account) would form a lock cycle. Taking the account lock first
    gives every user-session path the same User -> GameSession order.
    """
    if subject_type != GameSession.SUBJECT_USER:
        return None
    return User.objects.select_for_update().filter(pk=subject_id).only("pk", "is_active").first()


def _subject(
    request: HttpRequest,
    response: HttpResponse | None,
    *,
    create_guest: bool,
) -> tuple[str, UUID, str, str | None]:
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        nickname = UserProfile.objects.filter(user=user).values_list("nickname", flat=True).first()
        return GameSession.SUBJECT_USER, user.id, GameSession.MODE_USER, nickname

    identity: AnonymousIdentity | None
    if create_guest:
        identity = get_or_create_anonymous_identity(request, response)
    else:
        identity = get_anonymous_identity(request)
    if identity is None:
        raise SessionError("E_OWNERSHIP", "Session does not belong to this subject", 403)
    return GameSession.SUBJECT_ANON, identity.id, GameSession.MODE_GUEST, None


def create_session(
    request: HttpRequest,
    response: HttpResponse,
    *,
    game_id: str,
    now: datetime | None = None,
) -> tuple[GameSession, str, datetime]:
    current = _now(now)

    game = (
        Game.objects.select_related("current_version")
        .filter(technical_id=game_id, status=Game.STATUS_PUBLISHED)
        .first()
    )
    if game is None or game.current_version is None:
        raise SessionError("E_SESSION_INVALID", "Game is not available", 404)

    subject_type, subject_id, mode, _nickname = _subject(request, response, create_guest=True)
    max_seconds = max(0, min(int(game.max_session_seconds or 1800), MAX_SESSION_SECONDS))
    ticket = secrets.token_urlsafe(32)
    ticket_hash = _hash(ticket)
    seed = secrets.token_hex(16)
    ticket_expires_at = current + timedelta(seconds=TICKET_TTL_SECONDS)

    with transaction.atomic():
        # R-049 / ARCADE-SESSION-RACE-001: block and anonymise take a
        # ``select_for_update`` lock on the account row before revoking open
        # sessions. Lock the same row here and re-read ``is_active`` while
        # holding it, so a session can never be created for an account that
        # was blocked or anonymised while this transaction waited. If this
        # transaction wins instead, the block/anonymise revoke scan sees the
        # freshly created row and aborts it.
        if subject_type == GameSession.SUBJECT_USER:
            account = (
                User.objects.select_for_update().filter(pk=subject_id).only("is_active").first()
            )
            if account is None or not account.is_active:
                raise SessionError("E_SESSION_INVALID", "Account is not available", 403)
        _lock_subject_game(subject_type, subject_id, game.id)
        # Unactivated tickets never reach ``expired`` on their own; forget them
        # lazily so a subject cannot accumulate rows without ever activating.
        GameSession.objects.filter(
            subject_type=subject_type,
            subject_id=subject_id,
            game=game,
            state=GameSession.STATE_CREATED,
            created_at__lt=current - timedelta(seconds=ACTIVATION_WINDOW_SECONDS),
        ).update(state=GameSession.STATE_EXPIRED, updated_at=current)
        active = GameSession.objects.filter(
            subject_type=subject_type,
            subject_id=subject_id,
            game=game,
            state=GameSession.STATE_ACTIVE,
        ).count()
        if active >= MAX_ACTIVE_SESSIONS:
            raise SessionError("E_RATE_LIMIT", "Too many active sessions", 429)
        session = GameSession.objects.create(
            game=game,
            game_version=game.current_version,
            subject_type=subject_type,
            subject_id=subject_id,
            mode=mode,
            state=GameSession.STATE_CREATED,
            ticket_hash=ticket_hash,
            ticket_expires_at=ticket_expires_at,
            seed=seed,
            max_session_seconds=max_seconds,
        )
    return session, ticket, ticket_expires_at


def _load_owned_session(
    request: HttpRequest,
    session_id: UUID,
    *,
    lock: bool,
    lock_account: bool = False,
) -> tuple[GameSession, str | None]:
    subject_type, subject_id, _mode, nickname = _subject(request, None, create_guest=False)
    if lock and lock_account:
        # R-051: account before session, matching create_session/anonymize_user.
        _lock_account(subject_type, subject_id)
    queryset = GameSession.objects.select_related("game", "game_version")
    if lock:
        queryset = queryset.select_for_update()
    session = queryset.filter(pk=session_id).first()
    if session is None:
        raise SessionError("E_SESSION_INVALID", "Session not found", 404)
    if session.subject_type != subject_type or session.subject_id != subject_id:
        raise SessionError("E_OWNERSHIP", "Session does not belong to this subject", 403)
    return session, nickname


def activate_session(
    request: HttpRequest,
    session_id: UUID,
    *,
    ticket: str,
    binding_nonce: str,
    now: datetime | None = None,
) -> dict[str, object]:
    current = _now(now)
    expired = False
    with transaction.atomic():
        session, nickname = _load_owned_session(request, session_id, lock=True)
        if session.state == GameSession.STATE_FINISHED:
            raise SessionError("E_SESSION_FINISHED", "Session is finished", 410)
        if session.state in {GameSession.STATE_EXPIRED, GameSession.STATE_ABORTED}:
            raise SessionError("E_SESSION_EXPIRED", "Session is expired", 410)
        if session.state != GameSession.STATE_CREATED:
            raise SessionError("E_TICKET_INVALID", "Ticket is invalid", 400)

        if current > session.created_at + timedelta(seconds=ACTIVATION_WINDOW_SECONDS):
            session.state = GameSession.STATE_EXPIRED
            session.save(update_fields=["state", "updated_at"])
            expired = True
        elif (
            not session.ticket_hash
            or not session.ticket_expires_at
            or not hmac.compare_digest(_hash(ticket), session.ticket_hash)
        ):
            raise SessionError("E_TICKET_INVALID", "Ticket is invalid", 400)
        elif current > session.ticket_expires_at:
            session.state = GameSession.STATE_EXPIRED
            session.save(update_fields=["state", "updated_at"])
            expired = True
        else:
            nonce_hash = _hash(binding_nonce)
            if session.binding_nonce_hash and not hmac.compare_digest(
                nonce_hash, session.binding_nonce_hash
            ):
                raise SessionError("E_TICKET_INVALID", "Ticket is invalid", 400)

            # §2.12.1: ≤3 active sessions per (subject, game), under the same
            # advisory lock as creation. Creation-time counting alone is not
            # enough: tickets issued at 2 active could otherwise activate to 4.
            _lock_subject_game(session.subject_type, session.subject_id, session.game_id)
            active = GameSession.objects.filter(
                subject_type=session.subject_type,
                subject_id=session.subject_id,
                game_id=session.game_id,
                state=GameSession.STATE_ACTIVE,
            ).count()
            if active >= MAX_ACTIVE_SESSIONS:
                raise SessionError("E_RATE_LIMIT", "Too many active sessions", 429)

            session.state = GameSession.STATE_ACTIVE
            session.activated_at = current
            session.last_heartbeat_at = current
            session.binding_nonce_hash = nonce_hash
            session.ticket_hash = None
            session.ticket_expires_at = None
            session.save(
                update_fields=[
                    "state",
                    "activated_at",
                    "last_heartbeat_at",
                    "binding_nonce_hash",
                    "ticket_hash",
                    "ticket_expires_at",
                    "updated_at",
                ]
            )
            return _build_context(session, request, nickname)

    if expired:
        raise SessionError("E_SESSION_EXPIRED", "Session is expired", 410)
    raise SessionError("E_TICKET_INVALID", "Ticket is invalid", 400)


def heartbeat(
    request: HttpRequest,
    session_id: UUID,
    *,
    now: datetime | None = None,
) -> None:
    current = _now(now)
    expired = False
    with transaction.atomic():
        # R-051: heartbeat may insert ``UserGamePlaytime`` (User FK); lock the
        # account before the session so it cannot deadlock with anonymisation.
        session, _nickname = _load_owned_session(request, session_id, lock=True, lock_account=True)
        if session.state == GameSession.STATE_FINISHED:
            raise SessionError("E_SESSION_FINISHED", "Session is finished", 410)
        if session.state in {GameSession.STATE_EXPIRED, GameSession.STATE_ABORTED}:
            raise SessionError("E_SESSION_EXPIRED", "Session is expired", 410)
        if session.state != GameSession.STATE_ACTIVE:
            raise SessionError("E_SESSION_INVALID", "Session is not active", 400)

        last = session.last_heartbeat_at or session.activated_at or session.created_at
        max_duration = (
            session.activated_at is not None
            and (current - session.activated_at).total_seconds() > session.max_session_seconds
        )
        idle = (current - last).total_seconds() > IDLE_TIMEOUT_SECONDS
        if max_duration or idle:
            from apps.gameplay.services.popularity import credit_session

            session.state = GameSession.STATE_EXPIRED
            session.save(update_fields=["state", "updated_at"])
            credit_session(
                session,
                duration_ms=session.credited_ms,
                completed=False,
                now=current,
            )
            expired = True
        else:
            delta_ms = int(
                max(0, min((current - last).total_seconds() * 1000, MAX_HEARTBEAT_DELTA_MS))
            )
            previous_credited = session.credited_ms
            session.credited_ms = min(
                session.credited_ms + delta_ms,
                session.max_session_seconds * 1000,
            )
            applied_ms = session.credited_ms - previous_credited
            session.last_heartbeat_at = current
            session.save(update_fields=["credited_ms", "last_heartbeat_at", "updated_at"])
            if (
                applied_ms > 0
                and session.subject_type == GameSession.SUBJECT_USER
                and session.mode == GameSession.MODE_USER
            ):
                _credit_playtime(session.subject_id, session.game_id, applied_ms)

    if expired:
        raise SessionError("E_SESSION_EXPIRED", "Session is expired", 410)


def close_session(
    request: HttpRequest,
    session_id: UUID,
    *,
    now: datetime | None = None,
) -> None:
    """§2.23: finish a session without a result (idempotent 204)."""
    current = _now(now)
    with transaction.atomic():
        session, _nickname = _load_owned_session(request, session_id, lock=True)
        if session.state in {
            GameSession.STATE_FINISHED,
            GameSession.STATE_EXPIRED,
            GameSession.STATE_ABORTED,
        }:
            return
        if session.state == GameSession.STATE_ACTIVE:
            from apps.gameplay.services.popularity import credit_session

            credit_session(
                session,
                duration_ms=session.credited_ms,
                completed=False,
                now=current,
            )
        session.state = GameSession.STATE_ABORTED
        session.save(update_fields=["state", "updated_at"])


def _credit_playtime(user_id: UUID, game_id: UUID, delta_ms: int) -> None:
    """§2.12.3: credited time only for mode=user, never for service modes."""
    seconds = delta_ms // 1000
    if seconds <= 0:
        return
    updated = UserGamePlaytime.objects.filter(user_id=user_id, game_id=game_id).update(
        verified_seconds=F("verified_seconds") + seconds,
        updated_at=timezone.now(),
    )
    if updated:
        return
    try:
        with transaction.atomic():
            UserGamePlaytime.objects.create(
                user_id=user_id,
                game_id=game_id,
                verified_seconds=seconds,
            )
    except IntegrityError:
        UserGamePlaytime.objects.filter(user_id=user_id, game_id=game_id).update(
            verified_seconds=F("verified_seconds") + seconds,
            updated_at=timezone.now(),
        )


def _build_context(
    session: GameSession,
    request: HttpRequest,
    nickname: str | None,
) -> dict[str, object]:
    game = session.game
    version = session.game_version
    language = get_language() or game.default_language
    return {
        "sessionId": str(session.id),
        "gameId": game.technical_id,
        "gameVersion": version.semver,
        "mode": session.mode,
        "nickname": nickname,
        "language": language,
        "fallbackLanguage": game.default_language,
        "strings": {},
        "score": {
            "type": game.score_type,
            "unit": game.score_unit,
            "direction": game.score_direction,
            "minValue": game.score_min_value,
            "maxValue": game.score_max_value,
            "maxDeltaMs": MAX_HEARTBEAT_DELTA_MS,
        },
        "limits": {
            "minPlaytimeSeconds": game.min_session_seconds,
            "maxSessionSeconds": session.max_session_seconds,
            "pauseOnBlur": game.pause_on_blur,
            "heartbeatIntervalSeconds": 30,
            "idleTimeoutSeconds": IDLE_TIMEOUT_SECONDS,
        },
        "trustLevel": "client_reported",
        "seed": session.seed,
    }
