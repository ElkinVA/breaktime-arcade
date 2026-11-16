"""Плюрализация по CLDR через Babel."""
from __future__ import annotations

from babel.plural import to_python


def plural_form(count: int, language_code: str) -> str:
    """Возвращает CLDR-форму: one, few, many, other."""
    try:
        func = to_python(language_code)
        return func(count)
    except Exception:
        return "other"
