"""Durable CRM audit trail (§2.16.1, §2.22 ``AdminAuditLog``).

Privileged operations (staff role/status changes, publication and rollback)
are appended here with actor, target, action and timestamp. Rows are
append-only: model-level guards reject mutation and a PostgreSQL trigger
forbids UPDATE/DELETE, except for the ``ON DELETE SET NULL`` action performed
when the actor account itself is deleted.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import models


class AdminAuditLog(models.Model):
    """Append-only record of a privileged CRM action."""

    ACTION_STAFF_ROLE_CHANGED = "staff.role_changed"
    ACTION_STAFF_ACTIVATED = "staff.activated"
    ACTION_STAFF_DEACTIVATED = "staff.deactivated"
    ACTION_GAME_PUBLISHED = "game.published"
    ACTION_GAME_ROLLED_BACK = "game.rolled_back"

    ACTION_CHOICES = [
        (ACTION_STAFF_ROLE_CHANGED, "Смена роли сотрудника"),
        (ACTION_STAFF_ACTIVATED, "Активация сотрудника"),
        (ACTION_STAFF_DEACTIVATED, "Деактивация сотрудника"),
        (ACTION_GAME_PUBLISHED, "Публикация версии"),
        (ACTION_GAME_ROLLED_BACK, "Откат версии"),
    ]

    id = models.BigAutoField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crm_audit_events",
    )
    action = models.CharField(max_length=64, choices=ACTION_CHOICES)
    object_type = models.CharField(max_length=64, blank=True)
    object_id = models.UUIDField(null=True, blank=True)
    before_data = models.JSONField(null=True, blank=True)
    after_data = models.JSONField(null=True, blank=True)
    reason = models.TextField(blank=True)
    ip_hash = models.CharField(max_length=64, blank=True)

    class Meta:
        db_table = "admin_audit_log"
        ordering = ["-created_at", "-id"]
        verbose_name = "Запись аудита CRM"
        verbose_name_plural = "Журнал аудита CRM"
        indexes = [
            models.Index(fields=["action", "created_at"], name="ix_audit_action_created"),
            models.Index(fields=["object_type", "object_id"], name="ix_audit_object"),
        ]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} {self.object_type}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Only allow inserting a new row."""
        if self.pk is not None and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Запись аудита неизменяема.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValidationError("Запись аудита нельзя удалить.")


__all__ = ["AdminAuditLog"]
