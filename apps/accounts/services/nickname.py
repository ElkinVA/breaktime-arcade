"""Нормализация никнейма и confusables-скелетон (§2.10.2)."""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import re
import unicodedata
from datetime import datetime
from uuid import UUID

from confusable_homoglyphs import confusables
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.accounts.models import NicknameHistory, NicknameReservation, User, UserProfile

NICKNAME_RE = re.compile(r"^[\w]+(?: [\w]+)*$", re.UNICODE)


def normalize_nickname(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip()
    if not 3 <= len(value) <= 20:
        raise ValidationError("Никнейм должен содержать от 3 до 20 символов.")
    if not NICKNAME_RE.fullmatch(value):
        raise ValidationError("Никнейм: буквы/цифры/_, одиночные пробелы, без краёв.")
    return value


def _confusable_ascii(char: str) -> str | None:
    for entry in confusables.is_confusable(char):
        for homoglyph in entry.get("homoglyphs", []):
            candidate = str(homoglyph.get("c", ""))
            if len(candidate) == 1 and candidate.isascii() and candidate.isalnum():
                return candidate.casefold()
    return None


def nickname_skeleton(value: str) -> str:
    """NFKC → casefold → стабильное ASCII-представление confusables."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    result: list[str] = []
    for char in normalized:
        if char.isascii():
            result.append(char)
            continue
        replacement = _confusable_ascii(char)
        if replacement is not None:
            result.append(replacement)
            continue
        fallback = (
            unicodedata.normalize("NFKD", char).encode("ascii", "ignore").decode("ascii").casefold()
        )
        result.append(fallback or char)
    return "".join(result)


def nickname_hmac(skeleton: str) -> str:
    key = (settings.NICKNAME_HMAC_KEY or settings.SECRET_KEY or "").encode()
    return hmac.new(key, skeleton.encode(), hashlib.sha256).hexdigest()


def nickname_available(
    nickname: str,
    *,
    exclude_user_id: UUID | str | None = None,
) -> bool:
    skeleton = nickname_skeleton(normalize_nickname(nickname))
    query = UserProfile.objects.filter(nickname_skeleton=skeleton)
    if exclude_user_id is not None:
        query = query.exclude(user_id=exclude_user_id)
    return not query.exists()


@transaction.atomic
def change_nickname(user: User, nickname: str) -> UserProfile:
    """Меняет никнейм и сохраняет историю; интервал проверяет вызывающий слой."""
    profile = UserProfile.objects.select_for_update().get(user=user)
    new_nickname = normalize_nickname(nickname)
    new_skeleton = nickname_skeleton(new_nickname)
    if new_skeleton != profile.nickname_skeleton:
        if UserProfile.objects.filter(nickname_skeleton=new_skeleton).exclude(user=user).exists():
            raise ValidationError("Этот никнейм уже занят.")
        NicknameHistory.objects.create(
            user=user,
            nickname=profile.nickname,
            nickname_skeleton=profile.nickname_skeleton,
        )
        profile.nickname = new_nickname
        profile.nickname_skeleton = new_skeleton
        profile.save(update_fields=["nickname", "nickname_skeleton", "updated_at"])
    return profile


def reserve_nickname(skeleton: str, reserved_until: datetime) -> None:
    with contextlib.suppress(IntegrityError):
        # Повторное удаление/резерв не должен ломать анонимизацию.
        NicknameReservation.objects.create(
            skeleton_hmac=nickname_hmac(skeleton),
            reserved_until=reserved_until,
            reason="account_deleted",
        )
