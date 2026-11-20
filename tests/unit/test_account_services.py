from __future__ import annotations

import pytest
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import override_settings

from apps.accounts.services.nickname import nickname_skeleton, normalize_nickname
from apps.accounts.services.rate_limit import (
    clear_login_failures,
    login_allowed,
    record_login_failure,
    record_registration,
    registration_allowed,
)

LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


@override_settings(CACHES=LOCMEM_CACHES)
def test_login_rate_limit_is_subject_and_ip_scoped() -> None:
    cache.clear()
    assert login_allowed("alice", "203.0.113.1")
    for _ in range(5):
        record_login_failure("alice", "203.0.113.1")
    assert not login_allowed("alice", "203.0.113.1")
    assert login_allowed("bob", "203.0.113.2")
    clear_login_failures("alice", "203.0.113.1")


@override_settings(CACHES=LOCMEM_CACHES)
def test_registration_rate_limit_is_ip_scoped() -> None:
    cache.clear()
    assert registration_allowed("198.51.100.1")
    for _ in range(3):
        record_registration("198.51.100.1")
    assert not registration_allowed("198.51.100.1")
    assert registration_allowed("198.51.100.2")


def test_nickname_skeleton_collapses_confusables() -> None:
    assert nickname_skeleton("pаypal") == nickname_skeleton("paypal")
    assert nickname_skeleton("Alice") == "alice"


def test_nickname_validation_trims_edges_and_rejects_double_spaces() -> None:
    assert normalize_nickname(" Alice ") == "Alice"
    with pytest.raises(ValidationError):
        normalize_nickname("Alice  Bob")
