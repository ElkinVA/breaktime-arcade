"""Durable web-side state of one isolated ZIP extraction job.

The worker itself is DB-free (``BA-ZIP-WORKER-001``): it only reads/writes the
shared volumes. This model is owned by the web process and records queue
submission, polling outcome and stable failure diagnostics for the CRM.
"""

from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7
from apps.core.ids import uuid7


class ZipExtractionJob(models.Model):
    STATUS_QUEUED = "queued"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_REJECTED = "rejected"
    STATUS_TIMEOUT = "timeout"
    STATUS_CANCELLED = "cancelled"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_QUEUED, "В очереди"),
        (STATUS_RUNNING, "Выполняется"),
        (STATUS_COMPLETED, "Завершено"),
        (STATUS_REJECTED, "Отклонено"),
        (STATUS_TIMEOUT, "Таймаут"),
        (STATUS_CANCELLED, "Отменено"),
        (STATUS_FAILED, "Ошибка"),
    ]
    TERMINAL_STATUSES = frozenset(
        {
            STATUS_COMPLETED,
            STATUS_REJECTED,
            STATUS_TIMEOUT,
            STATUS_CANCELLED,
            STATUS_FAILED,
        }
    )

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    draft = models.ForeignKey(
        "pipeline.GameImportDraft",
        on_delete=models.CASCADE,
        related_name="extraction_jobs",
    )
    package_hash = models.CharField(max_length=64, db_index=True, help_text="SHA-256 исходного ZIP")
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_QUEUED, db_index=True
    )
    queue = models.CharField(max_length=32, default="zip")
    task_id = models.CharField(max_length=255, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    source_path = models.CharField(max_length=255, blank=True)
    result_path = models.CharField(max_length=255, blank=True)
    diagnostics = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "pipeline_zip_extraction_job"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["status", "created_at"],
                name="pipeline_zip_job_status_idx",
            )
        ]
        verbose_name = "Задание изолированной распаковки ZIP"
        verbose_name_plural = "Задания изолированной распаковки ZIP"

    def __str__(self) -> str:
        return f"{self.id} ({self.status})"
