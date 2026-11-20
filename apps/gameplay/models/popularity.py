from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7
from apps.core.ids import uuid7


class GamePlayCredit(models.Model):
    """Зачёт уникального игрока (§2.8): не чаще одного раза в 30 минут."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    game = models.ForeignKey(
        "catalog.Game",
        on_delete=models.PROTECT,
        related_name="play_credits",
    )
    subject_type = models.CharField(max_length=8)
    subject_id = models.UUIDField()
    last_credited_at = models.DateTimeField()

    class Meta:
        db_table = "gameplay_play_credit"
        verbose_name = "Зачёт популярности"
        verbose_name_plural = "Зачёты популярности"
        constraints = [
            models.UniqueConstraint(
                fields=["game", "subject_type", "subject_id"],
                name="uq_gameplay_play_credit_subject",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.game_id} {self.subject_type} {self.subject_id}"


class GameDailyStats(models.Model):
    """Дневная статистика игры (§2.8/§2.22)."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    game = models.ForeignKey(
        "catalog.Game",
        on_delete=models.PROTECT,
        related_name="daily_stats",
    )
    date = models.DateField()
    sessions = models.PositiveIntegerField(default=0)
    unique_sessions = models.PositiveIntegerField(default=0)
    completions = models.PositiveIntegerField(default=0)
    avg_duration_ms = models.PositiveBigIntegerField(default=0)

    class Meta:
        db_table = "gameplay_daily_stats"
        verbose_name = "Дневная статистика"
        verbose_name_plural = "Дневная статистика"
        constraints = [
            models.UniqueConstraint(fields=["game", "date"], name="uq_gameplay_daily_stats"),
        ]

    def __str__(self) -> str:
        return f"{self.game_id} {self.date}"
