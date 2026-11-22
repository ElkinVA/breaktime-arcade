"""Basic static content pages edited from the CRM (§2.16.2, §2.19).

The canonical schema keeps a language-neutral page (stable slug + publish
flag) and per-language translations. Bodies are stored only after the
allow-list sanitiser has run, so templates may render the stored value without
ever exposing arbitrary markup supplied by a staff member.
"""

from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7, CitextField
from apps.core.ids import uuid7


class ContentPage(models.Model):
    """Публичная статическая страница портала (например, «О проекте»)."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    slug = CitextField(max_length=128, unique=True)
    is_published = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "content_page"
        ordering = ["slug"]
        verbose_name = "Контентная страница"
        verbose_name_plural = "Контентные страницы"

    def __str__(self) -> str:
        return str(self.slug)


class ContentPageTranslation(models.Model):
    """Локализованный заголовок и тело страницы."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    page = models.ForeignKey(
        ContentPage,
        on_delete=models.CASCADE,
        related_name="translations",
    )
    language = models.ForeignKey(
        "i18n.Language",
        on_delete=models.CASCADE,
        related_name="content_page_translations",
    )
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True, default="")
    seo_title = models.CharField(max_length=60, blank=True, default="")
    seo_description = models.CharField(max_length=160, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "content_page_translation"
        ordering = ["page", "language__sort_order", "language__code"]
        verbose_name = "Перевод страницы"
        verbose_name_plural = "Переводы страниц"
        constraints = [
            models.UniqueConstraint(
                fields=["page", "language"],
                name="uq_content_page_translation",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.page_id} [{self.language_id}]"


__all__ = ["ContentPage", "ContentPageTranslation"]
