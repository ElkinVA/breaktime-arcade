from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7
from apps.core.ids import uuid7


class SiteSettings(models.Model):
    """Глобальные настройки портала."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    logo = models.ImageField(upload_to="site/logo/", blank=True)
    favicon = models.ImageField(upload_to="site/favicon/", blank=True)
    contacts = models.JSONField(default=dict, blank=True)
    counter_config = models.JSONField(default=dict, blank=True)
    default_theme = models.CharField(max_length=16, default="dark")
    reserved_host_labels = models.JSONField(
        default=list,
        blank=True,
        help_text="Зарезервированные метки игровых хостов (§2.4.1).",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "theme_site_settings"
        verbose_name = "Настройки сайта"
        verbose_name_plural = "Настройки сайта"

    def __str__(self) -> str:
        return "SiteSettings"
