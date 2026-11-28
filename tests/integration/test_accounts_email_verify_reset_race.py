"""ARCADE-EMAIL-VERIFY-RESET-RACE-001: reset-request and verify vs email change.

``password_reset_request`` and ``verify_email_token`` take the same ``User``
row lock as ``_update_email``. The submissions therefore have a single linear
order:

* a reset request that wins the lock issues its token for the still-current
  address; the committed email change then invalidates that token;
* an email change that commits first leaves no verified address for the reset
  request and invalidates any verification token issued for the old address;
* a verification that wins the lock only marks the address it was issued for,
  while a verification that loses the lock re-checks the current address and
  does not mark a freshly changed (unverified) address as verified.

The workers below use separate connections, so only the row locks under test
serialise them.
"""

from __future__ import annotations

import re
import threading
from typing import Any
from uuid import UUID

import pytest
from django.core import mail
from django.db import connections
from django.test import Client, override_settings
from django.utils import timezone

from apps.accounts import views as accounts_views
from apps.accounts.models import AccountToken, EmailAddress, User
from apps.accounts.services.email import password_reset_token_valid
from apps.accounts.services.rate_limit import ALLOWED
from apps.accounts.services.registration import register_user
from apps.accounts.services.tokens import find_token, issue_token

OLD_PASSWORD = "correct horse battery staple"
OLD_EMAIL = "race-old@example.com"
NEW_EMAIL = "race-new@example.com"

RESET_CONFIRM_PATH = re.compile(r"/en/auth/password-reset/confirm/([^/]+)/")


def _make_user(login: str, *, verified: bool) -> User:
    user = register_user(
        login=login,
        password=OLD_PASSWORD,
        nickname="Racer",
        email=OLD_EMAIL,
        age_confirmed=True,
        terms_accepted=True,
        privacy_accepted=True,
    )
    if verified:
        EmailAddress.objects.filter(user=user).update(verified_at=timezone.now())
    return user


def _verify_token(user: User) -> str:
    return issue_token(
        user,
        AccountToken.PURPOSE_EMAIL_VERIFY,
        ttl_seconds=1800,
        email=OLD_EMAIL,
    )


def _email_change_worker(
    user_id: UUID,
    new_email: str,
    result: dict[str, Any],
    client: Client,
) -> None:
    try:
        # Authenticate before the competing request takes the row lock: a
        # ``force_login`` inside this thread updates ``last_login`` and would
        # block on the same User row before the view is reached.
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


def _reset_request_worker(result: dict[str, Any]) -> None:
    try:
        response = Client().post("/en/auth/password-reset/", {"email": OLD_EMAIL})
        result["status"] = response.status_code
    except Exception as exc:  # noqa: BLE001 - surfaced on the test thread
        result["error"] = exc
    finally:
        connections.close_all()


def _verify_worker(token: str, result: dict[str, Any]) -> None:
    try:
        response = Client().get(f"/en/auth/verify-email/{token}/")
        result["status"] = response.status_code
    except Exception as exc:  # noqa: BLE001 - surfaced on the test thread
        result["error"] = exc
    finally:
        connections.close_all()


def _pause_views_invalidate(
    monkeypatch: pytest.MonkeyPatch,
    *,
    purpose: str,
    thread_name: str,
    paused: threading.Event,
    release: threading.Event,
) -> None:
    """Pause ``_update_email`` after the address rewrite, before token updates.

    Pausing inside ``invalidate_tokens`` keeps the surrounding transaction and
    its ``User`` row lock open, which makes the interleaving deterministic
    instead of timing-based.
    """
    real_invalidate = accounts_views.invalidate_tokens

    def invalidate(user: User, token_purpose: str) -> int:
        if (
            token_purpose == purpose
            and threading.current_thread().name == thread_name
            and not paused.is_set()
        ):
            paused.set()
            if not release.wait(timeout=30):
                raise AssertionError("test never released the paused transaction")
        return real_invalidate(user, token_purpose)

    monkeypatch.setattr(accounts_views, "invalidate_tokens", invalidate)


