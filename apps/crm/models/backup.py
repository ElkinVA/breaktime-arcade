from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7
from apps.core.ids import uuid7


class BackupRun(models.Model):
    """Запись о запуске резервного копирования (§2.5)."""

    TYPE_FULL = "full"
    TYPE_WAL = "wal"
    TYPE_RESTORE_CHECK = "restore_check"
    TYPE_CHOICES = [
        (TYPE_FULL, "Полный дамп"),
        (TYPE_WAL, "WAL-архив"),
        (TYPE_RESTORE_CHECK, "Проверка восстановления"),
    ]

    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_RUNNING, "Выполняется"),
        (STATUS_SUCCESS, "Успех"),
        (STATUS_FAILED, "Ошибка"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    type = models.CharField(max_length=16, choices=TYPE_CHOICES, db_index=True)
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_RUNNING,
        db_index=True,
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    sha256 = models.CharField(max_length=64, blank=True)
    file_path = models.CharField(max_length=512, blank=True)
    remote_uri = models.CharField(max_length=512, blank=True)
    error_message = models.TextField(blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "crm_backup_run"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["type", "-started_at"]),
            models.Index(fields=["status"]),
        ]
        verbose_name = "Запуск бэкапа"
        verbose_name_plural = "Запуски бэкапов"

    def __str__(self) -> str:
        return f"{self.type} {self.started_at:%Y-%m-%d %H:%M} ({self.status})"
