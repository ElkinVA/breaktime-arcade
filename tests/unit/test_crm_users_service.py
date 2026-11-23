"""Unit checks for CRM customer filter and deletion-window helpers."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.crm.services.users import (
    MIN_SEARCH_LENGTH,
    UserFilters,
    deletion_window_elapsed,
    parse_bool,
    parse_user_filters,
)


def test_parse_bool_accepts_common_forms_and_ignores_unknown() -> None:
    for value in ("1", "true", "TRUE", "yes", "on", True):
        assert parse_bool(value) is True
    for value in ("0", "false", "FALSE", "no", "off", False):
        assert parse_bool(value) is False
    for value in ("", None, "maybe", "2"):
        assert parse_bool(value) is None


def test_search_needs_at_least_two_characters() -> None:
    assert MIN_SEARCH_LENGTH == 2
    assert parse_user_filters({"q": " a "}) == UserFilters()
    assert parse_user_filters({"q": "ab"}) == UserFilters(query="ab")
    assert parse_user_filters({"search": "Alice"}) == UserFilters(query="Alice")


def test_filter_aliases_and_invalid_values_are_normalised() -> None:
    filters = parse_user_filters(
        {"verified": "true", "is_blocked": "0"},
    )
    assert filters == UserFilters(email_verified=True, blocked=False)

    assert parse_user_filters({"email_verified": "nonsense"}) == UserFilters()
    assert parse_user_filters({"blocked": ""}) == UserFilters()


def test_deletion_window_elapsed() -> None:
    assert deletion_window_elapsed(None) is False
    assert deletion_window_elapsed(timezone.now() - timedelta(days=1)) is False
    assert deletion_window_elapsed(timezone.now() - timedelta(days=7, minutes=1)) is True
