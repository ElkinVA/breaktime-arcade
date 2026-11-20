from __future__ import annotations

import pytest

from apps.i18n.services.accept_language import parse_accept_language, select_language

ACTIVE = ("en", "de", "nl", "ru", "fr", "es")


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("de", "de"),
        ("de-AT", "de"),
        ("de;q=0.5, fr;q=0.5", "de"),
        ("fr;q=0.5, de;q=0.5", "fr"),
        ("de;q=0.1, *;q=0.9", "en"),
        ("fr;q=0.1, *;q=0.9", "en"),
        ("de;q=0.9, *;q=0.5", "de"),
        ("en;q=0, *;q=0.5", "de"),
        ("de;q=0, *;q=0.5", "en"),
        ("*;q=0, de;q=0.9", "de"),
        ("en-US;q=0.9", "en"),
        ("it;q=1.0", "en"),
        ("de;q=0", "en"),
        (";;;", "en"),
        ("de;q=9, ;;, fr;q=0.8", "fr"),
        ("de;q=0.9, fr;q=abc", "de"),
        ("", "en"),
    ],
)
def test_select_language(header: str, expected: str) -> None:
    assert select_language(header, ACTIVE) == expected


@pytest.mark.parametrize(
    "header",
    [
        "*;q=0",
        "en;q=0",
        "en-US;q=0",
        "en;q=0, de;q=0, nl;q=0, ru;q=0, fr;q=0, es;q=0",
    ],
)
def test_select_language_returns_none_when_no_acceptable_language(header: str) -> None:
    assert select_language(header, ACTIVE) is None


def test_partial_header_keeps_valid_entries() -> None:
    entries = parse_accept_language("de;q=0.9, ;;, fr;q=0.8")

    assert [language for language, _ in entries] == ["de", "fr"]


def test_wildcard_uses_active_sort_order() -> None:
    assert select_language("en;q=0, *;q=0.5", ("fr", "de", "en")) == "fr"


def test_q_zero_regional_variant_excludes_base_language() -> None:
    assert select_language("en-US;q=0, *;q=0.5", ACTIVE) == "de"
