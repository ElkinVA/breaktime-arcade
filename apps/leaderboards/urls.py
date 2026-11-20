from __future__ import annotations

from django.urls import path

from apps.leaderboards.views import LeaderboardView, MyBestView

urlpatterns = [
    path(
        "games/<str:game_id>/leaderboard",
        LeaderboardView.as_view(),
        name="leaderboard",
    ),
    path(
        "games/<str:game_id>/me/best",
        MyBestView.as_view(),
        name="leaderboard-me-best",
    ),
]
