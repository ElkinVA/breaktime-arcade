from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7, CitextField
from apps.core.ids import uuid7


class NicknameHistory(models.Model):
    """История никнеймов; старые значения сохраняются для аудита."""

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="nickname_history",
    )
    nickname = CitextField(max_length=20, null=True, blank=True)  # type: ignore[misc]
    nickname_skeleton = models.CharField(max_length=64)
    valid_from = models.DateTimeField(auto_now_add=True)
    valid_to = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "accounts_nickname_history"
        ordering = ["-valid_from"]
        indexes = [models.Index(fields=["user", "valid_from"], name="ix_nickname_user_valid")]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.nickname_skeleton}"


class NicknameReservation(models.Model):
    """HMAC скелетона после удаления; без FK и без plaintext."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    skeleton_hmac = models.CharField(max_length=64, unique=True)
    reserved_until = models.DateTimeField()
    reason = models.CharField(max_length=64, default="account_deleted")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounts_nickname_reservation"

    def __str__(self) -> str:
        return self.skeleton_hmac
