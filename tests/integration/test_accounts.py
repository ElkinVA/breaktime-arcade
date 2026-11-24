from __future__ import annotations

import re
from datetime import timedelta

import pyotp
import pytest
from django.contrib.auth import authenticate
from django.core import mail
from django.core.cache import cache, caches
from django.http import HttpResponse
from django.test import Client, RequestFactory, override_settings
from django.utils import timezone

from apps.accounts.models import (
    AccountToken,
    AnonymousIdentity,
    EmailAddress,
    NicknameHistory,
    NicknameReservation,
    OwnerRecoveryCode,
    RecoveryCode,
    User,
    UserProfile,
)
from apps.accounts.services.anonymous import COOKIE_NAME, get_or_create_anonymous_identity
from apps.accounts.services.profile import anonymize_user, export_account_data
from apps.accounts.services.tokens import issue_token
from apps.accounts.services.two_factor import (
    enable_totp,
    generate_owner_recovery_code,
    generate_secret,
    verify_owner_recovery_code,
    verify_recovery_code,
    verify_totp,
)
from apps.accounts.tasks import anonymize_due_accounts

LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "throttle": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    cache.clear()
    caches["throttle"].clear()
    yield
    cache.clear()
    caches["throttle"].clear()


@pytest.fixture(autouse=True)
def bypass_rate_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rate limits проверяются отдельно; здесь не смешиваем их с account flow."""
    from apps.accounts.services.rate_limit import ALLOWED

    monkeypatch.setattr("apps.accounts.views.registration_attempt", lambda ip: ALLOWED)
    monkeypatch.setattr("apps.accounts.views.release_registration", lambda ip: None)
    monkeypatch.setattr("apps.accounts.views.login_attempt", lambda login, ip: ALLOWED)
    monkeypatch.setattr("apps.accounts.views.record_login_ip_failure", lambda ip: None)
    monkeypatch.setattr("apps.accounts.views.clear_login_attempts", lambda login: None)
    monkeypatch.setattr("apps.accounts.views.two_factor_attempt", lambda user_id, ip: ALLOWED)
    monkeypatch.setattr("apps.accounts.views.record_two_factor_ip_failure", lambda ip: None)
    monkeypatch.setattr("apps.accounts.views.clear_two_factor_attempts", lambda user_id: None)
    monkeypatch.setattr("apps.accounts.views.password_reset_attempt", lambda email, ip: ALLOWED)


def payload(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "login": "alice",
        "nickname": "Alice",
        "password1": "correct horse battery staple",
        "password2": "correct horse battery staple",
        "email": "alice@example.com",
        "age_confirmed": "on",
        "terms_accepted": "on",
        "privacy_accepted": "on",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
@override_settings(
    CACHES=LOCMEM_CACHES,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_register_creates_user_profile_email_and_legal_acceptance() -> None:
    client = Client()
    response = client.post("/en/auth/register/", payload())

    assert response.status_code == 302
    user = User.objects.get(login="alice")
    assert user.check_password("correct horse battery staple")
    assert user.profile.nickname == "Alice"
    assert user.email_address.email == "alice@example.com"
    assert user.email_address.verified_at is None
    assert user.legal_acceptances.count() == 1
    assert NicknameHistory.objects.filter(user=user).count() == 1
    assert len(mail.outbox) == 1
    assert "verify-email" in mail.outbox[0].body


@pytest.mark.django_db
@override_settings(
    CACHES=LOCMEM_CACHES,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_register_without_email_is_allowed_and_sends_nothing() -> None:
    client = Client()
    response = client.post("/en/auth/register/", payload(email=""))

    assert response.status_code == 302
    user = User.objects.get(login="alice")
    assert not EmailAddress.objects.filter(user=user).exists()
    assert mail.outbox == []


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_register_rejects_duplicate_login_and_confusable_nickname() -> None:
    client = Client()
    assert client.post("/en/auth/register/", payload(nickname="paypal")).status_code == 302
    client.post("/en/auth/logout/")

    duplicate_login = client.post("/en/auth/register/", payload(nickname="Other"))
    assert duplicate_login.status_code == 200
    assert "login" in duplicate_login.context["form"].errors

    confusable = client.post(
        "/en/auth/register/",
        payload(login="bob", nickname="pаypal", email="bob@example.com"),
    )
    assert confusable.status_code == 200
    assert "nickname" in confusable.context["form"].errors


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_login_logout_and_profile_require_authentication() -> None:
    client = Client()
    client.post("/en/auth/register/", payload())
    client.post("/en/auth/logout/")

    anonymous_profile = client.get("/en/account/")
    assert anonymous_profile.status_code == 302
    assert "/en/auth/login/" in anonymous_profile["Location"]

    login = client.post(
        "/en/auth/login/",
        {"username": "alice", "password": "correct horse battery staple"},
    )
    assert login.status_code == 302
    assert client.get("/en/account/").status_code == 200

    logout = client.post("/en/auth/logout/")
    assert logout.status_code == 302
    assert client.get("/en/account/").status_code == 302


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_login_fails_closed_when_throttle_cache_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.accounts.services.rate_limit import UNAVAILABLE

    monkeypatch.setattr("apps.accounts.views.login_attempt", lambda login, ip: UNAVAILABLE)
    client = Client()
    response = client.post(
        "/en/auth/login/",
        {"username": "alice", "password": "correct horse battery staple"},
    )
    assert response.status_code == 503
    assert not response.wsgi_request.user.is_authenticated


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_login_fails_closed_for_empty_username_too(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.accounts.services.rate_limit import UNAVAILABLE

    monkeypatch.setattr("apps.accounts.views.login_attempt", lambda login, ip: UNAVAILABLE)
    client = Client()
    response = client.post("/en/auth/login/", {"username": "", "password": "x"})
    assert response.status_code == 503


@pytest.mark.django_db
@override_settings(
    CACHES=LOCMEM_CACHES,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_email_verification_consumes_token() -> None:
    client = Client()
    client.post("/en/auth/register/", payload())
    token = re.search(r"/en/auth/verify-email/([^/]+)/", mail.outbox[0].body)
    assert token is not None

    response = client.get(f"/en/auth/verify-email/{token.group(1)}/")

    assert response.status_code == 302
    assert EmailAddress.objects.get(user__login="alice").verified_at is not None
    assert AccountToken.objects.filter(
        purpose=AccountToken.PURPOSE_EMAIL_VERIFY, used_at__isnull=False
    ).exists()


@pytest.mark.django_db
@override_settings(
    CACHES=LOCMEM_CACHES,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_password_reset_is_neutral_and_requires_verified_email() -> None:
    client = Client()
    client.post("/en/auth/register/", payload())
    mail.outbox.clear()

    unverified = client.post("/en/auth/password-reset/", {"email": "alice@example.com"})
    assert unverified.status_code == 302
    assert mail.outbox == []

    email = EmailAddress.objects.get(user__login="alice")
    email.verified_at = timezone.now()
    email.save(update_fields=["verified_at", "updated_at"])

    client.post("/en/auth/password-reset/", {"email": "alice@example.com"})
    assert len(mail.outbox) == 1
    token = re.search(r"/en/auth/password-reset/confirm/([^/]+)/", mail.outbox[0].body)
    assert token is not None

    response = client.post(
        f"/en/auth/password-reset/confirm/{token.group(1)}/",
        {"password1": "new correct horse battery", "password2": "new correct horse battery"},
    )
    assert response.status_code == 302
    assert User.objects.get(login="alice").check_password("new correct horse battery")


@pytest.mark.django_db
@override_settings(
    CACHES=LOCMEM_CACHES,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_new_password_reset_request_invalidates_previous_token() -> None:
    client = Client()
    client.post("/en/auth/register/", payload())
    email = EmailAddress.objects.get(user__login="alice")
    email.verified_at = timezone.now()
    email.save(update_fields=["verified_at", "updated_at"])
    mail.outbox.clear()

    client.post("/en/auth/password-reset/", {"email": "alice@example.com"})
    first = re.search(r"/en/auth/password-reset/confirm/([^/]+)/", mail.outbox[0].body)
    client.post("/en/auth/password-reset/", {"email": "alice@example.com"})
    second = re.search(r"/en/auth/password-reset/confirm/([^/]+)/", mail.outbox[1].body)
    assert first is not None and second is not None

    stale = client.get(f"/en/auth/password-reset/confirm/{first.group(1)}/")
    assert stale.status_code == 302
    assert User.objects.get(login="alice").check_password("correct horse battery staple")


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_profile_update_and_nickname_rate_limit() -> None:
    client = Client()
    client.post("/en/auth/register/", payload())
    user = User.objects.get(login="alice")
    history = NicknameHistory.objects.get(user=user)
    history.valid_from = timezone.now() - timedelta(days=31)
    history.save(update_fields=["valid_from"])

    response = client.post(
        "/en/account/edit/",
        {
            "nickname": "AliceNew",
            "email": "alice@example.com",
            "language_code": "en",
            "theme": "light",
        },
    )
    assert response.status_code == 302
    user.profile.refresh_from_db()
    assert user.profile.nickname == "AliceNew"
    assert user.profile.theme == "light"
    assert NicknameHistory.objects.filter(user=user).count() == 2

    user.profile.refresh_from_db()
    blocked = client.post(
        "/en/account/edit/",
        {
            "nickname": "AliceThird",
            "email": "alice@example.com",
            "language_code": "en",
            "theme": "dark",
        },
    )
    assert blocked.status_code == 200
    assert (
        "nickname" in blocked.context["form"].errors or blocked.context["form"].non_field_errors()
    )


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_password_change_invalidates_other_sessions() -> None:
    client = Client()
    client.post("/en/auth/register/", payload())
    second = Client()
    second.post(
        "/en/auth/login/",
        {"username": "alice", "password": "correct horse battery staple"},
    )
    assert second.get("/en/account/").status_code == 200

    response = client.post(
        "/en/account/password/",
        {
            "old_password": "correct horse battery staple",
            "new_password1": "new correct horse battery",
            "new_password2": "new correct horse battery",
        },
    )
    assert response.status_code == 302
    assert client.get("/en/account/").status_code == 200
    assert second.get("/en/account/").status_code == 302


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_registration_rejects_missing_consent_and_password_mismatch() -> None:
    client = Client()
    response = client.post(
        "/en/auth/register/",
        payload(password2="different password", terms_accepted=""),
    )

    assert response.status_code == 200
    errors = response.context["form"].errors
    assert "terms_accepted" in errors
    assert "password2" in errors


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_invalid_email_and_password_reset_tokens_are_rejected() -> None:
    client = Client()

    verify = client.get("/en/auth/verify-email/not-a-token/")
    reset = client.get("/en/auth/password-reset/confirm/not-a-token/")

    assert verify.status_code == 302
    assert reset.status_code == 302
    assert not AccountToken.objects.filter(used_at__isnull=False).exists()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_registration_post_requires_csrf() -> None:
    client = Client(enforce_csrf_checks=True)

    response = client.post("/en/auth/register/", payload())

    assert response.status_code == 403


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_email_change_requires_current_password() -> None:
    client = Client()
    client.post("/en/auth/register/", payload())
    client.post("/en/auth/logout/")
    client.post(
        "/en/auth/login/",
        {"username": "alice", "password": "correct horse battery staple"},
    )

    without_password = client.post(
        "/en/account/edit/",
        {
            "nickname": "Alice",
            "email": "new@example.com",
            "language_code": "en",
            "theme": "dark",
        },
    )
    assert without_password.status_code == 200
    assert EmailAddress.objects.get(user__login="alice").email == "alice@example.com"

    with_password = client.post(
        "/en/account/edit/",
        {
            "nickname": "Alice",
            "email": "new@example.com",
            "current_password": "correct horse battery staple",
            "language_code": "en",
            "theme": "dark",
        },
    )
    assert with_password.status_code == 302
    address = EmailAddress.objects.get(user__login="alice")
    assert address.email == "new@example.com"
    assert address.verified_at is None


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_account_export_and_deletion_request_cancel() -> None:
    client = Client()
    client.post("/en/auth/register/", payload())
    export = client.get("/en/account/export/")
    assert export.status_code == 200
    assert b"alice" in export.content

    response = client.post(
        "/en/account/delete/",
        {"password": "correct horse battery staple", "confirmation": "DELETE"},
    )
    assert response.status_code == 302
    user = User.objects.get(login="alice")
    assert user.profile.deletion_requested_at is not None

    cancel = client.post("/en/account/delete/cancel/")
    assert cancel.status_code == 302
    user.profile.refresh_from_db()
    assert user.profile.deletion_requested_at is None


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_anonymous_identity_cookie_is_signed_and_reused() -> None:
    request = RequestFactory().get("/en/games/")
    response = HttpResponse()
    first = get_or_create_anonymous_identity(request, response)
    cookie = response.cookies[COOKIE_NAME].value
    assert AnonymousIdentity.objects.count() == 1

    request.COOKIES[COOKIE_NAME] = cookie
    second = get_or_create_anonymous_identity(request, HttpResponse())
    assert second.pk == first.pk
    assert AnonymousIdentity.objects.count() == 1


@pytest.mark.django_db
def test_anonymize_user_removes_pii_and_reserves_nickname() -> None:
    user = User.objects.create_user(login="alice", password="correct horse battery staple")
    UserProfile.objects.create(
        user=user,
        nickname="Alice",
        nickname_skeleton="alice",
    )
    EmailAddress.objects.create(user=user, email="alice@example.com")
    NicknameHistory.objects.create(user=user, nickname="Alice", nickname_skeleton="alice")
    issue_token(
        user,
        AccountToken.PURPOSE_PASSWORD_RESET,
        ttl_seconds=1800,
        email="alice@example.com",
    )

    anonymize_user(user)

    assert not UserProfile.objects.filter(user=user).exists()
    assert not EmailAddress.objects.filter(user=user).exists()
    assert not AccountToken.objects.filter(user=user).exists()
    assert NicknameReservation.objects.count() == 1
    user.refresh_from_db()
    assert user.is_active is False
    assert user.login.startswith("deleted-")


@pytest.mark.django_db
def test_tombstone_cannot_authenticate_with_password_totp_or_recovery_code() -> None:
    password = "correct horse battery staple"
    user = User.objects.create_user(login="creduser", password=password)
    user.is_staff = True
    user.is_superuser = True
    user.save(update_fields=["is_staff", "is_superuser"])
    UserProfile.objects.create(user=user, nickname="CredUser", nickname_skeleton="creduser")

    secret = generate_secret()
    recovery_codes = enable_totp(user, secret, pyotp.TOTP(secret).now())
    owner_recovery_code = generate_owner_recovery_code(user)
    original_login = user.login
    assert RecoveryCode.objects.filter(user=user).count() == len(recovery_codes)
    assert OwnerRecoveryCode.objects.filter(user=user).exists()

    anonymize_user(user)

    user.refresh_from_db()
    # Password hash is unusable and the deleted-account login cannot log in.
    assert not user.check_password(password)
    assert user.has_usable_password() is False
    assert authenticate(request=None, login=original_login, password=password) is None

    # Every 2FA credential is gone and every verification path fails closed.
    assert user.totp_secret == ""
    assert user.totp_confirmed_at is None
    assert user.totp_last_counter is None
    assert not RecoveryCode.objects.filter(user=user).exists()
    assert not OwnerRecoveryCode.objects.filter(user=user).exists()
    assert verify_totp(user, pyotp.TOTP(secret).now()) is False
    assert verify_recovery_code(user, recovery_codes[0]) is False
    assert verify_owner_recovery_code(user, owner_recovery_code) is False

    # Export payload shape stays stable and never carries credentials.
    payload = export_account_data(user)
    assert set(payload) == {
        "login",
        "created_at",
        "profile",
        "email",
        "legal_acceptances",
    }
    assert "password" not in payload
    assert "totp_secret" not in payload
    assert "recovery_codes" not in payload


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_anonymize_due_accounts_processes_expired_window() -> None:
    user = User.objects.create_user(login="dueuser", password="correct horse battery staple")
    profile = UserProfile.objects.create(
        user=user,
        nickname="DueUser",
        nickname_skeleton="dueuser",
        deletion_requested_at=timezone.now() - timedelta(days=8),
    )

    assert anonymize_due_accounts() == 1
    assert not UserProfile.objects.filter(pk=profile.pk).exists()
    user.refresh_from_db()
    assert user.is_active is False
