from __future__ import annotations

import time

import pyotp
import pytest
from django.core.cache import cache, caches
from django.test import Client, override_settings

from apps.accounts.models import LoginEvent, OwnerRecoveryCode, RecoveryCode, User

LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "throttle": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}
PASSWORD = "correct horse battery staple"


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    cache.clear()
    caches["throttle"].clear()
    yield
    cache.clear()
    caches["throttle"].clear()


def _staff(login: str = "staff") -> User:
    user = User.objects.create_user(login=login, password=PASSWORD)
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    return user


def _superuser(login: str = "owner") -> User:
    user = User.objects.create_user(login=login, password=PASSWORD)
    user.is_staff = True
    user.is_superuser = True
    user.save(update_fields=["is_staff", "is_superuser"])
    return user


def _next_code(secret: str) -> str:
    """Код следующего 30-секундного окна (setup уже использовал текущее)."""
    return pyotp.TOTP(secret).at(int(time.time()) + 30)


def _begin_login(client: Client, login: str = "staff") -> None:
    response = client.post("/en/auth/login/", {"username": login, "password": PASSWORD})
    assert response.status_code == 302
    assert response["Location"].endswith("/en/auth/2fa/setup/") or response["Location"].endswith(
        "/en/auth/2fa/"
    )


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_staff_login_requires_setup_then_totp_and_recovery_codes() -> None:
    user = _staff()
    client = Client()
    _begin_login(client)

    setup = client.get("/en/auth/2fa/setup/")
    assert setup.status_code == 200
    secret = setup.context["secret"]
    code = pyotp.TOTP(secret).now()
    enabled = client.post("/en/auth/2fa/setup/", {"code": code})

    assert enabled.status_code == 200
    assert len(enabled.context["recovery_codes"]) == 10
    user.refresh_from_db()
    assert user.totp_confirmed_at is not None
    assert RecoveryCode.objects.filter(user=user, used_at__isnull=True).count() == 10
    assert client.get("/en/account/").status_code == 200

    client.post("/en/auth/logout/")
    _begin_login(client)
    verify = client.get("/en/auth/2fa/")
    assert verify.status_code == 200
    verified = client.post("/en/auth/2fa/", {"code": _next_code(user.totp_secret)})
    assert verified.status_code == 302
    assert client.get("/en/account/").status_code == 200


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_staff_totp_code_cannot_be_replayed() -> None:
    user = _staff()
    client = Client()
    _begin_login(client)
    secret = client.get("/en/auth/2fa/setup/").context["secret"]
    code = pyotp.TOTP(secret).now()
    client.post("/en/auth/2fa/setup/", {"code": code})
    client.post("/en/auth/logout/")
    _begin_login(client)

    replay = client.post("/en/auth/2fa/", {"code": code})
    assert replay.status_code == 200
    assert client.get("/en/account/").status_code == 302
    user.refresh_from_db()
    assert user.totp_confirmed_at is not None


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_recovery_code_is_single_use() -> None:
    user = _staff()
    client = Client()
    _begin_login(client)
    secret = client.get("/en/auth/2fa/setup/").context["secret"]
    code = pyotp.TOTP(secret).now()
    enabled = client.post("/en/auth/2fa/setup/", {"code": code})
    recovery = enabled.context["recovery_codes"][0]
    client.post("/en/auth/logout/")
    _begin_login(client)

    first = client.post("/en/auth/2fa/recovery/", {"code": recovery})
    assert first.status_code == 302
    assert client.get("/en/account/").status_code == 200

    client.post("/en/auth/logout/")
    _begin_login(client)
    second = client.post("/en/auth/2fa/recovery/", {"code": recovery})
    assert second.status_code == 200
    assert client.get("/en/account/").status_code == 302
    user.refresh_from_db()
    assert RecoveryCode.objects.filter(user=user, used_at__isnull=False).count() == 1


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_staff_can_disable_2fa_with_password_and_totp() -> None:
    user = _staff()
    client = Client()
    _begin_login(client)
    secret = client.get("/en/auth/2fa/setup/").context["secret"]
    code = pyotp.TOTP(secret).now()
    client.post("/en/auth/2fa/setup/", {"code": code})
    user.refresh_from_db()

    disable = client.post(
        "/en/auth/2fa/disable/",
        {"password": PASSWORD, "code": _next_code(user.totp_secret)},
    )
    assert disable.status_code == 302
    user.refresh_from_db()
    assert user.totp_secret == ""
    assert user.totp_confirmed_at is None
    assert not RecoveryCode.objects.filter(user=user).exists()
    assert client.get("/en/account/").status_code == 302


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_owner_offline_code_forces_new_2fa_setup() -> None:
    user = _superuser()
    client = Client()
    _begin_login(client, "owner")
    secret = client.get("/en/auth/2fa/setup/").context["secret"]
    enabled = client.post("/en/auth/2fa/setup/", {"code": pyotp.TOTP(secret).now()})
    owner_code = enabled.context["owner_recovery_code"]
    assert owner_code
    assert OwnerRecoveryCode.objects.filter(user=user, used_at__isnull=True).exists()
    client.post("/en/auth/logout/")

    _begin_login(client, "owner")
    recovered = client.post("/en/auth/2fa/owner-recovery/", {"code": owner_code})
    assert recovered.status_code == 302
    assert recovered["Location"].endswith("/en/auth/2fa/setup/")
    user.refresh_from_db()
    assert user.totp_secret == ""
    assert user.totp_confirmed_at is None
    assert not OwnerRecoveryCode.objects.filter(user=user).exists()
    assert LoginEvent.objects.filter(user=user, event=LoginEvent.EVENT_OWNER_RECOVERY_USED).exists()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_recovery_codes_can_be_regenerated() -> None:
    user = _staff()
    client = Client()
    _begin_login(client)
    secret = client.get("/en/auth/2fa/setup/").context["secret"]
    enabled = client.post("/en/auth/2fa/setup/", {"code": pyotp.TOTP(secret).now()})
    old_code = enabled.context["recovery_codes"][0]
    user.refresh_from_db()

    response = client.post(
        "/en/auth/2fa/regenerate/",
        {"password": PASSWORD, "code": _next_code(user.totp_secret)},
    )
    assert response.status_code == 200
    assert len(response.context["recovery_codes"]) == 10
    assert old_code not in response.context["recovery_codes"]

    client.post("/en/auth/logout/")
    _begin_login(client)
    stale = client.post("/en/auth/2fa/recovery/", {"code": old_code})
    assert stale.status_code == 200


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_login_events_are_recorded_without_plaintext_subject() -> None:
    User.objects.create_user(login="player", password=PASSWORD)
    client = Client()
    client.post("/en/auth/login/", {"username": "player", "password": "wrong password"})
    client.post("/en/auth/login/", {"username": "player", "password": PASSWORD})

    events = list(LoginEvent.objects.order_by("created_at"))
    assert [event.event for event in events] == [
        LoginEvent.EVENT_LOGIN_FAILED,
        LoginEvent.EVENT_LOGIN_SUCCESS,
    ]
    assert events[0].subject_hash
    assert "player" not in events[0].subject_hash
    assert events[1].user is not None
    assert events[1].subject_hash == ""


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_session_without_verified_2fa_is_rejected_for_staff() -> None:
    user = _staff()
    user.totp_secret = pyotp.random_base32()
    user.totp_confirmed_at = user.created_at
    user.save(update_fields=["totp_secret", "totp_confirmed_at"])
    client = Client()
    client.force_login(user)

    response = client.get("/en/account/")

    assert response.status_code == 302
    assert "/en/auth/login/" in response["Location"]


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_non_staff_login_does_not_require_2fa() -> None:
    User.objects.create_user(login="player", password=PASSWORD)
    client = Client()

    response = client.post("/en/auth/login/", {"username": "player", "password": PASSWORD})

    assert response.status_code == 302
    assert client.get("/en/account/").status_code == 200
