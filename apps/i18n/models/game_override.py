from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7, CitextField
from apps.core.ids import uuid7


class GameLocaleOverride(models.Model):
    """Переопределение строки игры из CRM. Приоритетнее пакета."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    game = models.ForeignKey(
        "catalog.Game",
        on_delete=models.CASCADE,
        related_name="locale_overrides",
    )
    language = models.ForeignKey(
        "i18n.Language",
        on_delete=models.CASCADE,
        related_name="game_overrides",
    )
    key = CitextField(max_length=128)
    value = models.TextField()
    status = models.CharField(max_length=16, default="published")
    updated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "i18n_game_locale_override"
        unique_together = [("game", "language", "key")]
        verbose_name = "Переопределение локали игры"
        verbose_name_plural = "Переопределения локалей игр"

    def __str__(self) -> str:
        return f"{self.game} [{self.language.code}] {self.key}"
