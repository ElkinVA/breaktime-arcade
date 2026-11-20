from __future__ import annotations

import uuid
from typing import Any

import pytest
from django.core.cache import cache
from django.test import Client, RequestFactory, override_settings

from apps.core.ids import uuid7
from apps.i18n.middleware import (
    CACHE_KEY,
    LanguageRegistryUnavailable,
    MissingFallbackLanguageError,
    get_active_language_codes_for_routing,
)
from apps.i18n.models import Language
from apps.i18n.services.accept_language import is_fallback_language_active
from apps.i18n.views import root_redirect

ACTIVE_LANGUAGE_CODES = ["en", "de", "nl", "ru", "fr", "es"]
LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


def test_healthz(anon_client: Client) -> None:
    response = anon_client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_security_headers(anon_client: Client) -> None:
    response = anon_client.get("/healthz")
    assert "nonce-" in response["Content-Security-Policy"]
    assert response["X-Request-ID"]
    assert response["X-Frame-Options"] == "DENY"


def test_uuid7_monotonic_and_version() -> None:
    values = [uuid7() for _ in range(1000)]
    assert all(isinstance(v, uuid.UUID) and v.version == 7 for v in values)
    assert values == sorted(values)
    assert len(set(values)) == len(values)


@pytest.mark.django_db
@override_settings(BA_BACKUP_CHECK_ENABLED=False)
def test_readyz(anon_client: Client) -> None:
    response = anon_client.get("/readyz")
    assert response.status_code in {200, 503}
    assert set(response.json()["checks"]) == {"db", "cache", "broker", "i18n"}


@pytest.mark.django_db
@override_settings(BA_BACKUP_CHECK_ENABLED=False, CACHES=LOCMEM_CACHES)
@pytest.mark.parametrize("mode", ["update", "bulk_update"])
def test_required_en_is_checked_from_db_after_mass_update(anon_client: Client, mode: str) -> None:
    original_en_active = Language.objects.get(code="en").is_active
    cache.set(CACHE_KEY, ACTIVE_LANGUAGE_CODES, 60)
    try:
        if mode == "update":
            Language.objects.filter(code="en").update(is_active=False)
        else:
            language = Language.objects.get(code="en")
            language.is_active = False
            Language.objects.bulk_update([language], ["is_active"])

        response = anon_client.get("/readyz")
        assert response.status_code == 503
        assert response.json()["checks"]["i18n"] == "fail"
        assert anon_client.get("/de/").status_code == 503
        assert anon_client.get("/").status_code == 503
        assert anon_client.get("/healthz").status_code == 200
    finally:
        Language.objects.filter(code="en").update(is_active=original_en_active)
        cache.delete(CACHE_KEY)

    response = anon_client.get("/readyz")
    assert response.json()["checks"]["i18n"] == "ok"
    assert anon_client.get("/de/").status_code == 200
    assert anon_client.get("/").status_code == 302


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
@pytest.mark.parametrize("mode", ["update", "bulk_update"])
def test_root_refreshes_cache_when_reactivated_en_is_missing(
    anon_client: Client, mode: str
) -> None:
    original_en_active = Language.objects.get(code="en").is_active
    try:
        Language.objects.filter(code="en").update(is_active=False)
        inactive_codes = list(
            Language.objects.filter(is_active=True)
            .order_by("sort_order", "code")
            .values_list("code", flat=True)
        )
        cache.set(CACHE_KEY, inactive_codes, 60)
        assert "en" not in cache.get(CACHE_KEY)

        if mode == "update":
            Language.objects.filter(code="en").update(is_active=True)
        else:
            language = Language.objects.get(code="en")
            language.is_active = True
            Language.objects.bulk_update([language], ["is_active"])

        assert is_fallback_language_active() is True
        response = anon_client.get("/")
        assert response.status_code == 302
        assert response["Location"] == "/en/"
        assert anon_client.get("/de/").status_code == 200
        accept_en = anon_client.get("/", HTTP_ACCEPT_LANGUAGE="en")
        assert accept_en.status_code == 302
        assert accept_en["Location"] == "/en/"
        refreshed = cache.get(CACHE_KEY)
        assert refreshed is not None
        assert "en" in refreshed
    finally:
        Language.objects.filter(code="en").update(is_active=original_en_active)
        cache.delete(CACHE_KEY)


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
@pytest.mark.parametrize("mode", ["update", "bulk_update"])
def test_middleware_refreshes_stale_cache_on_first_language_route(
    anon_client: Client, mode: str
) -> None:
    original_en_active = Language.objects.get(code="en").is_active
    try:
        Language.objects.filter(code="en").update(is_active=False)
        inactive_codes = list(
            Language.objects.filter(is_active=True)
            .order_by("sort_order", "code")
            .values_list("code", flat=True)
        )
        cache.set(CACHE_KEY, inactive_codes, 60)
        if mode == "update":
            Language.objects.filter(code="en").update(is_active=True)
        else:
            language = Language.objects.get(code="en")
            language.is_active = True
            Language.objects.bulk_update([language], ["is_active"])

        response = anon_client.get("/de/")

        assert response.status_code == 200
        assert "en" in cache.get(CACHE_KEY)
    finally:
        Language.objects.filter(code="en").update(is_active=original_en_active)
        cache.delete(CACHE_KEY)


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_missing_fallback_after_refresh_returns_503(
    anon_client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "apps.i18n.services.language_registry.get_active_language_codes",
        lambda: ["de", "nl", "ru", "fr", "es"],
    )

    response = anon_client.get("/de/")

    assert response.status_code == 503
    assert "Accept-Language" in response["Vary"]


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_root_returns_503_when_fallback_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "apps.i18n.services.language_registry.get_active_language_codes",
        lambda: ["de", "nl", "ru", "fr", "es"],
    )

    response = root_redirect(RequestFactory().get("/"))

    assert response.status_code == 503
    assert "Accept-Language" in response["Vary"]


