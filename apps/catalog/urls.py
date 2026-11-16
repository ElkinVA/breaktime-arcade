"""Маршруты каталога. Заглушки; наполняются блоками 3 и 5."""
from __future__ import annotations

from django.urls import path

from apps.catalog import views

app_name = "catalog"

urlpatterns = [
    path("", views.home, name="home"),
    path("games/", views.game_list, name="game_list"),
    path("games/<str:slug>/", views.game_detail, name="game_detail"),
    path("games/<str:slug>/play/", views.game_play, name="game_play"),
    path("games/<str:slug>/leaderboard/", views.game_leaderboard, name="game_leaderboard"),
    path("genres/<str:slug>/", views.genre_detail, name="genre_detail"),
]
