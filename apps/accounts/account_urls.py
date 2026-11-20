from django.urls import path

from apps.accounts import views

app_name = "account"

urlpatterns = [
    path("", views.profile, name="profile"),
    path("edit/", views.profile_edit, name="edit"),
    path("password/", views.password_change, name="password"),
    path("export/", views.export_account, name="export"),
    path("delete/", views.delete_account, name="delete"),
    path("delete/cancel/", views.delete_cancel, name="delete_cancel"),
]
