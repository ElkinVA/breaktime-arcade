from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import Client, RequestFactory, override_settings
from redis.exceptions import RedisError

from apps.i18n.services import language_registry
from apps.i18n.services.language_registry import (
    LanguageRegistryUnavailable,
    get_active_language_codes,
    get_active_language_codes_safely,
)
from apps.i18n.templatetags.portal_urls import language_url

LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_cache_read_failure_falls_back_to_database(monkeypatch: pytest.MonkeyPatch) -> None:
    cache.delete(language_registry.CACHE_KEY)
    monkeypatch.setattr(
        language_registry,
        "_cache_get",
        lambda: (_ for _ in ()).throw(RedisError("cache unavailable")),
    )

    codes = get_active_language_codes()

    assert "en" in codes
    assert "de" in codes


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_cache_write_failure_keeps_database_result(monkeypatch: pytest.MonkeyPatch) -> None:
    cache.delete(language_registry.CACHE_KEY)
    monkeypatch.setattr(
        language_registry,
        "_cache_set",
        lambda codes: (_ for _ in ()).throw(RedisError("cache unavailable")),
    )

    codes = get_active_language_codes()

    assert "en" in codes


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_cache_invalid_value_is_ignored() -> None:
    cache.set(language_registry.CACHE_KEY, "not-a-list", 60)

    codes = get_active_language_codes()

    assert "en" in codes
    assert isinstance(cache.get(language_registry.CACHE_KEY), list)


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_language_url_returns_empty_when_registry_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        language_registry,
        "get_active_language_codes",
        lambda: (_ for _ in ()).throw(LanguageRegistryUnavailable("db unavailable")),
    )
    request = RequestFactory().get("/de/games/")

    assert language_url({"request": request}, "fr") == ""


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_safe_codes_returns_empty_when_registry_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        language_registry,
        "get_active_language_codes",
        lambda: (_ for _ in ()).throw(LanguageRegistryUnavailable("db unavailable")),
    )

    assert get_active_language_codes_safely() == []


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_cache_read_failure_does_not_break_public_route(
    anon_client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        language_registry,
        "_cache_get",
        lambda: (_ for _ in ()).throw(RedisError("cache unavailable")),
    )

    response = anon_client.get("/de/")

    assert response.status_code == 200
