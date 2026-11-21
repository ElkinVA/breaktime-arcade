from __future__ import annotations

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models

from apps.core.fields import UUID7, CitextField
from apps.core.ids import uuid7


class GameTranslation(models.Model):
    """Локализованные данные игры."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    game = models.ForeignKey(
        "catalog.Game",
        on_delete=models.CASCADE,
        related_name="translations",
    )
    language = models.ForeignKey(
        "i18n.Language",
        on_delete=models.CASCADE,
        related_name="game_translations",
    )
    name = models.CharField(max_length=60)
    slug = CitextField(max_length=128, help_text="Уникален в рамках языка")
    short_description = models.CharField(max_length=160)
    description = models.TextField(max_length=1600)
    instructions = models.TextField(max_length=600, blank=True)
    controls = models.TextField(max_length=400, blank=True)
    seo_title = models.CharField(max_length=60, blank=True)
    seo_description = models.CharField(max_length=160, blank=True)
    search_vector = SearchVectorField(null=True, blank=True)
    overridden_fields = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "catalog_game_translation"
        unique_together = [("game", "language"), ("slug", "language")]
        indexes = [GinIndex(fields=["search_vector"])]
        verbose_name = "Перевод игры"
        verbose_name_plural = "Переводы игр"

    def __str__(self) -> str:
        return f"{self.game} [{self.language.code}] {self.name}"
