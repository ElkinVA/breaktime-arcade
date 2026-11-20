from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7, CitextField
from apps.core.ids import uuid7


class Tag(models.Model):
    """Тег игры. Создаётся автоматически при импорте (§2.14.4)."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    code = CitextField(max_length=64, unique=True)
    needs_translation = models.BooleanField(default=True, help_text="Пометка «требует перевода»")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "catalog_tag"
        ordering = ["code"]
        verbose_name = "Тег"
        verbose_name_plural = "Теги"

    def __str__(self) -> str:
        return self.code


class TagTranslation(models.Model):
    """Локализованное название тега."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="translations")
    language = models.ForeignKey(
        "i18n.Language", on_delete=models.CASCADE, related_name="tag_translations"
    )
    name = models.CharField(max_length=64)
    slug = CitextField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "catalog_tag_translation"
        unique_together = [("tag", "language"), ("slug", "language")]
        verbose_name = "Перевод тега"
        verbose_name_plural = "Переводы тегов"

    def __str__(self) -> str:
        return f"{self.tag.code} [{self.language.code}] {self.name}"
