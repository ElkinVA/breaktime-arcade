"""Helpers for spreadsheet-safe downloads.

CSV consumers often interpret a leading ``=``, ``+``, ``-``, ``@``, tab or
carriage return as a formula. Prefixing such cells with an apostrophe keeps
the displayed text but neutralises the formula.
"""

from __future__ import annotations

import json
from typing import Any

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def safe_text(value: object) -> str:
    """Render any scalar/JSON value as text without inventing a repr."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError, ValueError:
        return str(value)


def csv_cell(value: Any) -> str:
    """Neutralise spreadsheet formulas while preserving normal text."""
    text = safe_text(value)
    if text.startswith(FORMULA_PREFIXES):
        return "'" + text
    return text


__all__ = ["FORMULA_PREFIXES", "csv_cell", "safe_text"]
