"""Access helpers for the staff-only CRM (§2.16, §2.20).

The CRM is available to staff accounts with an explicit CRM role. Two-factor
enforcement for staff is handled by
``apps.accounts.middleware.StaffTwoFactorMiddleware``; these decorators close
the role/capability check before any CRM data is loaded and send unauthorised
visitors through the regular staff login/2FA flow.

Non-staff and anonymous visitors are redirected to the staff login (the
existing behaviour). Authenticated staff accounts without a role, or without
the required capability, receive a plain 403 page instead of a redirect loop.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, cast

from django.http import HttpRequest, HttpResponseBase, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse

from apps.crm.permissions import has_capability, is_staff_user


def _forbidden(request: HttpRequest) -> TemplateResponse:
    return TemplateResponse(
        request,
        "crm/forbidden.html",
        {"title": "Недостаточно прав · CRM"},
        status=403,
    )


def _login_redirect() -> HttpResponseRedirect:
    return HttpResponseRedirect(reverse("crm:login"))


def _two_factor_verified(request: HttpRequest) -> bool:
    """Defence-in-depth mirror of ``StaffTwoFactorMiddleware`` for staff."""
    if not getattr(request.user, "is_staff", False):
        return True
    session = getattr(request, "session", None)
    return bool(session and session.get("ba_2fa_verified"))


def staff_required[ViewFunc: Callable[..., HttpResponseBase]](view: ViewFunc) -> ViewFunc:
    """Allow only authenticated staff with an assigned CRM role."""

    @wraps(view)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        if not is_staff_user(request.user):
            return _login_redirect()
        if not _two_factor_verified(request):
            return HttpResponseRedirect(reverse("accounts:login"))
        if not getattr(request.user, "crm_role", ""):
            return _forbidden(request)
        return view(request, *args, **kwargs)

    return cast(ViewFunc, wrapper)


def role_required[ViewFunc: Callable[..., HttpResponseBase]](
    capability: str,
) -> Callable[[ViewFunc], ViewFunc]:
    """Require a specific §2.16 capability in addition to staff + role."""

    def decorator(view: ViewFunc) -> ViewFunc:
        @wraps(view)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
            if not is_staff_user(request.user):
                return _login_redirect()
            if not _two_factor_verified(request):
                return HttpResponseRedirect(reverse("accounts:login"))
            if not getattr(request.user, "crm_role", ""):
                return _forbidden(request)
            if not has_capability(request.user, capability):
                return _forbidden(request)
            return view(request, *args, **kwargs)

        return cast(ViewFunc, wrapper)

    return decorator


__all__ = ["role_required", "staff_required"]
