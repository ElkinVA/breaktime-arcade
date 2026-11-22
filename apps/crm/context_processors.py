"""Expose the current staff role/capabilities to CRM templates (§2.16)."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from apps.crm.permissions import active_role, capabilities_for


def crm(request: HttpRequest) -> dict[str, Any]:
    user = getattr(request, "user", None)
    return {
        "crm_caps": capabilities_for(user),
        "crm_role": active_role(user),
    }


__all__ = ["crm"]
