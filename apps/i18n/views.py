"""Публичные i18n-маршруты портала."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse, HttpResponseRedirect

from apps.i18n.services.accept_language import select_language
from apps.i18n.services.language_registry import (
    LanguageRegistryUnavailable,
    get_active_language_codes_for_routing,
)


def _response_with_vary(status: int) -> HttpResponse:
    response = HttpResponse(status=status)
    response["Vary"] = "Accept-Language"
    return response


def root_redirect(request: HttpRequest) -> HttpResponse:
    """Выбирает активный язык по Accept-Language и редиректит на /<lang>/.

    q=0 исключает язык, wildcard выбирает первый активный по sort_order,
    при отсутствии приемлемого языка возвращается 406. Если языковой реестр
    недоступен (БД/обязательный en), возвращается 503.
    """
    try:
        active_codes = [code.lower() for code in get_active_language_codes_for_routing()]
    except LanguageRegistryUnavailable:
        return _response_with_vary(503)

    chosen = select_language(request.headers.get("Accept-Language", ""), active_codes)
    if chosen is None:
        return _response_with_vary(406)

    response = HttpResponseRedirect(f"/{chosen}/")
    response["Vary"] = "Accept-Language"
    return response
