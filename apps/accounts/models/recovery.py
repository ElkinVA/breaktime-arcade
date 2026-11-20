from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7, CitextField
from apps.core.ids import uuid7


class AccountToken(models.Model):
    """Одноразовые токены подтверждения email и восстановления пароля."""

    PURPOSE_EMAIL_VERIFY = "email_verify"
    PURPOSE_PASSWORD_RESET = "password_reset"  # noqa: S105
    PURPOSE_CHOICES = [
        (PURPOSE_EMAIL_VERIFY, "Подтверждение email"),
        (PURPOSE_PASSWORD_RESET, "Восстановление пароля"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="account_tokens",
    )
    purpose = models.CharField(max_length=32, choices=PURPOSE_CHOICES)
    email = CitextField(max_length=254, blank=True)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounts_account_token"
        indexes = [
            models.Index(
                fields=["user", "purpose", "used_at"],
                name="ix_token_user_purpose",
            )
        ]

    def __str__(self) -> str:
        return f"{self.purpose}:{self.user_id}"
