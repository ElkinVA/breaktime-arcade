"""CRM customer account management (§2.16.2).

The screen is deliberately separate from staff administration: it lists and
inspects ordinary customer accounts (search, profile, results, email status,
blocking, deletion and personal-data export). Passwords, TOTP secrets and
recovery codes are never loaded into the response context.

Deletion reuses the account-domain services: a fresh request starts the same
7-day cancellation window as the customer cabinet, and an expired window runs
``anonymize_user`` exactly once. Repeating the operation is a safe no-op.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q, QuerySet
from django.utils import timezone

from apps.accounts.models import User, UserProfile
from apps.accounts.services import profile as profile_service
from apps.crm.models import AdminAuditLog
from apps.crm.services.audit import record_audit
from apps.gameplay.models import GameResult, GameSession, LeaderboardEntry

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})

MIN_SEARCH_LENGTH = 2
RECENT_RESULTS_LIMIT = 20


@dataclass(frozen=True, slots=True)
class UserFilters:
    query: str = ""
    email_verified: bool | None = None
    blocked: bool | None = None


@dataclass(frozen=True, slots=True)
class UserActionResult:
    ok: bool
    reason: str = ""
    is_active: bool | None = None
    audit: AdminAuditLog | None = None


def parse_bool(raw: Any) -> bool | None:
    """Parse an optional boolean query value; unknown/empty means "no filter"."""
    if isinstance(raw, bool):
        return raw
    value = str(raw).strip().lower() if raw is not None else ""
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    return None


def _first(params: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = params.get(name)
        if value not in (None, ""):
            return value
    return None


def parse_user_filters(params: Mapping[str, Any]) -> UserFilters:
    """Normalise list query parameters; search activates from 2 characters."""
    raw_query = _first(params, "q", "search")
    query = str(raw_query or "").strip()
    if len(query) < MIN_SEARCH_LENGTH:
        query = ""
    return UserFilters(
        query=query,
        email_verified=parse_bool(_first(params, "email_verified", "verified")),
        blocked=parse_bool(_first(params, "blocked", "is_blocked")),
    )


def search_users(filters: UserFilters) -> QuerySet[User]:
    """Return the filtered customer list, case-insensitively on CITEXT fields.

    Staff accounts belong to the separate "Сотрудники" screen and are excluded
    so customer blocking/deletion cannot be triggered from this list by mistake.
    """
    queryset = (
        User.objects.select_related("profile", "email_address")
        .filter(is_staff=False)
        .order_by("login")
    )
    if filters.query:
        queryset = queryset.filter(
            Q(login__icontains=filters.query)
            | Q(profile__nickname__icontains=filters.query)
            | Q(email_address__email__icontains=filters.query)
        )
    if filters.email_verified is True:
        queryset = queryset.filter(email_address__verified_at__isnull=False)
    elif filters.email_verified is False:
        queryset = queryset.filter(
            Q(email_address__isnull=True) | Q(email_address__verified_at__isnull=True)
        )
    if filters.blocked is True:
        queryset = queryset.filter(is_active=False)
    elif filters.blocked is False:
        queryset = queryset.filter(is_active=True)
    return queryset.distinct()


def recent_results(user: User) -> QuerySet[GameResult]:
    return (
        GameResult.objects.filter(user=user)
        .select_related("game")
        .order_by("-created_at", "-id")[:RECENT_RESULTS_LIMIT]
    )


def current_leaderboard_entries(user: User) -> QuerySet[LeaderboardEntry]:
    """Leaderboard rows for the games' current epoch only."""
    return (
        LeaderboardEntry.objects.filter(user=user, epoch=F("game__leaderboard_epoch"))
        .select_related("game")
        .order_by("game__technical_id", "epoch")
    )


def _revoke_open_sessions(user: User) -> int:
    """Abort open sessions and burn their launch tickets.

    Uses ``select_for_update`` so the caller's atomic block holds row locks
    until commit. A concurrent ``submit_result`` therefore either finishes
    first (leaving a ``finished`` session that is deliberately untouched) or
    observes ``aborted`` and refuses to persist a result, mirroring DB-001.
    """
    sessions = (
        GameSession.objects.select_for_update()
        .filter(
            subject_type=GameSession.SUBJECT_USER,
            subject_id=user.id,
            state__in=(GameSession.STATE_CREATED, GameSession.STATE_ACTIVE),
        )
        .order_by("pk")
    )
    revoked = 0
    for session in sessions:
        session.state = GameSession.STATE_ABORTED
        session.ticket_hash = None
        session.ticket_expires_at = None
        session.binding_nonce_hash = ""
        session.save(
            update_fields=[
                "state",
                "ticket_hash",
                "ticket_expires_at",
                "binding_nonce_hash",
                "updated_at",
            ]
        )
        revoked += 1
    return revoked


