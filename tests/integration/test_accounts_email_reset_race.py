"""ARCADE-EMAIL-RESET-RACE-001: email change/removal vs reset-confirm race.

``apps.accounts.views._update_email`` and the POST branch of
``password_reset_confirm`` take the same ``User`` row lock. The submissions
therefore have a single linear order:

* if the email change/removal commits first, the old-address reset token is
  already invalidated and can no longer set a password;
* if the reset-confirm wins the lock first, it completes against the
  still-current address and the email change is applied afterwards.

The workers below use separate connections, so only the row locks under test
serialise them.
"""

from __future__ import annotations

import threading
from typing import Any
from uuid import UUID

import pytest
from django.db import connections
from django.test import Client, override_settings
from django.utils import timezone

from apps.accounts import views as accounts_views
from apps.accounts.models import AccountToken, EmailAddress, User
from apps.accounts.services.email import password_reset_token_valid
from apps.accounts.services.registration import register_user
from apps.accounts.services.tokens import issue_token

OLD_PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "Another strong passphrase 42"
OLD_EMAIL = "old@example.com"
NEW_EMAIL = "new@example.com"


def _make_user(login: str) -> User:
    user = register_user(
        login=login,
        password=OLD_PASSWORD,
        nickname="Racer",
        email=OLD_EMAIL,
        age_confirmed=True,
        terms_accepted=True,
        privacy_accepted=True,
    )
    EmailAddress.objects.filter(user=user).update(verified_at=timezone.now())
    return user


def _reset_token(user: User) -> str:
    return issue_token(
        user,
        AccountToken.PURPOSE_PASSWORD_RESET,
        ttl_seconds=1800,
        email=OLD_EMAIL,
    )


def _email_change_worker(
    user_id: UUID,
    new_email: str,
    result: dict[str, Any],
    client: Client | None = None,
) -> None:
    try:
        # Authenticate before the competing reset takes the row lock. A
        # ``force_login`` inside this thread updates ``last_login`` and would
        # block on the same User row before the request reaches the view.
        if client is None:
            client = Client()
            client.force_login(User.objects.get(pk=user_id))
        response = client.post(
            "/en/account/edit/",
            {
                "nickname": "Racer",
                "email": new_email,
                "current_password": OLD_PASSWORD,
                "language_code": "en",
                "theme": "dark",
            },
        )
        result["status"] = response.status_code
    except Exception as exc:  # noqa: BLE001 - surfaced on the test thread
        result["error"] = exc
    finally:
        connections.close_all()


def _reset_worker(token: str, result: dict[str, Any]) -> None:
    try:
        client = Client()
        response = client.post(
            f"/en/auth/password-reset/confirm/{token}/",
            {"password1": NEW_PASSWORD, "password2": NEW_PASSWORD},
        )
        result["status"] = response.status_code
    except Exception as exc:  # noqa: BLE001 - surfaced on the test thread
        result["error"] = exc
    finally:
        connections.close_all()


def _pause_invalidate(
    monkeypatch: pytest.MonkeyPatch,
    *,
    thread_name: str,
    paused: threading.Event,
    release: threading.Event,
) -> None:
    """Pause the named flow after it took the User lock, before token updates.

    Pausing inside ``invalidate_tokens`` keeps the surrounding transaction and
    its ``User`` row lock open, which makes the interleaving deterministic
    instead of timing-based.
    """
    real_invalidate = accounts_views.invalidate_tokens

    def invalidate(user: User, purpose: str) -> int:
        if (
            purpose == AccountToken.PURPOSE_PASSWORD_RESET
            and threading.current_thread().name == thread_name
            and not paused.is_set()
        ):
            paused.set()
            if not release.wait(timeout=30):
                raise AssertionError("test never released the paused transaction")
        return real_invalidate(user, purpose)

    monkeypatch.setattr(accounts_views, "invalidate_tokens", invalidate)


