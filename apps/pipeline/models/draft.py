"""Server-side state of the game import wizard (``GameImportDraft``, §2.14.5).

The draft is the durable record of one upload: its immutable package hash,
diagnostics, import conflicts and the produced version. It is not a source of
truth for the catalog; ``Game.current_version`` remains authoritative.
"""

from __future__ import annotations

from typing import Any

from django.db import models

from apps.core.fields import UUID7
from apps.core.ids import uuid7


class GameImportDraft(models.Model):
    STATUS_UPLOADED = "uploaded"
    STATUS_VALIDATED = "validated"
    STATUS_REJECTED = "rejected"
    STATUS_IMPORTED = "imported"
    STATUS_PUBLISHED = "published"
    STATUS_CHOICES = [
        (STATUS_UPLOADED, "Загружен"),
        (STATUS_VALIDATED, "Проверен"),
        (STATUS_REJECTED, "Отклонён"),
        (STATUS_IMPORTED, "Импортирован"),
        (STATUS_PUBLISHED, "Опубликован"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    package_hash = models.CharField(max_length=64, db_index=True, help_text="SHA-256 исходного ZIP")
    original_filename = models.CharField(max_length=255, blank=True)
    size_bytes = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_UPLOADED, db_index=True
    )
    package_path = models.CharField(max_length=255, blank=True, help_text="Приватный исходный ZIP")
    runtime_path = models.CharField(max_length=255, blank=True, help_text="Публичный рабочий бандл")
    manifest = models.JSONField(default=dict, blank=True)
    diagnostics = models.JSONField(default=list, blank=True)
    validation_report = models.JSONField(default=dict, blank=True)
    import_report = models.JSONField(default=dict, blank=True)
    injection_report = models.JSONField(default=dict, blank=True)
    e2e_report = models.JSONField(default=dict, blank=True)
    conflicts = models.JSONField(default=list, blank=True)
    game = models.ForeignKey(
        "catalog.Game",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="import_drafts",
    )
    version = models.ForeignKey(
        "catalog.GameVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="import_drafts",
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="game_import_drafts",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "pipeline_game_import_draft"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["package_hash", "created_at"],
                name="pipeline_draft_pkg_created_idx",
            )
        ]
        verbose_name = "Черновик импорта игры"
        verbose_name_plural = "Черновики импорта игр"

    def __str__(self) -> str:
        return f"{self.original_filename or self.package_hash[:12]} ({self.status})"

    def add_diagnostics(self, diagnostics: list[dict[str, Any]]) -> None:
        self.diagnostics = [*self.diagnostics, *diagnostics]
