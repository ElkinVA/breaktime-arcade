from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7
from apps.core.ids import uuid7


class GameRatingAggregate(models.Model):
    """Денормализованный агрегат оценок игры (§2.9)."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    game = models.OneToOneField(
        "catalog.Game",
        on_delete=models.PROTECT,
        related_name="rating_aggregate",
    )
    total = models.PositiveBigIntegerField(default=0)
    count = models.PositiveIntegerField(default=0)
    average = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    wr_score = models.FloatField(default=0)
    distribution = models.JSONField(default=dict, blank=True)
    recalculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ratings_aggregate"
        verbose_name = "Агрегат оценок"
        verbose_name_plural = "Агрегаты оценок"

    def __str__(self) -> str:
        return f"{self.game_id} {self.average} ({self.count})"
