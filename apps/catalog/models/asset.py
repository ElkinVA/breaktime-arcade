from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7
from apps.core.ids import uuid7


class GameAsset(models.Model):
    """Изображение игры: обложка, скриншот."""

    TYPE_COVER = "cover"
    TYPE_SCREENSHOT = "screenshot"
    TYPE_CHOICES = [
        (TYPE_COVER, "Обложка"),
        (TYPE_SCREENSHOT, "Скриншот"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    game = models.ForeignKey("catalog.Game", on_delete=models.CASCADE, related_name="assets")
    version = models.ForeignKey(
        "catalog.GameVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assets",
    )
    type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    file = models.ImageField(upload_to="games/assets/")
    alt = models.JSONField(default=dict, blank=True, help_text="{lang: text}")
    sort_order = models.PositiveSmallIntegerField(default=0)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    bytes = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "catalog_game_asset"
        ordering = ["sort_order"]
        verbose_name = "Ассет игры"
        verbose_name_plural = "Ассеты игр"

    def __str__(self) -> str:
        return f"{self.game} {self.type} #{self.sort_order}"
