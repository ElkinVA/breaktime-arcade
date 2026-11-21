from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
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

    IMMUTABLE_FIELDS = (
        "id",
        "game_id",
        "semver",
        "package_hash",
        "runtime_hash",
        "sdk_version",
        "sdk_contract_version",
        "size_bytes",
        "manifest",
        "entry_path",
        "critical_path_bytes_declared",
        "critical_path_bytes_measured",
        "supported_languages",
        "claimed_verification",
        "validation_report",
        "import_report",
        "injection_report",
        "e2e_report",
        "manual_review_at",
        "created_at",
    )
    AUDIT_FIELDS = ("created_by", "manual_review_by")

    class Meta:
        db_table = "catalog_game_version"
        unique_together = [("game", "semver")]
        verbose_name = "Версия игры"
        verbose_name_plural = "Версии игр"

    def __str__(self) -> str:
        return f"{self.game} v{self.semver}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Reject ORM changes to content; only audit FKs may be nulled (DB-006)."""
        if not self._state.adding and self.pk is not None:
            update_fields = kwargs.get("update_fields")
            if update_fields is None:
                fields_to_check = set(self.IMMUTABLE_FIELDS)
                audit_to_check = set(self.AUDIT_FIELDS)
            else:
                names = set(update_fields)
                fields_to_check = {
                    field
                    for field in self.IMMUTABLE_FIELDS
                    if field in names or (field == "game_id" and "game" in names)
                }
                audit_to_check = {field for field in self.AUDIT_FIELDS if field in names}
            if fields_to_check or audit_to_check:
                previous = (
                    type(self)
                    .objects.filter(pk=self.pk)
                    .values("created_by_id", "manual_review_by_id", *fields_to_check)
                    .first()
                )
                if previous is not None:
                    for field in fields_to_check:
                        if getattr(self, field) != previous[field]:
                            raise ValidationError(
                                f"GameVersion.{field} is immutable",
                                code="game_version_immutable",
                            )
                    for field in audit_to_check:
                        old = previous[f"{field}_id"]
                        new = getattr(self, f"{field}_id")
                        if new != old and new is not None:
                            raise ValidationError(
                                f"GameVersion.{field} may only be nulled",
                                code="game_version_audit_immutable",
                            )
        super().save(*args, **kwargs)
