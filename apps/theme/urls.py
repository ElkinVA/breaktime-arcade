from django.urls import path

from apps.theme import views

app_name = "theme"

urlpatterns = [
    path("theme-<str:hash>.css", views.theme_css, name="theme_css"),
]
