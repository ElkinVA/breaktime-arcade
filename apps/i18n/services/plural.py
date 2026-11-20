"""Плюрализация по CLDR через Babel."""

from __future__ import annotations

from babel import Locale


def plural_form(count: int, language_code: str) -> str:
    """Возвращает CLDR-форму: one, few, many, other."""
    try:
        return Locale.parse(language_code).plural_form(count)
    except Exception:
        return "other"
