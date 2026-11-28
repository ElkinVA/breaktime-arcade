"""Rate limiting for the public game session API (§2.12, Приложение E).

Приложение E задаёт двухуровневые лимиты: первичный ключ — субъект, IP —
вторичный с повышенным порогом. Гостевые identity создаются сервером, поэтому
subject-ключ берётся только из валидной подписанной identity; мусорный или
просроченный токен попадает в IP-бакет и не создаёт новый бакет на каждый
запрос. Heartbeat лимитируется на сессию, а не на субъект.

Счётчики живут в отдельном Redis (alias ``throttle``, noeviction), чтобы
вытеснение cache-ключей не ослабляло лимиты. При недоступности backend
throttle работает fail-open: падение Redis не должно ломать публичные игры.
"""

from __future__ import annotations

import logging
import time
from uuid import UUID

from django.core.cache import caches
from redis.exceptions import RedisError
from rest_framework.throttling import (  # type: ignore[import-untyped]
    ScopedRateThrottle,
    SimpleRateThrottle,
)

from apps.accounts.services.anonymous import get_anonymous_identity
from apps.catalog.models import Game
from apps.core.net import normalize_ip
from apps.gameplay.models import GameSession

logger = logging.getLogger(__name__)

_FAILURE_LOG_INTERVAL_SECONDS = 60
_last_failure_log = 0.0


def _client_ip(request) -> str:
    """Client IP; IPv6 aggregated to /64 (Приложение E)."""
    return normalize_ip(request.META.get("REMOTE_ADDR") or "unknown")


def _cached_anonymous_identity(request):
    """Resolve the guest identity at most once for the current request.

    Heartbeat checks otherwise resolve the same signed cookie twice: once for
    the subject part of the key and once while validating the session. The
    cache is request-local and never creates an identity.
    """
    sentinel = object()
    cached = getattr(request, "_ba_anonymous_identity", sentinel)
    if cached is sentinel:
        cached = get_anonymous_identity(request)
        request._ba_anonymous_identity = cached
    return cached


def _subject_ident(request) -> str:
    if request.user and request.user.is_authenticated:
        return f"user:{request.user.pk}"
    identity = _cached_anonymous_identity(request)
    if identity is not None:
        return f"anon:{identity.id}"
    # Distinct namespace from GuestIpRateThrottle: the subject limit does not
    # apply to an unknown subject, and sharing the key would double-count hits.
    return f"nosubject:{_client_ip(request)}"


def _preflight_subject_ident(request) -> str | None:
    """Cheap subject identity for the heartbeat preflight; never touches the DB."""
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return f"user:{user.pk}"
    # Guests are capped by the shared IP preflight instead of the signed
    # cookie: an arbitrary cookie must not mint unbounded Redis buckets.
    return None


class ThrottleCacheMixin:
    """Resolve the dedicated throttle cache at request time (test overrides work)."""

    @property
    def cache(self):
        return caches["throttle"]


class ResilientThrottleMixin:
    """Handle throttle backend outages according to the operation's policy.

    Public game traffic fails open (availability), while abuse-intake scopes
    set ``fail_open = False`` so a Redis outage cannot remove their limit.
    """

    fail_open = True

    def allow_request(self, request, view) -> bool:
        global _last_failure_log
        try:
            allowed = super().allow_request(request, view)  # type: ignore[misc]
            return bool(allowed)
        except (RedisError, OSError) as exc:
            now = time.monotonic()
            if now - _last_failure_log >= _FAILURE_LOG_INTERVAL_SECONDS:
                _last_failure_log = now
                logger.error(
                    "throttle.cache_failed",
                    extra={
                        "scope": getattr(self, "scope", None),
                        "error": type(exc).__name__,
                        "fail_closed": not self.fail_open,
                    },
                )
            if self.fail_open:
                return True
            # DRF's check_throttles() calls wait() on a denied throttle; it
            # expects history to exist even when the cache lookup failed.
            self.history: list[float] = []
            self.now = time.time()
            return False


class SubjectScopedRateThrottle(ThrottleCacheMixin, ResilientThrottleMixin, ScopedRateThrottle):
    """Subject bucket (30/hour for sessions): user, live guest identity or IP."""

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": _subject_ident(request)}


class GuestIpRateThrottle(ThrottleCacheMixin, ResilientThrottleMixin, SimpleRateThrottle):
    """Secondary IP cap for anonymous session creation (600/hour, Приложение E).

    Authenticated users are exempt: their primary subject limit is enough and
    an office NAT must not throttle them. IPv6 is aggregated to /64.
    """

    scope = "sessions_ip"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            return None
        return f"throttle_sessions_ip:{_client_ip(request)}"


class IpRateThrottle(ThrottleCacheMixin, ResilientThrottleMixin, SimpleRateThrottle):
    """Secondary IP cap for operations whose primary key is the subject.

    The bucket is shared by every subject behind the same client IP (IPv6 is
    aggregated to /64 in ``_client_ip``). Used with per-scope subclasses so a
    secondary limit never consumes the primary subject bucket.
    """

    def get_cache_key(self, request, view):
        return f"throttle_{self.scope}:{_client_ip(request)}"


