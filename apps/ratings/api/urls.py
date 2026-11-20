from __future__ import annotations

from django.urls import path

from apps.ratings.api.views import RatingView, RatingVoteView

urlpatterns = [
    path("games/<str:game_id>/rating", RatingVoteView.as_view(), name="rating-vote"),
    path(
        "games/<str:game_id>/rating/summary",
        RatingView.as_view(),
        name="rating-summary",
    ),
]
