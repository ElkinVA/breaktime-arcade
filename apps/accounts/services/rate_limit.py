"""Атомарные субъектные лимиты регистрации/входа/восстановления.

Счётчики живут в выделенном Redis ``throttle`` (noeviction), а не в общем
LRU-кэше: вытеснение ключей не должно ослаблять защиту от перебора.

Для аутентификации отказ throttle-backend означает fail-closed: без счётчиков
нельзя гарантировать ограничение попыток, поэтому вход/2FA/восстановление/
регистрация отвечают нейтральной ошибкой, а не пропускают запрос.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from dataclasses import dataclass
from typing import Any

from django.core.cache import caches
from django_redis.cache import RedisCache  # type: ignore[import-untyped]
from django_redis.exceptions import ConnectionInterrupted  # type: ignore[import-untyped]
from redis.exceptions import RedisError

from apps.core.net import normalize_ip

logger = logging.getLogger(__name__)

# ValueError covers a foreign writer storing a non-integer at a counter key:
# treat it as a failed limit check (fail closed) instead of a 500.
# ConnectionInterrupted is django-redis's wrapper for transport failures and
# does not inherit RedisError.
CacheError = (RedisError, ConnectionInterrupted, OSError, ValueError)

LOGIN_ACCOUNT_LIMIT = 5
LOGIN_IP_FAILURE_LIMIT = 60
TWO_FACTOR_ACCOUNT_LIMIT = 10
TWO_FACTOR_IP_FAILURE_LIMIT = 30
PASSWORD_RESET_ACCOUNT_LIMIT = 3
PASSWORD_RESET_IP_LIMIT = 20
REGISTRATION_DEVICE_LIMIT = 3
REGISTRATION_IP_LIMIT = 30


@dataclass(frozen=True)
class LimitDecision:
    """Result of an atomic reservation; ``unavailable`` means fail-closed."""

    allowed: bool
    unavailable: bool = False


ALLOWED = LimitDecision(True)
DENIED = LimitDecision(False)
UNAVAILABLE = LimitDecision(False, True)

# Floor-safe decrement in one Redis round trip: GET and DECR cannot interleave
# with another release, and the counter never drops below zero. A missing key
# or a foreign non-integer value stays untouched (fail closed, no crash).
_RELEASE_FLOOR_SCRIPT = """
local value = redis.call('GET', KEYS[1])
if not value then
    return 0
end
local current = tonumber(value)
if not current or current <= 0 then
    return 0
