"""TOTP 2FA персонала: секрет, проверка, recovery-коды (§2.20)."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time

import pyotp
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import OwnerRecoveryCode, RecoveryCode, User

RECOVERY_CODE_COUNT = 10
TOTP_INTERVAL_SECONDS = 30
TOTP_VALID_WINDOW = 1


def generate_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(user: User, secret: str) -> str:
    issuer = getattr(settings, "TOTP_ISSUER", "Breaktime Arcade")
    return pyotp.TOTP(secret).provisioning_uri(name=user.login, issuer_name=issuer)


def _normalize_recovery_code(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _hash_recovery_code(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def generate_recovery_codes(user: User) -> list[str]:
    """Заменяет набор recovery-кодов; plaintext возвращается один раз."""
    RecoveryCode.objects.filter(user=user).delete()
    codes: list[str] = []
    for _ in range(RECOVERY_CODE_COUNT):
        code = secrets.token_hex(5).upper()
        codes.append(code)
        RecoveryCode.objects.create(user=user, code_hash=_hash_recovery_code(code))
    return codes


def generate_owner_recovery_code(user: User) -> str:
    """Создаёт офлайн-код владельца; plaintext возвращается один раз."""
    if not user.is_superuser:
        raise ValueError("owner recovery code is only for superusers")
    raw = secrets.token_hex(8).upper()
    OwnerRecoveryCode.objects.update_or_create(
        user=user,
        defaults={"code_hash": _hash_recovery_code(raw), "used_at": None},
    )
    return raw


def verify_owner_recovery_code(user: User, code: str) -> bool:
    normalized = _normalize_recovery_code(code)
    if len(normalized) < 8:
        return False
    with transaction.atomic():
        stored = (
            OwnerRecoveryCode.objects.select_for_update()
            .filter(user=user, used_at__isnull=True)
            .first()
        )
        if stored is None:
            return False
        if not hmac.compare_digest(stored.code_hash, _hash_recovery_code(normalized)):
            return False
        stored.used_at = timezone.now()
        stored.save(update_fields=["used_at"])
    return True


def enable_totp(user: User, secret: str, code: str) -> list[str]:
    """Подтверждает секрет кодом и включает 2FA; возвращает recovery-коды."""
    if not pyotp.TOTP(secret).verify(code.strip(), valid_window=TOTP_VALID_WINDOW):
        raise ValueError("invalid totp code")
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)
        locked.totp_secret = secret
        locked.totp_confirmed_at = timezone.now()
        locked.totp_last_counter = int(time.time()) // TOTP_INTERVAL_SECONDS
        locked.save(
            update_fields=[
                "totp_secret",
                "totp_confirmed_at",
                "totp_last_counter",
                "updated_at",
            ]
        )
    return generate_recovery_codes(user)


def verify_totp(user: User, code: str) -> bool:
    """Проверяет TOTP с защитой от повторного использования временного окна."""
    candidate = code.strip().replace(" ", "")
    if not candidate.isdigit() or len(candidate) != 6:
        return False
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)
        if not locked.totp_secret or locked.totp_confirmed_at is None:
            return False
        counter = int(time.time()) // TOTP_INTERVAL_SECONDS
        matched: int | None = None
        totp = pyotp.TOTP(locked.totp_secret)
        for offset in (0, -TOTP_VALID_WINDOW, TOTP_VALID_WINDOW):
            candidate_counter = counter + offset
            expected = totp.at(candidate_counter * TOTP_INTERVAL_SECONDS)
            if hmac.compare_digest(expected, candidate):
                matched = candidate_counter
                break
        if matched is None:
            return False
        if locked.totp_last_counter is not None and matched <= locked.totp_last_counter:
            return False
        locked.totp_last_counter = matched
        locked.save(update_fields=["totp_last_counter", "updated_at"])
    user.totp_last_counter = matched
    return True


def verify_recovery_code(user: User, code: str) -> bool:
    normalized = _normalize_recovery_code(code)
    if len(normalized) < 8:
        return False
    digest = _hash_recovery_code(normalized)
    with transaction.atomic():
        recovery = (
            RecoveryCode.objects.select_for_update()
            .filter(user=user, code_hash=digest, used_at__isnull=True)
            .first()
        )
        if recovery is None:
            return False
        recovery.used_at = timezone.now()
        recovery.save(update_fields=["used_at"])
    return True


def disable_totp(user: User) -> None:
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)
        locked.totp_secret = ""
        locked.totp_confirmed_at = None
        locked.totp_last_counter = None
        locked.save(
            update_fields=[
                "totp_secret",
                "totp_confirmed_at",
                "totp_last_counter",
                "updated_at",
            ]
        )
        RecoveryCode.objects.filter(user=user).delete()
        OwnerRecoveryCode.objects.filter(user=user).delete()


def staff_needs_setup(user: User) -> bool:
    return user.is_staff and user.totp_confirmed_at is None
