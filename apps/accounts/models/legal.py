from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7
from apps.core.ids import uuid7


class UserLegalAcceptance(models.Model):
    """Фиксация принятой версии документов; текст документов ведётся отдельно."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="legal_acceptances",
    )
    terms_version = models.CharField(max_length=64)
    privacy_version = models.CharField(max_length=64)
    accepted_at = models.DateTimeField(auto_now_add=True)
    ip_hash = models.CharField(max_length=64, blank=True)

    class Meta:
        db_table = "accounts_legal_acceptance"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "terms_version", "privacy_version"],
                name="uq_legal_user_versions",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.terms_version}/{self.privacy_version}"