end
return redis.call('DECR', KEYS[1])
"""

# LocMem (unit tests) cannot run Lua; serialise its read-then-decr in-process.
_RELEASE_LOCK = threading.Lock()


def _cache():
    return caches["throttle"]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:32]


def _ip_hash(ip: str | None) -> str:
    return _hash(normalize_ip(ip or "unknown"))


def _increment(key: str, timeout: int) -> int:
    """Atomically increment a fixed-window counter and return the new value."""
    cache = _cache()
    cache.add(key, 0, timeout)
    value = int(cache.incr(key))
    if value == 1:
        # Cover the add/incr race where the key expired between the two calls:
        # Redis INCR on a missing key creates a counter without a TTL. If the
        # repair itself fails, drop the key so a later attempt cannot inherit
        # a counter that would never expire.
        try:
            cache.touch(key, timeout)
        except CacheError:
            try:
                cache.delete(key)
            except CacheError:
                logger.error("security.rate_limit.ttl_repair_failed", exc_info=True)
            raise
    return value


def _read(key: str) -> int:
    return int(_cache().get(key) or 0)


def _delete(key: str) -> None:
    _cache().delete(key)


def _unavailable(scope: str, exc: Exception) -> LimitDecision:
    logger.error(
        "security.rate_limit.cache_failed",
        extra={"scope": scope, "error": type(exc).__name__, "fail_closed": True},
    )
    return UNAVAILABLE


def login_attempt(login: str, ip: str | None) -> LimitDecision:
    """Reserve one login attempt for the account; IP counts failures only."""
    account_key = f"auth:login:account:{_hash(login.lower())}"
    ip_key = f"auth:login:ip:{_ip_hash(ip)}"
    try:
        attempts = _increment(account_key, 900)
        ip_failures = _read(ip_key)
    except CacheError as exc:
        return _unavailable("login", exc)
    return LimitDecision(attempts <= LOGIN_ACCOUNT_LIMIT and ip_failures < LOGIN_IP_FAILURE_LIMIT)


def record_login_ip_failure(ip: str | None) -> None:
    try:
        _increment(f"auth:login:ip:{_ip_hash(ip)}", 900)
    except CacheError as exc:
        logger.error(
            "security.rate_limit.record_failed",
            extra={"scope": "login_ip", "error": type(exc).__name__},
        )


def clear_login_attempts(login: str) -> None:
    try:
        _delete(f"auth:login:account:{_hash(login.lower())}")
    except CacheError as exc:
        logger.error(
            "security.rate_limit.clear_failed",
            extra={"scope": "login", "error": type(exc).__name__},
        )


def two_factor_attempt(user_id: str, ip: str | None) -> LimitDecision:
    """Reserve one 2FA code attempt for the account; IP counts failures only."""
    account_key = f"auth:2fa:account:{_hash(user_id)}"
    ip_key = f"auth:2fa:ip:{_ip_hash(ip)}"
    try:
        attempts = _increment(account_key, 900)
        ip_failures = _read(ip_key)
    except CacheError as exc:
        return _unavailable("two_factor", exc)
    return LimitDecision(
        attempts <= TWO_FACTOR_ACCOUNT_LIMIT and ip_failures < TWO_FACTOR_IP_FAILURE_LIMIT
    )


def record_two_factor_ip_failure(ip: str | None) -> None:
    try:
        _increment(f"auth:2fa:ip:{_ip_hash(ip)}", 900)
    except CacheError as exc:
        logger.error(
            "security.rate_limit.record_failed",
            extra={"scope": "two_factor_ip", "error": type(exc).__name__},
        )


def clear_two_factor_attempts(user_id: str) -> None:
    try:
        _delete(f"auth:2fa:account:{_hash(user_id)}")
    except CacheError as exc:
        logger.error(
            "security.rate_limit.clear_failed",
            extra={"scope": "two_factor", "error": type(exc).__name__},
        )


def password_reset_attempt(email: str, ip: str | None) -> LimitDecision:
    """Reserve one reset request; every request counts, successful or not."""
    account_key = f"auth:reset:account:{_hash(email.casefold())}"
    ip_key = f"auth:reset:ip:{_ip_hash(ip)}"
    try:
        account_requests = _increment(account_key, 3600)
        ip_requests = _increment(ip_key, 3600)
    except CacheError as exc:
        return _unavailable("password_reset", exc)
    return LimitDecision(
        account_requests <= PASSWORD_RESET_ACCOUNT_LIMIT and ip_requests <= PASSWORD_RESET_IP_LIMIT
    )


def registration_device(csrf_token: str | None, ip: str | None) -> str:
    """Interim device key for registration (Приложение E).

    The CSRF cookie is the only stable per-browser identifier available on the
    public registration form; clearing it falls back to the per-IP bucket, and
    the IP cap still bounds rotation. A dedicated signed device cookie would
    need a cookie-policy/legal update and is left as an owner decision.
    """
    if csrf_token:
        return f"cookie:{csrf_token}"
    return f"nocookie:{normalize_ip(ip or 'unknown')}"


def registration_attempt(device: str, ip: str | None) -> LimitDecision:
    """Reserve one registration slot for the device and the client IP."""
    device_key = f"auth:register:device:{_hash(device)}"
    ip_key = f"auth:register:ip:{_ip_hash(ip)}"
    try:
        device_attempts = _increment(device_key, 86400)
        ip_attempts = _increment(ip_key, 86400)
    except CacheError as exc:
        return _unavailable("registration", exc)
    return LimitDecision(
        device_attempts <= REGISTRATION_DEVICE_LIMIT and ip_attempts <= REGISTRATION_IP_LIMIT
    )


def _release_counter(cache: Any, key: str) -> None:
    """Decrement ``key`` once, never below zero, without a read/decr gap.

    The production ``throttle`` alias is Redis, where the Lua script makes the
    check and decrement a single operation. Other backends (LocMem in unit
    tests) cannot execute Lua, so their read-then-decr runs under a
    process-local lock.
    """
    if isinstance(cache, RedisCache):
        client = cache.client
        get_client = getattr(client, "get_client", None)
        if get_client is not None:
            client = get_client(write=True)
        client.eval(_RELEASE_FLOOR_SCRIPT, 1, cache.make_key(key))
        return
    with _RELEASE_LOCK:
        if int(cache.get(key) or 0) > 0:
            cache.decr(key)


def release_registration(device: str, ip: str | None) -> None:
    """Return a reserved slot when the form is invalid or saving failed."""
    keys = (
        f"auth:register:device:{_hash(device)}",
        f"auth:register:ip:{_ip_hash(ip)}",
    )
    try:
        cache = _cache()
        for key in keys:
            _release_counter(cache, key)
    except CacheError as exc:
        logger.error(
            "security.rate_limit.release_failed",
            extra={"scope": "registration", "error": type(exc).__name__},
        )