@pytest.mark.django_db(transaction=True)
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_reset_request_first_invalidates_token_after_email_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reset issued before the change is invalidated when the change commits."""
    mail.outbox.clear()
    user = _make_user("race_reset_request_first", verified=True)
    monkeypatch.setattr(accounts_views, "password_reset_attempt", lambda email, ip: ALLOWED)

    reset_paused = threading.Event()
    release_reset = threading.Event()
    change_entered = threading.Event()

    real_prepare = accounts_views.prepare_password_reset_email

    def prepare_password_reset_email(user: User, target: EmailAddress) -> Any:
        delivery = real_prepare(user, target)
        if threading.current_thread().name == "reset-request" and not reset_paused.is_set():
            # The User row lock is still held by the surrounding transaction;
            # SMTP delivery is deferred until after that transaction commits.
            reset_paused.set()
            if not release_reset.wait(timeout=30):
                raise AssertionError("test never released the paused reset request")
        return delivery

    monkeypatch.setattr(
        accounts_views,
        "prepare_password_reset_email",
        prepare_password_reset_email,
    )

    real_update_email = accounts_views._update_email

    def update_email(request: Any, locked: User, value: str) -> None:
        change_entered.set()
        real_update_email(request, locked, value)

    monkeypatch.setattr(accounts_views, "_update_email", update_email)

    change_client = Client()
    change_client.force_login(user)
    reset_result: dict[str, Any] = {}
    change_result: dict[str, Any] = {}

    reset_thread = threading.Thread(
        target=_reset_request_worker,
        args=(reset_result,),
        name="reset-request",
    )
    change_thread = threading.Thread(
        target=_email_change_worker,
        args=(user.pk, NEW_EMAIL, change_result, change_client),
        name="email-change",
    )
    reset_thread.start()
    change_started = False
    try:
        assert reset_paused.wait(timeout=15), "reset request never took the User lock"
        change_thread.start()
        change_started = True
        assert change_entered.wait(timeout=15), "email change never reached _update_email"
        change_thread.join(timeout=0.5)
        blocked = change_thread.is_alive()
    finally:
        release_reset.set()
        reset_thread.join(timeout=30)
        if change_started:
            change_thread.join(timeout=30)

    assert blocked, "email change was not serialized behind the reset request"
    assert not reset_thread.is_alive()
    assert not change_thread.is_alive()
    assert "error" not in reset_result, reset_result.get("error")
    assert "error" not in change_result, change_result.get("error")
    assert reset_result["status"] == 302
    assert change_result["status"] == 302

    user.refresh_from_db()
    assert user.check_password(OLD_PASSWORD) is True

    address = EmailAddress.objects.filter(user=user).first()
    assert address is not None
    assert address.email == NEW_EMAIL
    assert address.verified_at is None

    reset_bodies = [
        message.body for message in mail.outbox if "password-reset/confirm/" in message.body
    ]
    assert len(reset_bodies) == 1
    match = RESET_CONFIRM_PATH.search(reset_bodies[0])
    assert match is not None
    assert password_reset_token_valid(match.group(1)) is False


@pytest.mark.django_db(transaction=True)
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_email_change_first_prevents_stale_reset_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A committed email change leaves no verified address for a reset request."""
    mail.outbox.clear()
    user = _make_user("race_email_change_first_reset", verified=True)

    reset_attempted = threading.Event()

    def password_reset_attempt(email: str, ip: str | None) -> Any:
        reset_attempted.set()
        return ALLOWED

    monkeypatch.setattr(accounts_views, "password_reset_attempt", password_reset_attempt)

    paused = threading.Event()
    release = threading.Event()
    _pause_views_invalidate(
        monkeypatch,
        purpose=AccountToken.PURPOSE_PASSWORD_RESET,
        thread_name="email-change",
        paused=paused,
        release=release,
    )

    change_client = Client()
    change_client.force_login(user)
    change_result: dict[str, Any] = {}
    reset_result: dict[str, Any] = {}

    change_thread = threading.Thread(
        target=_email_change_worker,
        args=(user.pk, NEW_EMAIL, change_result, change_client),
        name="email-change",
    )
    reset_thread = threading.Thread(
        target=_reset_request_worker,
        args=(reset_result,),
        name="reset-request",
    )
    change_thread.start()
    reset_started = False
    try:
        assert paused.wait(timeout=15), "email change never reached token invalidation"
        reset_thread.start()
        reset_started = True
        assert reset_attempted.wait(timeout=15), "reset request never reached the rate limiter"
        reset_thread.join(timeout=0.5)
        blocked = reset_thread.is_alive()
    finally:
        release.set()
        change_thread.join(timeout=30)
        if reset_started:
            reset_thread.join(timeout=30)

    assert blocked, "reset request was not serialized behind the email change"
    assert not change_thread.is_alive()
    assert not reset_thread.is_alive()
    assert "error" not in change_result, change_result.get("error")
    assert "error" not in reset_result, reset_result.get("error")
    assert change_result["status"] == 302
    assert reset_result["status"] == 302

    assert not any("password-reset/confirm/" in message.body for message in mail.outbox)

    address = EmailAddress.objects.filter(user=user).first()
    assert address is not None
    assert address.email == NEW_EMAIL
    assert address.verified_at is None


