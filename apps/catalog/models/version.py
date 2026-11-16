from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7
from apps.core.ids import uuid7


class GameVersion(models.Model):
    """Неизменяемая версия игры (§2.14.1)."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    game = models.ForeignKey("catalog.Game", on_delete=models.CASCADE, related_name="versions")
    semver = models.CharField(max_length=32, help_text="Уникален в рамках игры")
    package_hash = models.CharField(max_length=64, help_text="SHA-256 исходного ZIP")
    runtime_hash = models.CharField(max_length=64, help_text="SHA-256 рабочего бандла")
    sdk_version = models.CharField(max_length=32)
    sdk_contract_version = models.CharField(max_length=32, default="1")
    size_bytes = models.PositiveIntegerField()
    manifest = models.JSONField()
    entry_path = models.CharField(max_length=255, default="index.html")
    critical_path_bytes_declared = models.PositiveIntegerField(null=True, blank=True)
    critical_path_bytes_measured = models.PositiveIntegerField(null=True, blank=True)
    supported_languages = models.JSONField(default=list)
    claimed_verification = models.CharField(max_length=32, blank=True)
    validation_report = models.JSONField(default=dict, blank=True)
    import_report = models.JSONField(default=dict, blank=True)
    injection_report = models.JSONField(default=dict, blank=True)
    e2e_report = models.JSONField(default=dict, blank=True)
    manual_review_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="manual_reviews",
    )
    manual_review_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_versions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "catalog_game_version"
        unique_together = [("game", "semver")]
        verbose_name = "Версия игры"
        verbose_name_plural = "Версии игр"

    def __str__(self) -> str:
        return f"{self.game} v{self.semver}"