class ResultsIpRateThrottle(IpRateThrottle):
    """Results: 1200/hour per IP (Приложение E)."""

    scope = "results_ip"


class ReportsIpRateThrottle(IpRateThrottle):
    """Complaints: 30/day per IP (Приложение E); catches guest rotation."""

    scope = "reports_ip"
    fail_open = False


class ReportsSubjectRateThrottle(SubjectScopedRateThrottle):
    """Complaints: 5/day per subject; fail closed during a throttle outage."""

    fail_open = False


class HeartbeatPreflightMixin:
    """Record a preflight denial for the later session-scoped throttle.

    DRF evaluates every configured throttle before raising, so a denied
    preflight cannot stop ``SessionScopedRateThrottle`` from being constructed.
    The flag lets that throttle skip its GameSession lookup while the preflight
    denial still produces the 429.
    """

    def allow_request(self, request, view) -> bool:
        allowed = super().allow_request(request, view)  # type: ignore[misc]
        if not allowed:
            request._heartbeat_preflight_denied = True
        return bool(allowed)


class HeartbeatSubjectPreflightRateThrottle(
    HeartbeatPreflightMixin, ThrottleCacheMixin, ResilientThrottleMixin, SimpleRateThrottle
):
    """Cheap authenticated-subject cap checked before any session lookup.

    Guest requests have no database-free subject identifier, so they are
    covered by :class:`HeartbeatIpPreflightRateThrottle` instead. A denial is
    recorded by :class:`HeartbeatPreflightMixin`, so the later per-session
    throttle skips its ``GameSession`` lookup even though DRF evaluates every
    throttle class before raising.
    """

    scope = "heartbeat_preflight_subject"

    def get_cache_key(self, request, view):
        ident = _preflight_subject_ident(request)
        if ident is None:
            return None
        return f"throttle_heartbeat_preflight_subject:{ident}"


class HeartbeatIpPreflightRateThrottle(
    HeartbeatPreflightMixin, ThrottleCacheMixin, ResilientThrottleMixin, SimpleRateThrottle
):
    """Cheap shared IP cap for guest heartbeats, including unknown UUIDs.

    The key is fixed by the normalized client IP (IPv6 /64), so arbitrary
    session IDs or guest cookies cannot create an unbounded key space.
    Authenticated users are covered by the subject preflight and are exempt
    from the shared IP cap, matching the session-creation NAT policy.
    """

    scope = "heartbeat_preflight_ip"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            # Authenticated users have the subject preflight; a shared NAT IP
            # must not throttle an office with many legitimate players.
            return None
        return f"throttle_heartbeat_preflight_ip:{_client_ip(request)}"


class SessionScopedRateThrottle(ThrottleCacheMixin, ResilientThrottleMixin, SimpleRateThrottle):
    """Heartbeat bucket: 3/min per active session (Приложение E).

    The key derives from the active ``GameSession`` resolved for the request
    subject, never from the raw URL ``session_id``: unknown, expired or foreign
    IDs would otherwise mint an unbounded number of buckets. Those requests
    share a single per-subject ``invalid`` bucket instead.
    """

    scope = "heartbeat"

    def _active_session_id(self, request, session_id: UUID) -> UUID | None:
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            subject_type, subject_id = GameSession.SUBJECT_USER, user.id
        else:
            identity = _cached_anonymous_identity(request)
            if identity is None:
                return None
            subject_type, subject_id = GameSession.SUBJECT_ANON, identity.id
        session = GameSession.objects.filter(
            pk=session_id,
            subject_type=subject_type,
            subject_id=subject_id,
            state=GameSession.STATE_ACTIVE,
        ).first()
        return None if session is None else session.id

    def get_cache_key(self, request, view):
        session_id = view.kwargs.get("session_id")
        if session_id is None:
            return None
        if getattr(request, "_heartbeat_preflight_denied", False):
            # The preflight already produced the 429; do not resolve the UUID
            # (or load a guest identity) merely because DRF evaluates all
            # throttle classes before raising.
            return None
        resolved = self._active_session_id(request, session_id)
        suffix = "invalid" if resolved is None else resolved
        return f"throttle_heartbeat_{_subject_ident(request)}:{suffix}"


class StorageSessionRateThrottle(ThrottleCacheMixin, ResilientThrottleMixin, SimpleRateThrottle):
    """Storage bucket: 60/min per active game session (Приложение E)."""

    scope = "storage_session"

    def get_cache_key(self, request, view):
        game_id = view.kwargs.get("game_id")
        if game_id is None:
            return None
        game = Game.objects.filter(technical_id=game_id, status=Game.STATUS_PUBLISHED).first()
        if game is None:
            return None
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            session = GameSession.objects.filter(
                game=game,
                subject_type=GameSession.SUBJECT_USER,
                subject_id=user.id,
                state=GameSession.STATE_ACTIVE,
            ).first()
        else:
            identity = _cached_anonymous_identity(request)
            if identity is None:
                return None
            session = GameSession.objects.filter(
                game=game,
                subject_type=GameSession.SUBJECT_ANON,
                subject_id=identity.id,
                state=GameSession.STATE_ACTIVE,
            ).first()
        if session is None:
            return None
        return f"throttle_storage_session:{session.id}"
