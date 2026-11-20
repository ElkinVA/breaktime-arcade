from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.accounts.models import (
    AccountToken,
    AnonymousIdentity,
    LoginEvent,
    NicknameReservation,
    UserProfile,
)
from celery import shared_task


@shared_task
def cleanup_expired_account_records() -> dict[str, int]:
    """Удаляет записи по срокам §2.22: гости, токены, журнал, резервы."""
    now = timezone.now()
    expired_guests, _ = AnonymousIdentity.objects.filter(expires_at__lt=now).delete()
    expired_tokens, _ = AccountToken.objects.filter(expires_at__lt=now).delete()
    old_events, _ = LoginEvent.objects.filter(
        created_at__lt=now - timedelta(days=settings.LOGIN_EVENT_RETENTION_DAYS)
    ).delete()
    expired_reservations, _ = NicknameReservation.objects.filter(reserved_until__lt=now).delete()
    return {
        "anonymous_identities": expired_guests,
        "account_tokens": expired_tokens,
        "login_events": old_events,
        "nickname_reservations": expired_reservations,
    }


@shared_task
def anonymize_due_accounts() -> int:
    """Анонимизирует аккаунты после 7-дневного окна отмены."""
    cutoff = timezone.now() - timedelta(days=settings.ACCOUNT_DELETION_WINDOW_DAYS)
    due = list(
        UserProfile.objects.filter(
            deletion_requested_at__lte=cutoff,
            deleted_at__isnull=True,
        ).select_related("user")
    )
    for profile in due:
        from apps.accounts.services.profile import anonymize_user

        anonymize_user(profile.user)
    return len(due)
