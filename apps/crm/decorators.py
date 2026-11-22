"""Access helpers for the staff-only CRM (§2.16, §2.20).

The CRM is available to staff accounts only. Two-factor enforcement for staff
is handled by ``apps.accounts.middleware.StaffTwoFactorMiddleware``; this
decorator closes the role check before any CRM data is loaded and sends every
unauthorised visitor through the regular staff login/2FA flow.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, cast

from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse


def staff_required[ViewFunc: Callable[..., HttpResponse]](view: ViewFunc) -> ViewFunc:
    """Allow only authenticated staff; everyone else starts the staff login."""

    @wraps(view)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        user = request.user
        if not user.is_authenticated or not getattr(user, "is_staff", False):
            return HttpResponseRedirect(reverse("crm:login"))
        return view(request, *args, **kwargs)

    return cast(ViewFunc, wrapper)
