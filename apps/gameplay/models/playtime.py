from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.fields import UUID7
from apps.core.ids import uuid7


class UserGamePlaytime(models.Model):
    """Подтверждённое серверное игровое время (§2.12.3, §2.22).

    Only ``mode=user`` sessions with ``is_test=false`` are credited; guests
    and service modes never reach this table. Account deletion removes rows.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="game_playtime",
    )
    game = models.ForeignKey(
        "catalog.Game",
        on_delete=models.PROTECT,
        related_name="user_playtime",
    )
    verified_seconds = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gameplay_user_playtime"
        verbose_name = "Игровое время пользователя"
        verbose_name_plural = "Игровое время пользователей"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "game"],
                name="uq_gameplay_playtime_user_game",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} {self.game_id} {self.verified_seconds}"
