from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7
from apps.core.ids import uuid7


class RecoveryCode(models.Model):
    """Одноразовый резервный код 2FA; в БД хранится только hash."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="recovery_codes",
    )
    code_hash = models.CharField(max_length=64)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounts_recovery_code"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "code_hash"],
                name="uq_recovery_user_hash",
            )
        ]
        indexes = [
            models.Index(fields=["user", "used_at"], name="ix_recovery_user_used"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{'used' if self.used_at else 'unused'}"


class OwnerRecoveryCode(models.Model):
    """Офлайн-код владельца; хранится только hash и используется один раз."""

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="owner_recovery_code",
    )
    code_hash = models.CharField(max_length=64)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounts_owner_recovery_code"

    def __str__(self) -> str:
        return f"{self.user_id}:{'used' if self.used_at else 'unused'}"


class LoginEvent(models.Model):
    """Журнал входов/2FA без plaintext login/IP."""

    EVENT_LOGIN_FAILED = "login_failed"
    EVENT_LOGIN_SUCCESS = "login_success"
    EVENT_PASSWORD_OK = "password_ok"  # noqa: S105
    EVENT_2FA_SUCCESS = "2fa_success"
    EVENT_2FA_FAILED = "2fa_failed"
    EVENT_RECOVERY_USED = "recovery_used"
    EVENT_OWNER_RECOVERY_USED = "owner_recovery_used"
    EVENT_2FA_ENABLED = "2fa_enabled"
    EVENT_2FA_DISABLED = "2fa_disabled"
    EVENT_CHOICES = [
        (EVENT_LOGIN_FAILED, "Неудачный вход"),
        (EVENT_LOGIN_SUCCESS, "Успешный вход"),
        (EVENT_PASSWORD_OK, "Пароль подтверждён"),
        (EVENT_2FA_SUCCESS, "2FA подтверждена"),
        (EVENT_2FA_FAILED, "Неудачная 2FA"),
        (EVENT_RECOVERY_USED, "Использован recovery-код"),
        (EVENT_OWNER_RECOVERY_USED, "Использован owner recovery-код"),
        (EVENT_2FA_ENABLED, "2FA включена"),
        (EVENT_2FA_DISABLED, "2FA отключена"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="login_events",
    )
    subject_hash = models.CharField(max_length=64, blank=True)
    event = models.CharField(max_length=32, choices=EVENT_CHOICES)
    ip_hash = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounts_login_event"
        indexes = [
            models.Index(fields=["user", "created_at"], name="ix_login_event_user"),
            models.Index(fields=["event", "created_at"], name="ix_login_event_type"),
        ]

    def __str__(self) -> str:
        return f"{self.event}:{self.user_id or self.subject_hash}"
