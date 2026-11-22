"""Step-up authentication for sensitive CRM actions (§2.16.1, ADR D11).

Publishing, rollback and other owner-level operations require an explicit
password + staff TOTP confirmation. A successful confirmation elevates the
session for a short, configurable window (15 minutes by default); a failed one
must not change any application state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.contrib.sessions.backends.base import SessionBase
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.services.two_factor import verify_totp

SESSION_KEY = "crm_step_up_at"
DEFAULT_TTL_SECONDS = 15 * 60


@dataclass(frozen=True, slots=True)
class StepUpResult:
    """Outcome of a credential check. ``reason`` is safe for staff display."""

    ok: bool
    reason: str = ""


def step_up_ttl_seconds() -> int:
    value = getattr(settings, "CRM_STEP_UP_TTL_SECONDS", DEFAULT_TTL_SECONDS)
    try:
        ttl = int(value)
    except TypeError, ValueError:
        return DEFAULT_TTL_SECONDS
    return ttl if ttl > 0 else DEFAULT_TTL_SECONDS


def confirm_step_up(user: User, password: str, code: str) -> StepUpResult:
    """Verify the staff password and a fresh TOTP value.

    Password is checked first so a wrong password never consumes a TOTP
    counter. No session or domain state is touched here.
    """
    if not user.is_authenticated or not getattr(user, "is_staff", False):
        return StepUpResult(ok=False, reason="not_staff")
    if not password or not user.check_password(password):
        return StepUpResult(ok=False, reason="invalid_credentials")
    if not code or not verify_totp(user, code):
        return StepUpResult(ok=False, reason="invalid_credentials")
    return StepUpResult(ok=True)


def mark_step_up(session: SessionBase, *, now: datetime | None = None) -> None:
    """Record a successful elevation in the staff session."""
    timestamp = now or timezone.now()
    if timezone.is_naive(timestamp):
        timestamp = timestamp.replace(tzinfo=UTC)
    session[SESSION_KEY] = timestamp.isoformat()
    session.modified = True


def is_step_up_valid(session: SessionBase, *, now: datetime | None = None) -> bool:
    """Return ``True`` while the session elevation is inside its TTL."""
    raw = session.get(SESSION_KEY)
    if not isinstance(raw, str) or not raw:
        return False
    try:
        stamped = datetime.fromisoformat(raw)
    except ValueError:
        return False
    if timezone.is_naive(stamped):
        stamped = stamped.replace(tzinfo=UTC)
    current = now or timezone.now()
    if timezone.is_naive(current):
        current = current.replace(tzinfo=UTC)
    elapsed = current - stamped
    return timedelta(0) <= elapsed <= timedelta(seconds=step_up_ttl_seconds())


def clear_step_up(session: SessionBase) -> None:
    """Drop an elevation, e.g. after role/2FA changes."""
    session.pop(SESSION_KEY, None)
