"""Shared catalog constants.

``FALLBACK_LANGUAGE_CODE`` is the mandatory portal language used whenever a
localized value is missing.  Slug resolution and SEO canonical URLs must agree
on it, so both import this single definition instead of repeating the literal.
"""

from __future__ import annotations

FALLBACK_LANGUAGE_CODE = "en"

__all__ = ["FALLBACK_LANGUAGE_CODE"]
