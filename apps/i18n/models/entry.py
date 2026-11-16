from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7, CitextField
from apps.core.ids import uuid7


class TranslationEntry(models.Model):
    """Строка интерфейса портала. namespace+key+language уникальны."""

    STATUS_DRAFT = "draft"
    STATUS_REVIEW = "review"
    STATUS_APPROVED = "approved"
    STATUS_PUBLISHED = "published"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Черновик"),
        (STATUS_REVIEW, "На проверке"),
        (STATUS_APPROVED, "Проверено"),
        (STATUS_PUBLISHED, "Опубликовано"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    namespace = CitextField(max_length=64, db_index=True)
    key = CitextField(max_length=128)
    language = models.ForeignKey(
        "i18n.Language",
        on_delete=models.CASCADE,
        related_name="translations",
    )
    value = models.TextField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    is_machine_translated = models.BooleanField(default=False)
    updated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="translation_edits",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "i18n_translation_entry"
        unique_together = [("namespace", "key", "language")]
        verbose_name = "Перевод интерфейса"
        verbose_name_plural = "Переводы интерфейса"

    def __str__(self) -> str:
        return f"{self.namespace}.{self.key} [{self.language.code}]"
