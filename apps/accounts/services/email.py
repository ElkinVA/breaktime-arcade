"""Подтверждение email и нейтральное восстановление пароля."""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.core.mail import send_mail
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import AccountToken, EmailAddress, User
from apps.accounts.services.tokens import (
    consume_token,
    find_token,
    invalidate_tokens,
    issue_token,
)


def send_verification_email(user: User, request: HttpRequest) -> None:
    email = EmailAddress.objects.filter(user=user).first()
    if email is None or email.verified_at is not None:
        return
    invalidate_tokens(user, AccountToken.PURPOSE_EMAIL_VERIFY)
    raw = issue_token(
        user,
        AccountToken.PURPOSE_EMAIL_VERIFY,
        ttl_seconds=settings.EMAIL_VERIFICATION_TIMEOUT,
        email=email.email,
    )
    path = reverse("accounts:verify_email", args=[raw])
    url = request.build_absolute_uri(path)
    send_mail(
        subject="Confirm your Breaktime Arcade email",
        message=f"Confirm your email: {url}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email.email],
        fail_silently=False,
    )


def verify_email_token(raw: str) -> EmailAddress | None:
    # ARCADE-EMAIL-VERIFY-RESET-RACE-001: take the same User row lock as
    # ``_update_email``/``password_reset_confirm`` before consuming the token
    # or touching EmailAddress. A concurrent email change then linearizes:
    # the link is only honoured while the address it was issued for is still
    # current, so a change cannot leave the new address marked as verified.
    pending = find_token(raw, AccountToken.PURPOSE_EMAIL_VERIFY)
    if pending is None:
        return None
    user = User.objects.select_for_update().filter(pk=pending.user_id).first()
    if user is None:
        return None
    token = consume_token(raw, AccountToken.PURPOSE_EMAIL_VERIFY)
    if token is None or token.user_id != user.pk:
        return None
    email = EmailAddress.objects.filter(user_id=user.pk).first()
    if email is None or email.email.casefold() != token.email.casefold():
        return None
    if email.verified_at is None:
        email.verified_at = timezone.now()
        email.save(update_fields=["verified_at", "updated_at"])
    return email


@dataclass(frozen=True)
class PasswordResetDelivery:
    """Token data snapshotted under the User lock for post-commit delivery."""

    recipient: str
    raw_token: str


def prepare_password_reset_email(
    user: User,
    email: EmailAddress,
) -> PasswordResetDelivery:
    """Invalidate old tokens and issue a reset token while the caller holds the lock.

    This function deliberately performs no I/O outside the database. The
    caller must invoke it inside the transaction that holds the User row lock,
    then pass the returned immutable snapshot to
    :func:`send_password_reset_email` only after that transaction commits.
    """
    invalidate_tokens(user, AccountToken.PURPOSE_PASSWORD_RESET)
    raw = issue_token(
        user,
        AccountToken.PURPOSE_PASSWORD_RESET,
        ttl_seconds=settings.PASSWORD_RESET_TIMEOUT,
        email=email.email,
    )
    return PasswordResetDelivery(recipient=email.email, raw_token=raw)


def send_password_reset_email(delivery: PasswordResetDelivery, request: HttpRequest) -> None:
    """Deliver an already-created reset token; never touches the User lock."""
    path = reverse("accounts:password_reset_confirm", args=[delivery.raw_token])
    url = request.build_absolute_uri(path)
    send_mail(
        subject="Reset your Breaktime Arcade password",
        message=f"Reset your password: {url}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[delivery.recipient],
        fail_silently=False,
    )


def send_2fa_change_notice(user: User, *, enabled: bool) -> None:
    email = EmailAddress.objects.filter(user=user, verified_at__isnull=False).first()
    if email is None:
        return
    action = "enabled" if enabled else "disabled"
    send_mail(
        subject=f"Breaktime Arcade: two-factor authentication {action}",
        message=(
            f"Two-factor authentication was {action} for your account. "
            "If it was not you, contact support immediately."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email.email],
        fail_silently=True,
    )


def send_email_change_notice(old_email: str, request: HttpRequest) -> None:
    """Notify the previous (verified) address after a committed change.

    The caller snapshots the old address while holding the account row lock
    and invokes this after the transaction commits, so no mail is sent while
    the lock is held.
    """
    send_mail(
        subject="Your Breaktime Arcade email was changed",
        message="A new email was added to your account. If it was not you, contact support.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[old_email],
        fail_silently=True,
    )


def find_verified_email(value: str) -> EmailAddress | None:
    return EmailAddress.objects.filter(
        email__iexact=value.strip(),
        verified_at__isnull=False,
    ).first()


def password_reset_token_valid(raw: str) -> bool:
    token = find_token(raw, AccountToken.PURPOSE_PASSWORD_RESET)
    return token is not None and token.user.is_active


def password_reset_token_user(raw: str) -> User | None:
    token = find_token(raw, AccountToken.PURPOSE_PASSWORD_RESET)
    if token is None or not token.user.is_active:
        return None
    return token.user
