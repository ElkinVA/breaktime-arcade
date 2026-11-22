from __future__ import annotations

import apps.core.fields
import apps.core.ids
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pipeline", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ZipExtractionJob",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        db_default=apps.core.fields.UUID7(),
                        default=apps.core.ids.uuid7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "package_hash",
                    models.CharField(db_index=True, help_text="SHA-256 исходного ZIP", max_length=64),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "В очереди"),
                            ("running", "Выполняется"),
                            ("completed", "Завершено"),
                            ("rejected", "Отклонено"),
                            ("timeout", "Таймаут"),
                            ("cancelled", "Отменено"),
                            ("failed", "Ошибка"),
                        ],
                        db_index=True,
                        default="queued",
                        max_length=16,
                    ),
                ),
                ("queue", models.CharField(default="zip", max_length=32)),
                ("task_id", models.CharField(blank=True, max_length=255)),
                ("error_code", models.CharField(blank=True, max_length=64)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("source_path", models.CharField(blank=True, max_length=255)),
                ("result_path", models.CharField(blank=True, max_length=255)),
                ("diagnostics", models.JSONField(blank=True, default=dict)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "draft",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="extraction_jobs",
                        to="pipeline.gameimportdraft",
                    ),
                ),
            ],
            options={
                "verbose_name": "Задание изолированной распаковки ZIP",
                "verbose_name_plural": "Задания изолированной распаковки ZIP",
                "db_table": "pipeline_zip_extraction_job",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["status", "created_at"],
                        name="pipeline_zip_job_status_idx",
                    )
                ],
            },
        ),
    ]
