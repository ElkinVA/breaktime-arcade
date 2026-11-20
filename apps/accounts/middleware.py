"""Принудительная 2FA для персонала (§2.20)."""

from __future__ import annotations

from collections.abc import Callable

from django.contrib import messages
from django.contrib.auth import logout as auth_logout
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

_EXEMPT_PREFIXES = (
    "/auth/2fa/",
    "/auth/logout/",
    "/healthz",
    "/readyz",
    "/static/",
    "/media/",
)


def _without_language_prefix(path: str) -> str:
    parts = path.strip("/").split("/")
    if parts and len(parts[0]) == 2:
        return "/" + "/".join(parts[1:])
    return path


class StaffTwoFactorMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        user = request.user
        path = _without_language_prefix(request.path_info)
        if (
            user.is_authenticated
            and user.is_staff
            and not any(path.startswith(prefix) for prefix in _EXEMPT_PREFIXES)
        ):
            if user.totp_confirmed_at is None:
                return redirect("accounts:two_factor_setup")
            if not request.session.get("ba_2fa_verified"):
                auth_logout(request)
                messages.warning(request, "Требуется повторный вход с 2FA.")
                return redirect("accounts:login")
        return self.get_response(request)
