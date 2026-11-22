from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.fields import UUID7
from apps.core.ids import uuid7


class GameRatingVote(models.Model):
    """Оценка игры пользователем (§2.9): одна строка на (game, user)."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    game = models.ForeignKey(
        "catalog.Game",
        on_delete=models.PROTECT,
        related_name="rating_votes",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="game_rating_votes",
    )
    value = models.PositiveSmallIntegerField()
    is_valid = models.BooleanField(default=True)
    moderated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="moderated_rating_votes",
    )
    reason = models.CharField(max_length=255, blank=True)
    moderated_at = models.DateTimeField(null=True, blank=True)
    change_count_30d = models.PositiveSmallIntegerField(default=0)
    change_window_started_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    changed_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "ratings_vote"
        verbose_name = "Оценка игры"
        verbose_name_plural = "Оценки игр"
        constraints = [
            models.UniqueConstraint(fields=["game", "user"], name="uq_ratings_vote_game_user"),
            models.CheckConstraint(
                condition=models.Q(value__gte=1, value__lte=5),
                name="ck_ratings_vote_value",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "changed_at"],
                name="ix_ratings_vote_user_changed",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.game_id} {self.user_id} {self.value}"
