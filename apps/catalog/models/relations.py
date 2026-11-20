from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7
from apps.core.ids import uuid7


class GameGenre(models.Model):
    """Дополнительный жанр игры (§2.8); основной — Game.primary_genre."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    game = models.ForeignKey("catalog.Game", on_delete=models.CASCADE, related_name="genre_links")
    genre = models.ForeignKey("catalog.Genre", on_delete=models.CASCADE, related_name="game_links")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "catalog_game_genre"
        constraints = [
            models.UniqueConstraint(fields=["game", "genre"], name="uq_game_genre"),
        ]

    def __str__(self) -> str:
        return f"{self.game_id}:{self.genre_id}"


class GameTag(models.Model):
    """Тег игры; создаётся импортом, но модель не зависит от пайплайна."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    game = models.ForeignKey("catalog.Game", on_delete=models.CASCADE, related_name="tag_links")
    tag = models.ForeignKey("catalog.Tag", on_delete=models.CASCADE, related_name="game_links")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "catalog_game_tag"
        constraints = [
            models.UniqueConstraint(fields=["game", "tag"], name="uq_game_tag"),
        ]

    def __str__(self) -> str:
        return f"{self.game_id}:{self.tag_id}"