@pytest.mark.django_db(transaction=True)
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_verify_first_marks_only_the_current_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A verification that wins the lock completes before the email change."""
    mail.outbox.clear()
    user = _make_user("race_verify_first", verified=False)
    token = _verify_token(user)

    paused = threading.Event()
    release = threading.Event()
    change_entered = threading.Event()
    verified: dict[str, Any] = {}

    real_verify = accounts_views.verify_email_token

    def verify_email_token(raw: str) -> EmailAddress | None:
        result = real_verify(raw)
        if threading.current_thread().name == "verify-email" and not paused.is_set():
            verified["email"] = result.email if result is not None else None
            # The view's transaction, and its User row lock, are still open.
            paused.set()
            if not release.wait(timeout=30):
                raise AssertionError("test never released the paused verify")
        return result

    monkeypatch.setattr(accounts_views, "verify_email_token", verify_email_token)

    real_update_email = accounts_views._update_email

    def update_email(request: Any, locked: User, value: str) -> None:
        change_entered.set()
        real_update_email(request, locked, value)

    monkeypatch.setattr(accounts_views, "_update_email", update_email)

    change_client = Client()
    change_client.force_login(user)
    verify_result: dict[str, Any] = {}
    change_result: dict[str, Any] = {}

    verify_thread = threading.Thread(
        target=_verify_worker,
        args=(token, verify_result),
        name="verify-email",
    )
    change_thread = threading.Thread(
        target=_email_change_worker,
        args=(user.pk, NEW_EMAIL, change_result, change_client),
        name="email-change",
    )
    verify_thread.start()
    change_started = False
    try:
        assert paused.wait(timeout=15), "verify never took the User lock"
        change_thread.start()
        change_started = True
        assert change_entered.wait(timeout=15), "email change never reached _update_email"
        change_thread.join(timeout=0.5)
        blocked = change_thread.is_alive()
    finally:
        release.set()
        verify_thread.join(timeout=30)
        if change_started:
            change_thread.join(timeout=30)

    assert blocked, "email change was not serialized behind verify"
    assert not verify_thread.is_alive()
    assert not change_thread.is_alive()
    assert "error" not in verify_result, verify_result.get("error")
    assert "error" not in change_result, change_result.get("error")
    assert verify_result["status"] == 302
    assert change_result["status"] == 302
    assert verified["email"] == OLD_EMAIL

    address = EmailAddress.objects.filter(user=user).first()
    assert address is not None
    assert address.email == NEW_EMAIL
    assert address.verified_at is None


@pytest.mark.django_db(transaction=True)
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_email_change_first_blocks_stale_verify(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A verification that loses the lock must not verify the changed address."""
    mail.outbox.clear()
    user = _make_user("race_email_change_first_verify", verified=False)
    token = _verify_token(user)

    paused = threading.Event()
    release = threading.Event()
    _pause_views_invalidate(
        monkeypatch,
        purpose=AccountToken.PURPOSE_EMAIL_VERIFY,
        thread_name="email-change",
        paused=paused,
        release=release,
    )

    verify_entered = threading.Event()
    verified: dict[str, Any] = {}
    real_verify = accounts_views.verify_email_token

    def verify_email_token(raw: str) -> EmailAddress | None:
        verify_entered.set()
        result = real_verify(raw)
        verified["email"] = result.email if result is not None else None
        return result

    monkeypatch.setattr(accounts_views, "verify_email_token", verify_email_token)

    change_client = Client()
    change_client.force_login(user)
    verify_result: dict[str, Any] = {}
    change_result: dict[str, Any] = {}

    change_thread = threading.Thread(
        target=_email_change_worker,
        args=(user.pk, NEW_EMAIL, change_result, change_client),
        name="email-change",
    )
    verify_thread = threading.Thread(
        target=_verify_worker,
        args=(token, verify_result),
        name="verify-email",
    )
    change_thread.start()
    verify_started = False
    try:
        assert paused.wait(timeout=15), "email change never reached verify-token invalidation"
        verify_thread.start()
        verify_started = True
        assert verify_entered.wait(timeout=15), "verify never entered the service"
        verify_thread.join(timeout=0.5)
        blocked = verify_thread.is_alive()
    finally:
        release.set()
        change_thread.join(timeout=30)
        if verify_started:
            verify_thread.join(timeout=30)

    assert blocked, "verify was not serialized behind the email change"
    assert not change_thread.is_alive()
    assert not verify_thread.is_alive()
    assert "error" not in change_result, change_result.get("error")
    assert "error" not in verify_result, verify_result.get("error")
    assert change_result["status"] == 302
    assert verify_result["status"] == 302
    assert verified["email"] is None

    address = EmailAddress.objects.filter(user=user).first()
    assert address is not None
    assert address.email == NEW_EMAIL
    assert address.verified_at is None

    assert find_token(token, AccountToken.PURPOSE_EMAIL_VERIFY) is None


