from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import (
    AccountToken,
    AnonymousIdentity,
    LoginEvent,
    NicknameReservation,
    User,
)
from apps.accounts.tasks import cleanup_expired_account_records


@pytest.mark.django_db
def test_cleanup_removes_only_expired_records() -> None:
    now = timezone.now()
    user = User.objects.create_user(login="keeper", password="correct horse battery staple")
    expired_guest = AnonymousIdentity.objects.create(
        token_hash="expired",
        expires_at=now - timedelta(days=1),
    )
    future_guest = AnonymousIdentity.objects.create(
        token_hash="future",
        expires_at=now + timedelta(days=1),
    )
    expired_token = AccountToken.objects.create(
        user=user,
        purpose=AccountToken.PURPOSE_EMAIL_VERIFY,
        token_hash="expired-token",
        expires_at=now - timedelta(days=1),
    )
    future_token = AccountToken.objects.create(
        user=user,
        purpose=AccountToken.PURPOSE_EMAIL_VERIFY,
        token_hash="future-token",
        expires_at=now + timedelta(days=1),
    )
    old_event = LoginEvent.objects.create(
        user=user,
        event=LoginEvent.EVENT_LOGIN_SUCCESS,
    )
    LoginEvent.objects.filter(pk=old_event.pk).update(created_at=now - timedelta(days=400))
    fresh_event = LoginEvent.objects.create(
        user=user,
        event=LoginEvent.EVENT_LOGIN_SUCCESS,
    )
    expired_reservation = NicknameReservation.objects.create(
        skeleton_hmac="expired-reservation",
        reserved_until=now - timedelta(days=1),
    )
    future_reservation = NicknameReservation.objects.create(
        skeleton_hmac="future-reservation",
        reserved_until=now + timedelta(days=1),
    )

    result = cleanup_expired_account_records()

    assert result["anonymous_identities"] == 1
    assert result["account_tokens"] == 1
    assert result["login_events"] == 1
    assert result["nickname_reservations"] == 1
    assert not AnonymousIdentity.objects.filter(pk=expired_guest.pk).exists()
    assert AnonymousIdentity.objects.filter(pk=future_guest.pk).exists()
    assert not AccountToken.objects.filter(pk=expired_token.pk).exists()
    assert AccountToken.objects.filter(pk=future_token.pk).exists()
    assert not LoginEvent.objects.filter(pk=old_event.pk).exists()
    assert LoginEvent.objects.filter(pk=fresh_event.pk).exists()
    assert not NicknameReservation.objects.filter(pk=expired_reservation.pk).exists()
    assert NicknameReservation.objects.filter(pk=future_reservation.pk).exists()
