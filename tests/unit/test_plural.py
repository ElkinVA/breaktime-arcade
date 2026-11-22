"""CLDR plural forms for the active portal languages (§2.15)."""

from __future__ import annotations

import pytest

from apps.i18n.services.plural import plural_form

ACTIVE_LANGUAGES = ("en", "de", "nl", "ru", "fr", "es")
KNOWN_FORMS = {"zero", "one", "two", "few", "many", "other"}


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, "many"), (1, "one"), (2, "few"), (5, "many"), (21, "one")],
)
def test_russian_plural_forms(count: int, expected: str) -> None:
    assert plural_form(count, "ru") == expected


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, "other"), (1, "one"), (2, "other"), (5, "other")],
)
def test_english_plural_forms(count: int, expected: str) -> None:
    assert plural_form(count, "en") == expected


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, "other"), (1, "one"), (2, "other"), (5, "other")],
)
def test_german_plural_forms(count: int, expected: str) -> None:
    assert plural_form(count, "de") == expected


@pytest.mark.parametrize("language_code", ACTIVE_LANGUAGES)
@pytest.mark.parametrize("count", [0, 1, 2, 5])
def test_every_active_language_returns_a_cldr_form(language_code: str, count: int) -> None:
    assert plural_form(count, language_code) in KNOWN_FORMS


def test_unknown_locale_falls_back_to_other() -> None:
    assert plural_form(1, "not-a-locale") == "other"


@pytest.mark.parametrize("language_code", ["", "zz", "not-a-locale"])
def test_invalid_locale_falls_back_for_every_count(language_code: str) -> None:
    assert plural_form(0, language_code) == "other"
    assert plural_form(1, language_code) == "other"
    assert plural_form(2, language_code) == "other"
    assert plural_form(5, language_code) == "other"
