"""Кабинет: настройки, смена никнейма, запрос удаления."""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Any
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import (
    AccountToken,
    EmailAddress,
    NicknameHistory,
    OwnerRecoveryCode,
    RecoveryCode,
    User,
    UserLegalAcceptance,
    UserProfile,
)
from apps.accounts.services.nickname import (
    change_nickname,
    nickname_skeleton,
    normalize_nickname,
    reserve_nickname,
)
from apps.accounts.services.registration import ensure_profile
from apps.i18n.models import Language

__all__ = [
    "anonymize_user",
    "can_change_nickname",
    "export_account_data",
    "cancel_deletion",
    "ensure_profile",
    "nickname_change_available",
    "request_deletion",
    "update_nickname",
    "update_settings",
    "validate_nickname_for_user",
]


def can_change_nickname(profile: UserProfile) -> bool:
    last = NicknameHistory.objects.filter(user=profile.user).order_by("-valid_from").first()
    if last is None:
        return True
    return timezone.now() - last.valid_from >= timedelta(
        days=settings.NICKNAME_CHANGE_INTERVAL_DAYS
    )


@transaction.atomic
def update_nickname(user: User, nickname: str) -> UserProfile:
    profile = UserProfile.objects.select_for_update().get(user=user)
    if not can_change_nickname(profile):
        raise ValidationError("Никнейм можно менять не чаще одного раза в 30 дней.")
    return change_nickname(user, nickname)


@transaction.atomic
def update_settings(
    user: User,
    *,
    language_code: str | None = None,
    theme: str = "dark",
    marketing_consent: bool = False,
) -> UserProfile:
    profile = UserProfile.objects.select_for_update().get(user=user)
    if language_code:
        language = Language.objects.filter(code=language_code, is_active=True).first()
        if language is not None:
            profile.language = language
    profile.theme = theme
    profile.marketing_consent_at = timezone.now() if marketing_consent else None
    profile.save(update_fields=["language", "theme", "marketing_consent_at", "updated_at"])
    return profile


@transaction.atomic
def request_deletion(user: User) -> UserProfile:
    profile = UserProfile.objects.select_for_update().get(user=user)
    profile.deletion_requested_at = timezone.now()
    profile.save(update_fields=["deletion_requested_at", "updated_at"])
    return profile


@transaction.atomic
def cancel_deletion(user: User) -> UserProfile:
    profile = UserProfile.objects.select_for_update().get(user=user)
    requested = profile.deletion_requested_at
    if requested is None:
        return profile
    if timezone.now() - requested >= timedelta(days=settings.ACCOUNT_DELETION_WINDOW_DAYS):
        raise ValidationError("Окно отмены удаления истекло.")
    profile.deletion_requested_at = None
    profile.save(update_fields=["deletion_requested_at", "updated_at"])
    return profile


@transaction.atomic
def anonymize_user(user: User) -> None:
    """Удаляет активные персональные данные, оставляя HMAC-резерв никнейма."""
    profile = UserProfile.objects.filter(user=user).first()
    if profile is not None:
        reserve_nickname(
            profile.nickname_skeleton,
            timezone.now() + timedelta(days=settings.NICKNAME_RESERVATION_DAYS),
        )
        profile.delete()
    EmailAddress.objects.filter(user=user).delete()
    NicknameHistory.objects.filter(user=user).delete()
    UserLegalAcceptance.objects.filter(user=user).delete()
    AccountToken.objects.filter(user=user).delete()

    # DB-001: tombstone session identity and close open sessions under row
    # locks before anonymising results, so a concurrent submit_result cannot
    # create a fresh result after the result pass has run.
    from apps.gameplay.models import GamePlayCredit, GameSession, UserGamePlaytime
    from apps.gameplay.services.results import anonymize_user_results
    from apps.gameplay.services.storage import delete_user_storage
    from apps.ratings.services.voting import remove_user_ratings

    open_states = {GameSession.STATE_CREATED, GameSession.STATE_ACTIVE}
    for session in (
        GameSession.objects.select_for_update()
        .filter(
            subject_type=GameSession.SUBJECT_USER,
            subject_id=user.id,
        )
        .order_by("pk")
    ):
        session.subject_type = GameSession.SUBJECT_DELETED
        session.subject_id = uuid4()
        update_fields = ["subject_type", "subject_id", "updated_at"]
        if session.state in open_states:
            session.state = GameSession.STATE_ABORTED
            session.ticket_hash = None
            session.ticket_expires_at = None
            session.binding_nonce_hash = ""
            update_fields.extend(
                ["state", "ticket_hash", "ticket_expires_at", "binding_nonce_hash"]
            )
        session.save(update_fields=update_fields)

    anonymize_user_results(user)
    delete_user_storage(user)
    UserGamePlaytime.objects.filter(user=user).delete()
    GamePlayCredit.objects.filter(
        subject_type="user",
        subject_id=user.id,
    ).delete()
    remove_user_ratings(user)

    # R-049: a tombstone must not retain any authenticatable credential —
    # password hash, TOTP secret/counter or recovery codes.
    RecoveryCode.objects.filter(user=user).delete()
    OwnerRecoveryCode.objects.filter(user=user).delete()
    user.set_unusable_password()
    user.totp_secret = ""
    user.totp_confirmed_at = None
    user.totp_last_counter = None
    user.is_active = False
    user.login = f"deleted-{hashlib.sha256(str(user.pk).encode()).hexdigest()[:20]}"
    user.save(
        update_fields=[
            "is_active",
            "login",
            "password",
            "totp_secret",
            "totp_confirmed_at",
            "totp_last_counter",
        ]
    )


def export_account_data(user: User) -> dict[str, Any]:
    """Build the JSON payload used by both cabinet and CRM exports (§2.10.4).

    The shape is deliberately stable: CRM staff must receive exactly the same
    fields as the account owner. Password hashes, TOTP secrets and recovery
    codes are never part of this payload.
    """
    profile_obj = UserProfile.objects.filter(user=user).first()
    email = EmailAddress.objects.filter(user=user).first()
    legal = list(
        UserLegalAcceptance.objects.filter(user=user).values(
            "terms_version", "privacy_version", "accepted_at"
        )
    )
    return {
        "login": user.login,
        "created_at": user.created_at.isoformat(),
        "profile": None
        if profile_obj is None
        else {
            "nickname": profile_obj.nickname,
            "theme": profile_obj.theme,
            "language": profile_obj.language.code
            if profile_obj.language_id and profile_obj.language
            else None,
            "age_confirmed_at": profile_obj.age_confirmed_at.isoformat()
            if profile_obj.age_confirmed_at
            else None,
            "marketing_consent_at": profile_obj.marketing_consent_at.isoformat()
            if profile_obj.marketing_consent_at
            else None,
            "deletion_requested_at": profile_obj.deletion_requested_at.isoformat()
            if profile_obj.deletion_requested_at
            else None,
        },
        "email": None
        if email is None
        else {
            "email": email.email,
            "verified_at": email.verified_at.isoformat() if email.verified_at else None,
        },
        "legal_acceptances": legal,
    }


def nickname_change_available(user: User) -> bool:
    profile = UserProfile.objects.filter(user=user).first()
    return profile is not None and can_change_nickname(profile)


def validate_nickname_for_user(user: User, nickname: str) -> str:
    normalized = normalize_nickname(nickname)
    skeleton = nickname_skeleton(normalized)
    if UserProfile.objects.filter(nickname_skeleton=skeleton).exclude(user=user).exists():
        raise ValidationError("Этот никнейм уже занят.")
    return normalized
