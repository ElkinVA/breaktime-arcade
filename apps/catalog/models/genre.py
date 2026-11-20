from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7, CitextField
from apps.core.ids import uuid7


class Genre(models.Model):
    """Жанр игры. Канонические коды: arcade, puzzle, action, ... (§2.8)."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    code = CitextField(max_length=32, unique=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    image = models.ImageField(upload_to="genres/", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "catalog_genre"
        ordering = ["sort_order", "code"]
        verbose_name = "Жанр"
        verbose_name_plural = "Жанры"

    def __str__(self) -> str:
        return self.code


class GenreTranslation(models.Model):
    """Локализованное название и описание жанра."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    genre = models.ForeignKey(Genre, on_delete=models.CASCADE, related_name="translations")
    language = models.ForeignKey(
        "i18n.Language", on_delete=models.CASCADE, related_name="genre_translations"
    )
    name = models.CharField(max_length=64)
    slug = CitextField(max_length=64, help_text="Уникален в рамках языка")
    description = models.TextField(max_length=500, blank=True)
    seo_title = models.CharField(max_length=60, blank=True)
    seo_description = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "catalog_genre_translation"
        unique_together = [("genre", "language"), ("slug", "language")]
        verbose_name = "Перевод жанра"
        verbose_name_plural = "Переводы жанров"

    def __str__(self) -> str:
        return f"{self.genre.code} [{self.language.code}] {self.name}"
