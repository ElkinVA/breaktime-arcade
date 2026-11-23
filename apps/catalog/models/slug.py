"""Slug-history registry for permanent redirects after a slug change (§2.4.1, §2.6)."""

from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7, CitextField
from apps.core.ids import uuid7


class GameSlugHistory(models.Model):
    """A public slug previously used by a game.

    ``Game.slug`` is language-neutral (``language`` is ``NULL``) while
    ``GameTranslation.slug`` is recorded together with its language.  The row
    outlives the change so ``catalog:game_detail`` can answer an old URL with a
    permanent ``301`` to the current canonical URL.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    game = models.ForeignKey(
        "catalog.Game",
        on_delete=models.CASCADE,
        related_name="slug_history",
    )
    language = models.ForeignKey(
        "i18n.Language",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        help_text="NULL для language-neutral Game.slug",
    )
    slug = CitextField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "catalog_game_slug_history"
        verbose_name = "История слага игры"
        verbose_name_plural = "Истории слагов игр"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["game", "language", "slug"],
                name="catalog_slug_history_unique",
                nulls_distinct=False,
            ),
        ]
        indexes = [
            models.Index(fields=["slug"], name="catalog_slug_hist_slug_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.game_id} · {self.slug}"
