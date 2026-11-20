"""Простые субъектные лимиты регистрации/входа/восстановления."""

from __future__ import annotations

import contextlib
import hashlib
import logging

from django.core.cache import cache
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

CacheError = (RedisError, OSError)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:32]


def _count(key: str, timeout: int) -> int:
    try:
        value = cache.get(key)
        return int(value or 0)
    except CacheError as exc:
        logger.warning("account.rate_limit.cache_failed", exc_info=exc)
        return 0


def _hit(key: str, timeout: int) -> int:
    try:
        cache.add(key, 0, timeout)
        return int(cache.incr(key))
    except CacheError as exc:
        logger.warning("account.rate_limit.cache_failed", exc_info=exc)
        return 0


def login_allowed(login: str, ip: str | None) -> bool:
    account_key = f"auth:login:account:{_hash(login.lower())}"
    ip_key = f"auth:login:ip:{_hash(ip or 'unknown')}"
    return _count(account_key, 900) < 5 and _count(ip_key, 900) < 60


def record_login_failure(login: str, ip: str | None) -> None:
    _hit(f"auth:login:account:{_hash(login.lower())}", 900)
    _hit(f"auth:login:ip:{_hash(ip or 'unknown')}", 900)


def clear_login_failures(login: str, ip: str | None) -> None:
    # Успешный вход сбрасывает только счётчик аккаунта. IP-счётчик общий
    # для всех аккаунтов за NAT и не должен обнуляться одним валидным входом.
    del ip
    key = f"auth:login:account:{_hash(login.lower())}"
    with contextlib.suppress(RedisError, OSError):
        cache.delete(key)


def registration_allowed(ip: str | None) -> bool:
    return _count(f"auth:register:ip:{_hash(ip or 'unknown')}", 86400) < 3


def record_registration(ip: str | None) -> None:
    _hit(f"auth:register:ip:{_hash(ip or 'unknown')}", 86400)


def two_factor_allowed(user_id: str, ip: str | None) -> bool:
    return (
        _count(f"auth:2fa:account:{_hash(user_id)}", 900) < 10
        and _count(f"auth:2fa:ip:{_hash(ip or 'unknown')}", 900) < 30
    )


def record_two_factor_failure(user_id: str, ip: str | None) -> None:
    _hit(f"auth:2fa:account:{_hash(user_id)}", 900)
    _hit(f"auth:2fa:ip:{_hash(ip or 'unknown')}", 900)


def password_reset_allowed(email: str, ip: str | None) -> bool:
    return (
        _count(f"auth:reset:account:{_hash(email.lower())}", 3600) < 3
        and _count(f"auth:reset:ip:{_hash(ip or 'unknown')}", 3600) < 20
    )


def record_password_reset(email: str, ip: str | None) -> None:
    _hit(f"auth:reset:account:{_hash(email.lower())}", 3600)
    _hit(f"auth:reset:ip:{_hash(ip or 'unknown')}", 3600)