@pytest.mark.django_db(transaction=True)
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_delayed_smtp_does_not_hold_user_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The email is sent after commit, so SMTP latency cannot serialize email change."""
    mail.outbox.clear()
    user = _make_user("race_smtp_delay", verified=True)
    monkeypatch.setattr(accounts_views, "password_reset_attempt", lambda email, ip: ALLOWED)

    send_started = threading.Event()
    release_send = threading.Event()
    change_entered = threading.Event()
    real_send = accounts_views.send_password_reset_email

    def send_wrapper(delivery: object, request: object) -> None:
        send_started.set()
        if not release_send.wait(timeout=30):
            raise AssertionError("test never released SMTP delivery")
        real_send(delivery, request)  # type: ignore[arg-type]

    monkeypatch.setattr(accounts_views, "send_password_reset_email", send_wrapper)

    real_update_email = accounts_views._update_email

    def update_email(request: object, locked: User, value: str) -> None:
        change_entered.set()
        real_update_email(request, locked, value)  # type: ignore[arg-type]

    monkeypatch.setattr(accounts_views, "_update_email", update_email)

    change_client = Client()
    change_client.force_login(user)
    reset_result: dict[str, Any] = {}
    change_result: dict[str, Any] = {}
    reset_thread = threading.Thread(
        target=_reset_request_worker,
        args=(reset_result,),
        name="reset-request",
    )
    change_thread = threading.Thread(
        target=_email_change_worker,
        args=(user.pk, NEW_EMAIL, change_result, change_client),
        name="email-change",
    )
    reset_thread.start()
    change_started = False
    try:
        assert send_started.wait(timeout=15), "reset request never reached SMTP delivery"
        change_thread.start()
        change_started = True
        assert change_entered.wait(timeout=15), "email change never entered _update_email"
        change_thread.join(timeout=15)
        assert not change_thread.is_alive(), "SMTP latency held the User lock"
    finally:
        release_send.set()
        reset_thread.join(timeout=30)
        if change_started:
            change_thread.join(timeout=30)

    assert not reset_thread.is_alive()
    assert "error" not in reset_result, reset_result.get("error")
    assert "error" not in change_result, change_result.get("error")
    assert reset_result["status"] == 302
    assert change_result["status"] == 302
    address = EmailAddress.objects.filter(user=user).first()
    assert address is not None
    assert address.email == NEW_EMAIL
    reset_tokens = [
        message.body for message in mail.outbox if "password-reset/confirm/" in message.body
    ]
    assert len(reset_tokens) == 1
    match = RESET_CONFIRM_PATH.search(reset_tokens[0])
    assert match is not None
    assert password_reset_token_valid(match.group(1)) is False


@pytest.mark.django_db(transaction=True)
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_smtp_failure_after_commit_does_not_500_or_claim_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A committed token survives SMTP failure without a false success message."""
    mail.outbox.clear()
    user = _make_user("race_smtp_failure", verified=True)
    old_raw = issue_token(
        user,
        AccountToken.PURPOSE_PASSWORD_RESET,
        ttl_seconds=1800,
        email=OLD_EMAIL,
    )
    monkeypatch.setattr(accounts_views, "password_reset_attempt", lambda email, ip: ALLOWED)
    monkeypatch.setattr(
        accounts_views,
        "send_password_reset_email",
        lambda delivery, request: (_ for _ in ()).throw(RuntimeError("smtp down")),
    )

    response = Client().post("/en/auth/password-reset/", {"email": OLD_EMAIL}, follow=True)

    assert response.status_code == 200
    assert not any("письмо отправлено" in text for text in response.content.decode().splitlines())
    assert password_reset_token_valid(old_raw) is False
    assert (
        AccountToken.objects.filter(
            user=user,
            purpose=AccountToken.PURPOSE_PASSWORD_RESET,
            used_at__isnull=True,
        ).count()
        == 1
    )
