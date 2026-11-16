"""Языковой префикс URL из активных языков БД (§2.6, §2.15)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.utils import translation

if TYPE_CHECKING:
    from collections.abc import Callable

    from apps.i18n.models import Language

    GetResponse = Callable[[HttpRequest], HttpResponse]

CACHE_KEY = "i18n:active_codes"
CACHE_TTL = 600


def get_active_language_codes() -> list[str]:
    codes = cache.get(CACHE_KEY)
    if codes is not None:
        return codes
    from apps.i18n.models import Language

    codes = list(
        Language.objects.filter(is_active=True)
        .order_by("sort_order", "code")
        .values_list("code", flat=True)
    )
    cache.set(CACHE_KEY, codes, CACHE_TTL)
    return codes


def get_active_languages() -> list[Language]:
    from apps.i18n.models import Language

    return list(Language.objects.filter(is_active=True).order_by("sort_order", "code"))


class LanguagePrefixMiddleware:
    """Определяет язык из URL-префикса /<lang>/, выставляет translation и request.language."""

    def __init__(self, get_response: GetResponse) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        path = request.path_info
        codes = get_active_language_codes()
        language_code = settings.LANGUAGE_CODE

        # Проверяем префикс /<lang>/
        if path.startswith("/"):
            parts = path[1:].split("/", 1)
            if parts and parts[0] in codes:
                language_code = parts[0]
                translation.activate(language_code)
                request.LANGUAGE_CODE = language_code  # type: ignore[attr-defined]

        response = self.get_response(request)

        translation.deactivate()
        return response


def invalidate_language_cache() -> None:
    cache.delete(CACHE_KEY)
