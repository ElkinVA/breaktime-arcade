"""Представления CRM."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse

from apps.crm.services.dashboard import dashboard_stats


def login_view(request: HttpRequest) -> TemplateResponse:
    return TemplateResponse(request, "crm/login.html")


def logout_view(request: HttpRequest) -> HttpResponseRedirect:
    return HttpResponseRedirect(reverse("crm:login"))


def dashboard(request: HttpRequest) -> TemplateResponse | HttpResponseRedirect:
    if not request.user.is_authenticated or not request.user.is_staff:
        return HttpResponseRedirect(reverse("crm:login"))
    return TemplateResponse(
        request,
        "crm/dashboard.html",
        {
            "title": "CRM",
            "stats": dashboard_stats(),
        },
    )