@pytest.mark.django_db
def test_helper_raises_for_missing_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "apps.i18n.services.language_registry.get_active_language_codes",
        lambda: ["de", "nl", "ru", "fr", "es"],
    )

    with pytest.raises(MissingFallbackLanguageError):
        get_active_language_codes_for_routing()


@pytest.mark.django_db
def test_helper_does_not_mask_unexpected_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "apps.i18n.services.language_registry.get_active_language_codes",
        lambda: (_ for _ in ()).throw(RuntimeError("unexpected cache bug")),
    )

    with pytest.raises(RuntimeError, match="unexpected cache bug"):
        get_active_language_codes_for_routing()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_registry_unavailable_on_refresh_returns_503(
    anon_client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def fake_codes() -> list[str]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return ["de"]
        raise LanguageRegistryUnavailable("cache unavailable")

    monkeypatch.setattr(
        "apps.i18n.services.language_registry.get_active_language_codes",
        fake_codes,
    )

    response = anon_client.get("/de/")

    assert response.status_code == 503
    assert "Accept-Language" in response["Vary"]


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_root_registry_unavailable_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def fake_codes() -> list[str]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return ["de"]
        raise LanguageRegistryUnavailable("cache unavailable")

    monkeypatch.setattr(
        "apps.i18n.services.language_registry.get_active_language_codes",
        fake_codes,
    )

    response = root_redirect(RequestFactory().get("/"))

    assert response.status_code == 503
    assert "Accept-Language" in response["Vary"]


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_db_error_returns_503(anon_client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "apps.i18n.services.language_registry.is_fallback_language_active",
        lambda: (_ for _ in ()).throw(LanguageRegistryUnavailable("db unavailable")),
    )

    response = anon_client.get("/de/")

    assert response.status_code == 503
    assert "Accept-Language" in response["Vary"]


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_root_db_error_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "apps.i18n.services.language_registry.is_fallback_language_active",
        lambda: (_ for _ in ()).throw(LanguageRegistryUnavailable("db unavailable")),
    )

    response = root_redirect(RequestFactory().get("/"))

    assert response.status_code == 503
    assert "Accept-Language" in response["Vary"]


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_language_save_invalidates_active_codes_cache(
    django_capture_on_commit_callbacks: Any,
) -> None:
    cache.set(CACHE_KEY, ["en"], 60)
    language = Language.objects.get(code="de")

    with django_capture_on_commit_callbacks(execute=True):
        language.save()

    assert cache.get(CACHE_KEY) is None


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_language_delete_invalidates_active_codes_cache(
    django_capture_on_commit_callbacks: Any,
) -> None:
    cache.set(CACHE_KEY, ["en", "de"], 60)

    with django_capture_on_commit_callbacks(execute=True):
        Language.objects.filter(code="de").delete()

    assert cache.get(CACHE_KEY) is None


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_cache_invalidation_waits_for_commit_and_clears_repopulation(
    django_capture_on_commit_callbacks: Any,
) -> None:
    cache.set(CACHE_KEY, ["en"], 60)
    language = Language.objects.get(code="de")

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        language.save()
        assert cache.get(CACHE_KEY) == ["en"]
        cache.set(CACHE_KEY, ["en", "de"], 60)

    assert callbacks
    for callback in callbacks:
        callback()

    assert cache.get(CACHE_KEY) is None
