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

import ipaddress
import logging
import time

from django.core.cache import caches
from redis.exceptions import RedisError
from rest_framework.throttling import (  # type: ignore[import-untyped]
    ScopedRateThrottle,
    SimpleRateThrottle,
)

from apps.accounts.services.anonymous import get_anonymous_identity
from apps.catalog.models import Game
from apps.gameplay.models import GameSession

logger = logging.getLogger(__name__)

_FAILURE_LOG_INTERVAL_SECONDS = 60
_last_failure_log = 0.0


def _client_ip(request) -> str:
    """Client IP; IPv6 aggregated to /64 (Приложение E)."""
    raw = request.META.get("REMOTE_ADDR") or "unknown"
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        return raw
    if isinstance(address, ipaddress.IPv6Address):
        # IPv4-mapped addresses must share the IPv4 bucket, not the whole ::/64.
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(ipaddress.ip_network(f"{address}/64", strict=False).network_address)
    return str(address)


def _subject_ident(request) -> str:
    if request.user and request.user.is_authenticated:
        return f"user:{request.user.pk}"
    identity = get_anonymous_identity(request)
    if identity is not None:
        return f"anon:{identity.id}"
    # Distinct namespace from GuestIpRateThrottle: the subject limit does not
    # apply to an unknown subject, and sharing the key would double-count hits.
    return f"nosubject:{_client_ip(request)}"


class ThrottleCacheMixin:
    """Resolve the dedicated throttle cache at request time (test overrides work)."""

    @property
    def cache(self):
        return caches["throttle"]


class ResilientThrottleMixin:
    """Fail-open on throttle backend outage; availability over strictness."""

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
                    extra={"scope": getattr(self, "scope", None), "error": type(exc).__name__},
                )
            return True


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


class SessionScopedRateThrottle(ThrottleCacheMixin, ResilientThrottleMixin, SimpleRateThrottle):
    """Heartbeat bucket: 3/min per session (Приложение E), not per subject."""

    scope = "heartbeat"

    def get_cache_key(self, request, view):
        session_id = view.kwargs.get("session_id")
        if session_id is None:
            return None
        return f"throttle_heartbeat_{_subject_ident(request)}:{session_id}"


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
            identity = get_anonymous_identity(request)
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
