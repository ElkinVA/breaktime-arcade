"""Кабинет: настройки, смена никнейма, запрос удаления."""

from __future__ import annotations

import hashlib
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import (
    AccountToken,
    EmailAddress,
    NicknameHistory,
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
    if timezone.now() - requested > timedelta(days=settings.ACCOUNT_DELETION_WINDOW_DAYS):
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

    # DB-001: anonymise results, remove leaderboard rows in the same flow.
    from apps.gameplay.models import UserGamePlaytime
    from apps.gameplay.services.results import anonymize_user_results
    from apps.gameplay.services.storage import delete_user_storage

    anonymize_user_results(user)
    delete_user_storage(user)
    UserGamePlaytime.objects.filter(user=user).delete()

    user.is_active = False
    user.login = f"deleted-{hashlib.sha256(str(user.pk).encode()).hexdigest()[:20]}"
    user.save(update_fields=["is_active", "login"])


def nickname_change_available(user: User) -> bool:
    profile = UserProfile.objects.filter(user=user).first()
    return profile is not None and can_change_nickname(profile)


def validate_nickname_for_user(user: User, nickname: str) -> str:
    normalized = normalize_nickname(nickname)
    skeleton = nickname_skeleton(normalized)
    if UserProfile.objects.filter(nickname_skeleton=skeleton).exclude(user=user).exists():
        raise ValidationError("Этот никнейм уже занят.")
    return normalized
