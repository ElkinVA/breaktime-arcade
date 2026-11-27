from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.test import override_settings
from django_redis.exceptions import ConnectionInterrupted

from apps.accounts.services import rate_limit
from apps.accounts.services.nickname import nickname_skeleton, normalize_nickname
from apps.accounts.services.rate_limit import (
    clear_login_attempts,
    login_attempt,
    password_reset_attempt,
    record_login_ip_failure,
    registration_attempt,
    registration_device,
    release_registration,
    two_factor_attempt,
)

LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "throttle": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


class _FailingCache:
    def __getattr__(self, name: str):
        def fail(*args: object, **kwargs: object) -> None:
            raise ConnectionInterrupted("throttle backend down")

        return fail


@pytest.fixture(autouse=True)
def clear_throttle_cache(settings) -> None:
    settings.CACHES = LOCMEM_CACHES
    caches["throttle"].clear()
    yield
    caches["throttle"].clear()


@override_settings(CACHES=LOCMEM_CACHES)
def test_login_attempts_are_atomic_and_subject_scoped() -> None:
    assert all(login_attempt("alice", "203.0.113.1").allowed for _ in range(5))
    assert not login_attempt("alice", "203.0.113.1").allowed
    assert login_attempt("bob", "203.0.113.2").allowed
    clear_login_attempts("alice")
    assert login_attempt("alice", "203.0.113.1").allowed


@override_settings(CACHES=LOCMEM_CACHES)
def test_concurrent_login_attempts_cannot_exceed_the_limit() -> None:
    with ThreadPoolExecutor(max_workers=10) as pool:
        decisions = list(pool.map(lambda _: login_attempt("alice", None), range(20)))
    assert sum(decision.allowed for decision in decisions) == 5


@override_settings(CACHES=LOCMEM_CACHES)
def test_login_ip_failure_limit_is_enforced() -> None:
    for _ in range(60):
        record_login_ip_failure("203.0.113.9")
    assert not login_attempt("carol", "203.0.113.9").allowed
    assert login_attempt("carol", "203.0.113.10").allowed


@override_settings(CACHES=LOCMEM_CACHES)
def test_registration_limit_is_device_and_ip_scoped() -> None:
    assert registration_attempt("device-a", "198.51.100.1").allowed
    assert registration_attempt("device-a", "198.51.100.1").allowed
    assert registration_attempt("device-a", "198.51.100.1").allowed
    assert not registration_attempt("device-a", "198.51.100.1").allowed
    assert registration_attempt("device-b", "198.51.100.1").allowed


@override_settings(CACHES=LOCMEM_CACHES)
def test_registration_ip_limit_is_thirty_per_day() -> None:
    assert registration_attempt("device-0", "198.51.100.4").allowed
    for index in range(1, 30):
        assert registration_attempt(f"device-{index}", "198.51.100.4").allowed
    assert not registration_attempt("device-31", "198.51.100.4").allowed


@override_settings(CACHES=LOCMEM_CACHES)
def test_registration_limit_aggregates_ipv6_by_64() -> None:
    for index in range(30):
        assert registration_attempt(f"device-{index}", "2001:db8:0:1::1").allowed
    assert not registration_attempt("device-31", "2001:db8:0:1::2").allowed
    assert registration_attempt("device-31", "2001:db8:0:2::1").allowed


@override_settings(CACHES=LOCMEM_CACHES)
def test_registration_ip_buckets_collapse_ipv4_mapped() -> None:
    for index in range(30):
        assert registration_attempt(f"device-{index}", "203.0.113.77").allowed
    assert not registration_attempt("device-30", "::ffff:203.0.113.77").allowed


def test_registration_device_uses_csrf_cookie_or_ip_fallback() -> None:
    assert registration_device("token", "203.0.113.1") == "cookie:token"
    assert registration_device(None, "2001:db8::1") == registration_device(None, "2001:db8::2")
    assert registration_device(None, "203.0.113.1") != registration_device(None, "203.0.113.2")


@override_settings(CACHES=LOCMEM_CACHES)
def test_two_factor_ip_failure_limit_is_enforced() -> None:
    for _ in range(30):
        rate_limit.record_two_factor_ip_failure("203.0.113.40")
    assert not two_factor_attempt("user-2", "203.0.113.40").allowed
    assert two_factor_attempt("user-2", "203.0.113.41").allowed


@override_settings(CACHES=LOCMEM_CACHES)
def test_password_reset_ip_limit_is_enforced() -> None:
    for index in range(20):
        assert password_reset_attempt(f"user{index}@example.com", "203.0.113.50").allowed
    assert not password_reset_attempt("another@example.com", "203.0.113.50").allowed


@override_settings(CACHES=LOCMEM_CACHES)
def test_registration_slot_is_released_for_invalid_form() -> None:
    assert registration_attempt("device-release", "198.51.100.3").allowed
    assert registration_attempt("device-release", "198.51.100.3").allowed
    assert registration_attempt("device-release", "198.51.100.3").allowed
    release_registration("device-release", "198.51.100.3")
    assert registration_attempt("device-release", "198.51.100.3").allowed
    assert not registration_attempt("device-release", "198.51.100.3").allowed


@override_settings(CACHES=LOCMEM_CACHES)
def test_concurrent_registration_releases_clamp_at_zero() -> None:
    device, ip = "device-race-release", "198.51.100.5"
    device_key = f"auth:register:device:{rate_limit._hash(device)}"
    ip_key = f"auth:register:ip:{rate_limit._ip_hash(ip)}"
    assert all(registration_attempt(device, ip).allowed for _ in range(3))
    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(lambda _: release_registration(device, ip), range(20)))
    assert rate_limit._read(device_key) == 0
    assert rate_limit._read(ip_key) == 0
    release_registration(device, ip)
    assert rate_limit._read(device_key) == 0
    assert rate_limit._read(ip_key) == 0


@override_settings(CACHES=LOCMEM_CACHES)
def test_password_reset_limit_is_atomic() -> None:
    assert password_reset_attempt("alice@example.com", "203.0.113.20").allowed
    assert password_reset_attempt("alice@example.com", "203.0.113.20").allowed
    assert password_reset_attempt("alice@example.com", "203.0.113.20").allowed
    assert not password_reset_attempt("alice@example.com", "203.0.113.20").allowed


@override_settings(CACHES=LOCMEM_CACHES)
def test_two_factor_limit_is_atomic() -> None:
    assert all(two_factor_attempt("user-1", "203.0.113.30").allowed for _ in range(10))
    assert not two_factor_attempt("user-1", "203.0.113.30").allowed


@override_settings(CACHES=LOCMEM_CACHES)
def test_security_limits_fail_closed_when_cache_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rate_limit, "_cache", lambda: _FailingCache())
    decisions = (
        login_attempt("alice", "203.0.113.1"),
        two_factor_attempt("user-1", "203.0.113.1"),
        password_reset_attempt("alice@example.com", "203.0.113.1"),
        registration_attempt("device", "203.0.113.1"),
    )
    assert all(decision.unavailable and not decision.allowed for decision in decisions)


def test_nickname_skeleton_collapses_confusables() -> None:
    assert nickname_skeleton("pаypal") == nickname_skeleton("paypal")
    assert nickname_skeleton("Alice") == "alice"


def test_nickname_validation_trims_edges_and_rejects_double_spaces() -> None:
    assert normalize_nickname(" Alice ") == "Alice"
    with pytest.raises(ValidationError):
        normalize_nickname("Alice  Bob")
