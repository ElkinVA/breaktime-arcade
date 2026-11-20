"""DRF exception handling shared by public API endpoints."""

from __future__ import annotations

from typing import Any

from rest_framework.exceptions import Throttled  # type: ignore[import-untyped]
from rest_framework.views import exception_handler as drf_exception_handler  # type: ignore[import-untyped]


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Any:
    """Keep DRF behaviour, but report throttling with the platform error shape.

    §2.23 requires structured, localisable errors; DRF would otherwise return
    ``{"detail": ...}`` for 429. ``Retry-After`` is preserved.
    """
    response = drf_exception_handler(exc, context)
    if response is not None and isinstance(exc, Throttled):
        response.data = {"code": "E_RATE_LIMIT", "message": "Too many requests"}
    return response
