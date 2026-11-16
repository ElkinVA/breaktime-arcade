from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest


def platform(request: HttpRequest) -> dict[str, object]:
    return {
        "csp_nonce": getattr(request, "csp_nonce", ""),
        "request_id": getattr(request, "request_id", ""),
        "portal_origin": settings.PORTAL_ORIGIN,
        "games_domain": settings.GAMES_DOMAIN,
    }
