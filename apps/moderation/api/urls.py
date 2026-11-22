from __future__ import annotations

from django.urls import path

from apps.moderation.api.views import ComplaintCreateView

urlpatterns = [
    path("reports", ComplaintCreateView.as_view(), name="report-create"),
]
