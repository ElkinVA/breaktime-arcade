"""Маршруты CRM (§2.16)."""

from __future__ import annotations

from django.urls import path

from apps.crm import views

app_name = "crm"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("step-up/", views.step_up, name="step_up"),
    path("staff/", views.staff_management, name="staff"),
    path("content/", views.content_overview, name="content"),
    path("moderation/", views.moderation_queue, name="moderation"),
    path("audit/", views.audit_log, name="audit"),
    path("games/", views.games_list, name="games"),
    path("games/add/", views.wizard_upload, name="game_add"),
    path("games/<uuid:game_id>/", views.game_detail, name="game_detail"),
    path("games/<uuid:game_id>/publish/", views.game_publish, name="game_publish"),
    path("games/<uuid:game_id>/rollback/", views.game_rollback, name="game_rollback"),
    # Мастер добавления/обновления игры (§2.14.5).
    path("wizard/", views.wizard_upload, name="wizard_upload"),
    path("wizard/upload/", views.wizard_upload, name="wizard_step1"),
    path("wizard/<uuid:draft_id>/", views.wizard_analysis, name="wizard_step2"),
    path("wizard/<uuid:draft_id>/analysis/", views.wizard_analysis, name="wizard_analysis"),
    path("wizard/<uuid:draft_id>/card/", views.wizard_card, name="wizard_card"),
    path("wizard/<uuid:draft_id>/step3/", views.wizard_card, name="wizard_step3"),
    path("wizard/<uuid:draft_id>/check/", views.wizard_check, name="wizard_check"),
    path("wizard/<uuid:draft_id>/step4/", views.wizard_check, name="wizard_step4"),
    path("wizard/<uuid:draft_id>/publish/", views.wizard_publish, name="wizard_publish"),
    path("wizard/<uuid:draft_id>/step5/", views.wizard_publish, name="wizard_step5"),
    path("wizard/<uuid:draft_id>/report/", views.wizard_report, name="wizard_report"),
]
