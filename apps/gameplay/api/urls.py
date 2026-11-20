from __future__ import annotations

from django.urls import path

from apps.gameplay.api.views import (
    SessionActivateView,
    SessionCreateView,
    SessionHeartbeatView,
    SessionResultView,
)

urlpatterns = [
    path("sessions", SessionCreateView.as_view(), name="session-create"),
    path(
        "sessions/<uuid:session_id>/activate",
        SessionActivateView.as_view(),
        name="session-activate",
    ),
    path(
        "sessions/<uuid:session_id>/heartbeat",
        SessionHeartbeatView.as_view(),
        name="session-heartbeat",
    ),
    path(
        "sessions/<uuid:session_id>/result",
        SessionResultView.as_view(),
        name="session-result",
    ),
]
