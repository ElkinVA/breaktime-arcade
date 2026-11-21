"""Result submission and leaderboard maintenance (§2.11–§2.13, §2.22).

The result is stored only for authenticated users; guests receive
``E_GUEST_FORBIDDEN`` and nothing is written (§2.12.5). Session completion,
result insert and leaderboard upsert happen in one transaction, guarded by an
advisory lock per (game, epoch, user).
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from uuid import UUID

from django.db import connection, transaction

from apps.accounts.models import AnonymousIdentity, User
from apps.core.contracts import validate_eventlog_semantics
from apps.gameplay.models import GameResult, GameSession, LeaderboardEntry
from apps.gameplay.services.sessions import SessionError, _now
from apps.gameplay.services.verifier import verify

MAX_IDEMPOTENCY_KEY_LENGTH = 128
DURATION_TOLERANCE_MS = 5000


def _advisory_key(game_id: UUID, epoch: int, user_id: UUID) -> int:
    raw = f"result:{game_id}:{epoch}:{user_id}".encode()
    return int.from_bytes(hashlib.blake2b(raw, digest_size=8).digest(), "big", signed=True)


def _lock_leaderboard(game_id: UUID, epoch: int, user_id: UUID) -> None:
    key = _advisory_key(game_id, epoch, user_id)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])


def _is_better(
    direction: str,
    value: int,
    achieved_at: datetime,
    other_value: int,
    other_at: datetime,
) -> bool:
    if direction == "lower_is_better":
        return value < other_value or (value == other_value and achieved_at < other_at)
    return value > other_value or (value == other_value and achieved_at < other_at)


def _rank(game, epoch: int, value: int, achieved_at: datetime, user_id: UUID) -> int:
    entries = LeaderboardEntry.objects.filter(game=game, epoch=epoch, is_public=True)
    # §2.11.3 tie-break: achieved_at ASC, then user_id ASC.
    tie_break = entries.filter(value=value, achieved_at=achieved_at, user_id__lt=user_id)
    if game.score_direction == "lower_is_better":
        better = entries.filter(value__lt=value) | entries.filter(
            value=value, achieved_at__lt=achieved_at
        )
    else:
        better = entries.filter(value__gt=value) | entries.filter(
            value=value, achieved_at__lt=achieved_at
        )
    return better.count() + tie_break.count() + 1


def _subject(request, session: GameSession) -> tuple[str, User | None, AnonymousIdentity | None]:
    user = getattr(request, "user", None)
    if (
        user is not None
        and user.is_authenticated
        and session.subject_type == GameSession.SUBJECT_USER
    ):
        if session.subject_id == user.id:
            return GameResult.SUBJECT_USER, user, None
        raise SessionError("E_OWNERSHIP", "Session does not belong to this subject", 403)

    identity = None
    if session.subject_type == GameSession.SUBJECT_ANON:
        from apps.accounts.services.anonymous import get_anonymous_identity

        identity = get_anonymous_identity(request)
        if identity is None or identity.id != session.subject_id:
            raise SessionError("E_OWNERSHIP", "Session does not belong to this subject", 403)
        return GameResult.SUBJECT_ANON, None, identity

    raise SessionError("E_OWNERSHIP", "Session does not belong to this subject", 403)


def submit_result(
    request,
    session_id: UUID,
    *,
    idempotency_key: str,
    value: int,
    duration_ms: int,
    seed: str | None = None,
    event_log: object | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    current = _now(now)
    if not idempotency_key or len(idempotency_key) > MAX_IDEMPOTENCY_KEY_LENGTH:
        raise SessionError("E_INVALID_REQUEST", "Invalid request", 400)

    with transaction.atomic():
        session = (
            GameSession.objects.select_for_update()
            .select_related("game", "game_version")
            .filter(pk=session_id)
            .first()
        )
        if session is None:
            raise SessionError("E_SESSION_INVALID", "Session not found", 404)

        if session.subject_type == GameSession.SUBJECT_ANON:
            # §2.12.5: guest result is never stored; SDK normalises this answer.
            raise SessionError("E_GUEST_FORBIDDEN", "Guest results are not stored", 403)

        subject_type, user, _identity = _subject(request, session)
        if subject_type != GameResult.SUBJECT_USER or user is None:
            raise SessionError("E_GUEST_FORBIDDEN", "Guest results are not stored", 403)

        existing = GameResult.objects.filter(session=session).first()
        if existing is not None:
            if existing.idempotency_key == idempotency_key:
                return dict(existing.response)
            raise SessionError("E_SESSION_FINISHED", "Session is finished", 410)

        if session.state != GameSession.STATE_ACTIVE:
            if session.state in {GameSession.STATE_EXPIRED, GameSession.STATE_ABORTED}:
                raise SessionError("E_SESSION_EXPIRED", "Session is expired", 410)
            raise SessionError("E_SESSION_INVALID", "Session is not active", 400)

        if seed is not None and seed != session.seed:
            raise SessionError("E_MESSAGE_INVALID", "Seed does not match the session", 400)
        if event_log is not None:
            if not isinstance(event_log, dict):
                raise SessionError("E_MESSAGE_INVALID", "Invalid eventLog", 400)
            if event_log.get("seed") != session.seed:
                raise SessionError("E_MESSAGE_INVALID", "eventLog seed does not match", 400)
            verification = (session.game_version.manifest or {}).get("verification", {})
            event_kinds = (
                verification.get("eventKinds", []) if isinstance(verification, dict) else []
            )
            errors = validate_eventlog_semantics(
                event_log,
                event_kinds if isinstance(event_kinds, list) else [],
                duration_ms,
            )
            if errors:
                raise SessionError("E_MESSAGE_INVALID", "Invalid eventLog", 400)

        game = session.game
        last = session.last_heartbeat_at or session.activated_at or session.created_at
        if (
            session.activated_at is None
            or (current - session.activated_at).total_seconds() > session.max_session_seconds
            or (current - last).total_seconds() > 30 * 60
        ):
            session.state = GameSession.STATE_EXPIRED
            session.save(update_fields=["state", "updated_at"])
            raise SessionError("E_SESSION_EXPIRED", "Session is expired", 410)

        # §2.14.5: preview/autotest are excluded from records and aggregates.
        is_test = session.mode != GameSession.MODE_USER

        if not (game.score_min_value <= value <= game.score_max_value):
            raise SessionError("E_SCORE_RANGE", "Score is out of range", 400)
        if duration_ms < 0 or duration_ms > session.max_session_seconds * 1000:
            raise SessionError("E_DURATION_INVALID", "Duration is invalid", 400)
        if not is_test and duration_ms < game.min_session_seconds * 1000:
            raise SessionError("E_DURATION_INVALID", "Duration is invalid", 400)
        if session.mode == GameSession.MODE_AUTOTEST and duration_ms > 60_000:
            raise SessionError("E_DURATION_INVALID", "Duration is invalid", 400)
        if abs(duration_ms - session.credited_ms) > DURATION_TOLERANCE_MS:
            raise SessionError("E_DURATION_INVALID", "Duration is invalid", 400)

        verdict = verify(
            game=game,
            version=session.game_version,
            event_log=event_log,
            value=value,
            duration_ms=duration_ms,
            is_test=is_test,
        )
        epoch = game.leaderboard_epoch
        response: dict[str, object] = {
            "status": "quarantined" if verdict.quarantined else "saved",
            "rank": None,
            "is_personal_best": False,
            "is_record": False,
            "trust_level": verdict.level,
        }

        result = GameResult.objects.create(
            session=session,
            game=game,
            game_version=session.game_version,
            subject_type=GameResult.SUBJECT_USER,
            user=user,
            epoch=epoch,
            value=value,
            unit=game.score_unit,
            duration_ms=duration_ms,
            trust_level=verdict.level,
            is_test=is_test,
            is_quarantined=verdict.quarantined,
            verifier_flags={"verifier": "heuristic_v1", "flags": list(verdict.flags)},
            idempotency_key=idempotency_key,
            response=response,
        )
        # DB-003 compares achieved_at with the result's created_at exactly.
        achieved_at = result.created_at

        leaderboard_allowed = (
            game.leaderboard_enabled
            and not is_test
            and not verdict.quarantined
            and (
                not game.leaderboard_only_verified
                or verdict.level
                in {
                    GameResult.TRUST_HEURISTIC_VALIDATED,
                    GameResult.TRUST_REPLAY_VERIFIED,
                    GameResult.TRUST_SERVER_AUTHORITATIVE,
                }
            )
        )
        is_personal_best = False
        if leaderboard_allowed:
            _lock_leaderboard(game.id, epoch, user.id)
            previous = LeaderboardEntry.objects.filter(game=game, epoch=epoch, user=user).first()
            is_personal_best = previous is None or _is_better(
                game.score_direction,
                value,
                achieved_at,
                previous.value,
                previous.achieved_at,
            )
            if is_personal_best:
                LeaderboardEntry.objects.update_or_create(
                    game=game,
                    epoch=epoch,
                    user=user,
                    defaults={
                        "best_result": result,
                        "value": value,
                        "achieved_at": achieved_at,
                        "is_public": True,
                        "trust_level": verdict.level,
                    },
                )
            response["is_personal_best"] = is_personal_best
            response["rank"] = _rank(game, epoch, value, achieved_at, user.id)
            response["is_record"] = response["rank"] == 1
            result.response = response
            result.save(update_fields=["response"])

        session.state = GameSession.STATE_FINISHED
        session.finished_at = current
        session.save(update_fields=["state", "finished_at", "updated_at"])

        from apps.gameplay.services.popularity import credit_session

        # §2.8 counts server duration; use credited_ms, not the client value.
        credit_session(
            session,
            duration_ms=session.credited_ms,
            completed=True,
            now=current,
        )
        return response


def anonymize_user_results(user) -> None:
    """DB-001: results keep anonymised values; leaderboard rows are removed."""
    with transaction.atomic():
        LeaderboardEntry.objects.filter(user=user).delete()
        GameResult.objects.filter(user=user).update(
            subject_type=GameResult.SUBJECT_DELETED,
            user=None,
            anon=None,
        )
