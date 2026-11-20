from django.urls import path

from apps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("2fa/", views.two_factor_verify, name="two_factor_verify"),
    path("2fa/recovery/", views.two_factor_recovery, name="two_factor_recovery"),
    path("2fa/owner-recovery/", views.two_factor_owner_recovery, name="two_factor_owner_recovery"),
    path("2fa/setup/", views.two_factor_setup, name="two_factor_setup"),
    path("2fa/regenerate/", views.two_factor_regenerate, name="two_factor_regenerate"),
    path("2fa/disable/", views.two_factor_disable, name="two_factor_disable"),
    path("verify-email/<str:token>/", views.verify_email, name="verify_email"),
    path("resend-verification/", views.resend_verification, name="resend_verification"),
    path("password-reset/", views.password_reset_request, name="password_reset"),
    path(
        "password-reset/confirm/<str:token>/",
        views.password_reset_confirm,
        name="password_reset_confirm",
    ),
]
