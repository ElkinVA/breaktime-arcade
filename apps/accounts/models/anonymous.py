from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7
from apps.core.ids import uuid7


class AnonymousIdentity(models.Model):
    """Серверная запись гостя; cookie содержит подписанный токен, не id."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "accounts_anonymous_identity"
        indexes = [models.Index(fields=["expires_at"], name="ix_anonymous_expiry")]

    def __str__(self) -> str:
        return str(self.id)
