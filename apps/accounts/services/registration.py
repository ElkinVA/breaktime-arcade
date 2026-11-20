"""Создание аккаунта и профиля в одной транзакции."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounts.models import (
    EmailAddress,
    NicknameHistory,
    User,
    UserLegalAcceptance,
    UserProfile,
)
from apps.accounts.services.nickname import nickname_skeleton, normalize_nickname
from apps.i18n.models import Language


def _ip_hash(ip: str | None) -> str:
    if not ip:
        return ""
    return hashlib.sha256(ip.encode()).hexdigest()


@transaction.atomic
def register_user(
    *,
    login: str,
    password: str,
    nickname: str,
    email: str = "",
    language_code: str = "en",
    age_confirmed: bool,
    terms_accepted: bool,
    privacy_accepted: bool,
    marketing_consent: bool = False,
    ip: str | None = None,
) -> User:
    if not age_confirmed:
        raise ValidationError("Требуется подтверждение возраста 16+.")
    if not terms_accepted or not privacy_accepted:
        raise ValidationError("Требуется принять условия и политику.")

    normalized = normalize_nickname(nickname)
    skeleton = nickname_skeleton(normalized)
    login = login.strip().lower()
    email = email.strip().lower()

    if UserProfile.objects.filter(nickname_skeleton=skeleton).exists():
        raise ValidationError("Этот никнейм уже занят.")
    if email and EmailAddress.objects.filter(email__iexact=email).exists():
        raise ValidationError("Этот email уже используется.")

    user = User.objects.create_user(login=login, password=password)
    language = Language.objects.filter(code=language_code, is_active=True).first()
    now = datetime.now(UTC)
    UserProfile.objects.create(
        user=user,
        nickname=normalized,
        nickname_skeleton=skeleton,
        language=language,
        age_confirmed_at=now if age_confirmed else None,
        marketing_consent_at=now if marketing_consent else None,
    )
    NicknameHistory.objects.create(
        user=user,
        nickname=normalized,
        nickname_skeleton=skeleton,
    )
    if email:
        EmailAddress.objects.create(user=user, email=email)
    UserLegalAcceptance.objects.create(
        user=user,
        terms_version=settings.TERMS_VERSION,
        privacy_version=settings.PRIVACY_VERSION,
        ip_hash=_ip_hash(ip),
    )
    return user


def ensure_profile(user: User) -> UserProfile:
    """Для служебных/старых пользователей, созданных до профиля."""
    profile = UserProfile.objects.filter(user=user).first()
    if profile is not None:
        return profile
    nickname = (user.login or "player")[:20]
    while len(nickname) < 3:
        nickname += "0"
    base = nickname
    index = 1
    while True:
        candidate = nickname if index == 1 else f"{base[:17]}{index:02d}"[:20]
        skeleton = nickname_skeleton(candidate)
        if not UserProfile.objects.filter(nickname_skeleton=skeleton).exists():
            break
        index += 1
    return UserProfile.objects.create(
        user=user,
        nickname=candidate,
        nickname_skeleton=skeleton,
    )
