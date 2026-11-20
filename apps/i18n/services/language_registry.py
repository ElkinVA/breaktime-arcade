"""Кэш активных языков с явными ошибками инфраструктуры.

Кэш — оптимизация, а не источник истины. Падение Redis не должно делать
публичные страницы недоступными, если PostgreSQL отвечает. Неожиданные
исключения не перехватываются: они должны оставаться диагностируемыми.
"""

from __future__ import annotations

import logging

from django.core.cache import cache
from django.db import DatabaseError
from redis.exceptions import RedisError

from apps.i18n.services.accept_language import FALLBACK_LANGUAGE_CODE

logger = logging.getLogger(__name__)

CACHE_KEY = "i18n:active_codes"
CACHE_TTL = 600

CacheInfrastructureError = (RedisError, OSError)


class LanguageRegistryUnavailable(RuntimeError):
    """Языковой реестр недоступен из-за БД или кэша."""


class MissingFallbackLanguageError(LanguageRegistryUnavailable):
    """Обязательный en отсутствует в активных языках."""


def _cache_get() -> object:
    return cache.get(CACHE_KEY)


def _cache_set(codes: list[str]) -> None:
    cache.set(CACHE_KEY, codes, CACHE_TTL)


def _cache_delete() -> None:
    cache.delete(CACHE_KEY)


def _read_cache() -> list[str] | None:
    try:
        value = _cache_get()
    except CacheInfrastructureError as exc:
        logger.warning("i18n.cache.read_failed", exc_info=exc)
        return None

    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(code, str) for code in value):
        logger.warning("i18n.cache.invalid_value")
        invalidate_language_cache()
        return None
    return value


def _write_cache(codes: list[str]) -> None:
    try:
        _cache_set(codes)
    except CacheInfrastructureError as exc:
        # База уже ответила; потеря кэша не должна ломать запрос.
        logger.warning("i18n.cache.write_failed", exc_info=exc)


def _delete_cache() -> None:
    try:
        _cache_delete()
    except CacheInfrastructureError as exc:
        logger.warning("i18n.cache.delete_failed", exc_info=exc)


def _load_from_db() -> list[str]:
    from apps.i18n.models import Language

    try:
        return list(
            Language.objects.filter(is_active=True)
            .order_by("sort_order", "code")
            .values_list("code", flat=True)
        )
    except DatabaseError as exc:
        raise LanguageRegistryUnavailable("active language query failed") from exc


def get_active_language_codes() -> list[str]:
    """Возвращает активные коды; при отказе кэша читает PostgreSQL."""
    cached = _read_cache()
    if cached is not None:
        return cached

    codes = _load_from_db()
    _write_cache(codes)
    return codes


def get_active_language_codes_safely() -> list[str]:
    """Безопасный вариант для шаблонов: при отказе возвращает пустой список."""
    try:
        return get_active_language_codes()
    except LanguageRegistryUnavailable as exc:
        logger.warning("i18n.registry.unavailable", exc_info=exc)
        return []


def is_fallback_language_active() -> bool:
    """Проверяет обязательный en напрямую в БД, не через общий кэш."""
    from apps.i18n.models import Language

    try:
        return Language.objects.filter(
            code=FALLBACK_LANGUAGE_CODE,
            is_active=True,
        ).exists()
    except DatabaseError as exc:
        raise LanguageRegistryUnavailable("fallback language query failed") from exc


def get_active_language_codes_for_routing() -> list[str]:
    """Возвращает активные коды, гарантируя свежий en при активной БД."""
    if not is_fallback_language_active():
        raise MissingFallbackLanguageError

    codes = get_active_language_codes()
    if FALLBACK_LANGUAGE_CODE not in codes:
        # Кэш мог быть заполнен, пока en был неактивен. Перечитываем его
        # после свежей проверки обязательного языка.
        invalidate_language_cache()
        codes = get_active_language_codes()
    if FALLBACK_LANGUAGE_CODE not in codes:
        raise MissingFallbackLanguageError
    return codes


def invalidate_language_cache() -> None:
    """Инвалидирует кэш, не превращая отказ Redis в ошибку запроса."""
    _delete_cache()
