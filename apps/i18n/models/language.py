from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7, CitextField
from apps.core.ids import uuid7


class Language(models.Model):
    """Активный язык портала. Источник для URL-префиксов, sitemap и hreflang."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    code = CitextField(max_length=8, unique=True, help_text="ISO 639-1, например 'en', 'de', 'nl'.")
    name = models.CharField(max_length=64, help_text="Отображаемое название на самом языке.")
    native_name = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_rtl = models.BooleanField(default=False)
    sort_order = models.PositiveSmallIntegerField(default=0)
    plural_rule = models.CharField(
        max_length=16,
        default="other",
        help_text="CLDR plural rule: one, few, many, other и т.д.",
    )
    fts_config = models.CharField(
        max_length=64,
        blank=True,
        help_text="PostgreSQL FTS конфигурация. Пусто = simple + unaccent + pg_trgm.",
    )
    ui_ready_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Момент, когда 100% строк интерфейса переведено и опубликовано.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "i18n_language"
        ordering = ["sort_order", "code"]
        verbose_name = "Язык"
        verbose_name_plural = "Языки"

    def __str__(self) -> str:
        return f"{self.code} ({self.name})"

    @property
    def is_fully_ready(self) -> bool:
        return self.is_active and self.ui_ready_at is not None
