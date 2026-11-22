"""Маршруты CRM (§2.16)."""

from __future__ import annotations

from django.urls import path

from apps.crm import views

app_name = "crm"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("games/", views.games_list, name="games"),
    path("games/<uuid:game_id>/", views.game_detail, name="game_detail"),
    path("games/<uuid:game_id>/publish/", views.game_publish, name="game_publish"),
    path("games/<uuid:game_id>/rollback/", views.game_rollback, name="game_rollback"),
]