@pytest.mark.django_db(transaction=True)
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
@pytest.mark.parametrize(
    ("new_email", "expects_address"),
    [(NEW_EMAIL, True), ("", False)],
    ids=["change", "removal"],
)
def test_committed_email_change_or_removal_wins_over_old_reset_token(
    monkeypatch: pytest.MonkeyPatch,
    new_email: str,
    expects_address: bool,
) -> None:
    """A committed email change/removal makes the old reset token unusable."""
    user = _make_user(f"race_committed_{'change' if expects_address else 'remove'}")
    token = _reset_token(user)

    paused = threading.Event()
    release = threading.Event()
    _pause_invalidate(
        monkeypatch,
        thread_name="email-change",
        paused=paused,
        release=release,
    )

    change_result: dict[str, Any] = {}
    reset_result: dict[str, Any] = {}
    reset_started = threading.Event()

    def reset_worker() -> None:
        reset_started.set()
        _reset_worker(token, reset_result)

    # Authenticate up front so force_login's last_login write cannot contend
    # for the User row lock under test.
    change_client = Client()
    change_client.force_login(user)
    # Change/removal acquires the User lock and pauses after rewriting the
    # address, before invalidating reset tokens.
    change_thread = threading.Thread(
        target=_email_change_worker,
        args=(user.pk, new_email, change_result, change_client),
        name="email-change",
    )
    reset_thread = threading.Thread(target=reset_worker, name="reset-confirm")
    change_thread.start()
    reset_thread_started = False
    try:
        assert paused.wait(timeout=15), "email change never reached token invalidation"
        # The reset starts while the change still holds the lock. It must wait
        # for the commit and then observe the invalidated token.
        reset_thread.start()
        reset_thread_started = True
        assert reset_started.wait(timeout=15)
        reset_thread.join(timeout=0.5)
        blocked = reset_thread.is_alive()
    finally:
        release.set()
        change_thread.join(timeout=30)
        if reset_thread_started:
            reset_thread.join(timeout=30)

    assert blocked, "reset-confirm was not serialized behind the email change"
    assert not change_thread.is_alive()
    assert not reset_thread.is_alive()
    assert "error" not in change_result, change_result.get("error")
    assert "error" not in reset_result, reset_result.get("error")
    assert change_result["status"] == 302
    assert reset_result["status"] == 302

    user.refresh_from_db()
    assert user.check_password(OLD_PASSWORD) is True
    assert user.check_password(NEW_PASSWORD) is False

    address = EmailAddress.objects.filter(user=user).first()
    if expects_address:
        assert address is not None
        assert address.email == new_email
        assert address.verified_at is None
    else:
        assert address is None

    assert password_reset_token_valid(token) is False


@pytest.mark.django_db(transaction=True)
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
@pytest.mark.parametrize(
    ("new_email", "expects_address"),
    [(NEW_EMAIL, True), ("", False)],
    ids=["change", "removal"],
)
def test_reset_confirm_wins_against_current_address(
    monkeypatch: pytest.MonkeyPatch,
    new_email: str,
    expects_address: bool,
) -> None:
    """A reset that takes the lock first completes against the current address."""
    user = _make_user(f"race_reset_{'change' if expects_address else 'remove'}")
    token = _reset_token(user)

    reset_paused = threading.Event()
    release_reset = threading.Event()
    change_entered = threading.Event()

    real_consume = accounts_views.consume_token

    def consume(raw: str, purpose: str) -> AccountToken | None:
        consumed = real_consume(raw, purpose)
        if (
            purpose == AccountToken.PURPOSE_PASSWORD_RESET
            and threading.current_thread().name == "reset-confirm"
            and not reset_paused.is_set()
        ):
            # The User row lock is already held and the token is marked used,
            # but the password update and commit are still pending.
            reset_paused.set()
            if not release_reset.wait(timeout=30):
                raise AssertionError("test never released the paused reset")
        return consumed

    real_update_email = accounts_views._update_email

    def update_email(request: Any, locked: User, value: str) -> None:
        # The email-change form has validated the current password against the
        # still-current hash; the real call will block on the User row lock.
        change_entered.set()
        real_update_email(request, locked, value)

    monkeypatch.setattr(accounts_views, "consume_token", consume)
    monkeypatch.setattr(accounts_views, "_update_email", update_email)

    change_result: dict[str, Any] = {}
    reset_result: dict[str, Any] = {}
    change_client = Client()
    change_client.force_login(user)

    reset_thread = threading.Thread(
        target=_reset_worker,
        args=(token, reset_result),
        name="reset-confirm",
    )
    change_thread = threading.Thread(
        target=_email_change_worker,
        args=(user.pk, new_email, change_result, change_client),
        name="email-change",
    )
    reset_thread.start()
    change_thread_started = False
    try:
        assert reset_paused.wait(timeout=15), "reset confirm never took the User lock"
        change_thread.start()
        change_thread_started = True
        assert change_entered.wait(timeout=15), "email change never reached _update_email"
        change_thread.join(timeout=0.5)
        blocked = change_thread.is_alive()
    finally:
        release_reset.set()
        reset_thread.join(timeout=30)
        if change_thread_started:
            change_thread.join(timeout=30)

    assert blocked, "email change was not serialized behind the reset confirm"
    assert not reset_thread.is_alive()
    assert not change_thread.is_alive()
    assert "error" not in reset_result, reset_result.get("error")
    assert "error" not in change_result, change_result.get("error")
    assert reset_result["status"] == 302
    assert change_result["status"] == 302

    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD) is True
    assert user.check_password(OLD_PASSWORD) is False

    address = EmailAddress.objects.filter(user=user).first()
    if expects_address:
        assert address is not None
        assert address.email == new_email
        assert address.verified_at is None
    else:
        assert address is None

    assert password_reset_token_valid(token) is False
