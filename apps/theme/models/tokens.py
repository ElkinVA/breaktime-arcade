from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7
from apps.core.ids import uuid7


class ThemeTokenSet(models.Model):
    """Набор дизайн-токенов из CRM. Генерирует /theme-<hash>.css (§2.7)."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    version = models.PositiveIntegerField(default=1)
    tokens = models.JSONField(help_text="CSS-переменные: {--ba-bg: '#0f1115', ...}")
    hash = models.CharField(max_length=16, unique=True, db_index=True)
    is_active = models.BooleanField(default=False)
    updated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "theme_token_set"
        verbose_name = "Набор токенов темы"
        verbose_name_plural = "Наборы токенов темы"

    def __str__(self) -> str:
        return f"Theme v{self.version} ({self.hash})"
