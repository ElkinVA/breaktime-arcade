from __future__ import annotations

import pytest

from apps.i18n.services.plural import plural_form


@pytest.mark.parametrize(
    ("count", "expected"),
    [(1, "one"), (2, "few"), (5, "many"), (21, "one")],
)
def test_russian_plural_forms(count: int, expected: str) -> None:
    assert plural_form(count, "ru") == expected


@pytest.mark.parametrize(("count", "expected"), [(1, "one"), (2, "other")])
def test_english_plural_forms(count: int, expected: str) -> None:
    assert plural_form(count, "en") == expected


def test_unknown_locale_falls_back_to_other() -> None:
    assert plural_form(1, "not-a-locale") == "other"