def toggle_user_active(
    *,
    actor: User,
    target_id: UUID,
    ip: str | None = None,
    reason: str = "",
) -> UserActionResult:
    """Block/unblock a customer account and append an audit row atomically."""
    with transaction.atomic():
        target = User.objects.select_for_update().filter(pk=target_id, is_staff=False).first()
        if target is None:
            return UserActionResult(ok=False, reason="not_found")
        if target.pk == actor.pk:
            return UserActionResult(ok=False, reason="self_target")
        if not UserProfile.objects.filter(user=target).exists():
            # An anonymised tombstone must never become an authenticatable
            # account again through the customer block/unblock screen.
            return UserActionResult(ok=False, reason="already_deleted")
        before = {"is_active": target.is_active}
        target.is_active = not target.is_active
        target.updated_at = timezone.now()
        target.save(update_fields=["is_active", "updated_at"])
        if not target.is_active:
            # §2.16.2: a block must also cut off the SDK sessions and unused
            # launch tickets that were issued while the account was active.
            _revoke_open_sessions(target)
        audit = record_audit(
            actor=actor,
            action=(
                AdminAuditLog.ACTION_USER_BLOCKED
                if not target.is_active
                else AdminAuditLog.ACTION_USER_UNBLOCKED
            ),
            object_type="user",
            object_id=target.pk,
            before=before,
            after={"is_active": target.is_active},
            reason=reason,
            ip=ip,
        )
    return UserActionResult(ok=True, is_active=target.is_active, audit=audit)


def deletion_window_elapsed(requested_at: datetime | None) -> bool:
    """True when the 7-day cancellation window has fully elapsed."""
    if requested_at is None:
        return False
    return timezone.now() - requested_at >= timedelta(days=settings.ACCOUNT_DELETION_WINDOW_DAYS)


def delete_customer(
    *,
    actor: User,
    target_id: UUID,
    ip: str | None = None,
    reason: str = "",
) -> UserActionResult:
    """Delete a customer honouring the 7-day window; idempotent by design.

    - no pending request -> start the same cancellation window as the cabinet;
    - pending request inside the window -> keep it cancellable, change nothing;
    - pending request past the window -> anonymise personal data once;
    - profile already gone -> success no-op (the account was deleted before).
    """
    with transaction.atomic():
        target = User.objects.select_for_update().filter(pk=target_id, is_staff=False).first()
        if target is None:
            return UserActionResult(ok=False, reason="not_found")
        if target.pk == actor.pk:
            return UserActionResult(ok=False, reason="self_target")
        profile = UserProfile.objects.select_for_update().filter(user=target).first()
        if profile is None:
            return UserActionResult(ok=True, reason="already_deleted")

        if deletion_window_elapsed(profile.deletion_requested_at):
            previous_login = target.login
            previous_active = target.is_active
            profile_service.anonymize_user(target)
            audit = record_audit(
                actor=actor,
                action=AdminAuditLog.ACTION_USER_DELETED,
                object_type="user",
                object_id=target.pk,
                before={"login": previous_login, "is_active": previous_active},
                after={"anonymized": True},
                reason=reason,
                ip=ip,
            )
            return UserActionResult(ok=True, reason="deleted", audit=audit)

        if profile.deletion_requested_at is None:
            updated = profile_service.request_deletion(target)
            requested_at = updated.deletion_requested_at
            audit = record_audit(
                actor=actor,
                action=AdminAuditLog.ACTION_USER_DELETION_REQUESTED,
                object_type="user",
                object_id=target.pk,
                before={"deletion_requested_at": None},
                after={
                    "deletion_requested_at": (
                        requested_at.isoformat() if requested_at is not None else None
                    )
                },
                reason=reason,
                ip=ip,
            )
            return UserActionResult(ok=True, reason="scheduled", audit=audit)

    return UserActionResult(ok=True, reason="window_active")


__all__ = [
    "MIN_SEARCH_LENGTH",
    "UserActionResult",
    "UserFilters",
    "current_leaderboard_entries",
    "delete_customer",
    "deletion_window_elapsed",
    "parse_bool",
    "parse_user_filters",
    "recent_results",
    "search_users",
    "toggle_user_active",
]
