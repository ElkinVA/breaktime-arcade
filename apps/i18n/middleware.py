"""Языковой префикс URL из активных языков БД (§2.6, §2.15)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.utils import translation

from apps.i18n.services.language_registry import (
    CACHE_KEY,
    CACHE_TTL,
    LanguageRegistryUnavailable,
    MissingFallbackLanguageError,
    get_active_language_codes,
    get_active_language_codes_for_routing,
    invalidate_language_cache,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from apps.i18n.models import Language

    GetResponse = Callable[[HttpRequest], HttpResponse]

__all__ = [
    "CACHE_KEY",
    "CACHE_TTL",
    "LanguageRegistryUnavailable",
    "MissingFallbackLanguageError",
    "LanguagePrefixMiddleware",
    "get_active_language_codes",
    "get_active_language_codes_for_routing",
    "get_active_languages",
    "invalidate_language_cache",
]


def get_active_languages() -> list[Language]:
    from apps.i18n.models import Language

    return list(Language.objects.filter(is_active=True).order_by("sort_order", "code"))


class LanguagePrefixMiddleware:
    """Определяет язык из URL-префикса /<lang>/, выставляет translation и request.language."""

    def __init__(self, get_response: GetResponse) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        path = request.path_info

        # Health-пробы не должны зависеть от БД языковой конфигурации.
        if path in {"/healthz", "/readyz"}:
            return self.get_response(request)

        # Единая проверка: en должен быть активен в БД, а список кодов
        # доступен. Неожиданные исключения не маскируются под 503.
        try:
            codes = get_active_language_codes_for_routing()
        except LanguageRegistryUnavailable:
            response = HttpResponse(status=503)
            response["Vary"] = "Accept-Language"
            return response

        language_code = settings.LANGUAGE_CODE

        # Проверяем префикс /<lang>/
        if path.startswith("/"):
            parts = path[1:].split("/", 1)
            if parts and parts[0] in codes:
                language_code = parts[0]
                translation.activate(language_code)
                request.LANGUAGE_CODE = language_code

        # Не деактивировать здесь: LocaleMiddleware расположен снаружи и
        # читает активный язык в process_response для Content-Language.
        # Каждый следующий запрос LocaleMiddleware активирует язык заново.
        return self.get_response(request)
