from __future__ import annotations

import apps.core.fields
import apps.core.ids
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("accounts", "0004_ownerrecoverycode_loginevent"),
        ("catalog", "0010_game_identity_case_sensitive_guard"),
        ("core", "0001_extensions"),
    ]

    operations = [
        migrations.CreateModel(
            name="GameImportDraft",
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
                ("original_filename", models.CharField(blank=True, max_length=255)),
                ("size_bytes", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("uploaded", "Загружен"),
                            ("validated", "Проверен"),
                            ("rejected", "Отклонён"),
                            ("imported", "Импортирован"),
                            ("published", "Опубликован"),
                        ],
                        db_index=True,
                        default="uploaded",
                        max_length=16,
                    ),
                ),
                (
                    "package_path",
                    models.CharField(blank=True, help_text="Приватный исходный ZIP", max_length=255),
                ),
                (
                    "runtime_path",
                    models.CharField(blank=True, help_text="Публичный рабочий бандл", max_length=255),
                ),
                ("manifest", models.JSONField(blank=True, default=dict)),
                ("diagnostics", models.JSONField(blank=True, default=list)),
                ("validation_report", models.JSONField(blank=True, default=dict)),
                ("import_report", models.JSONField(blank=True, default=dict)),
                ("injection_report", models.JSONField(blank=True, default=dict)),
                ("e2e_report", models.JSONField(blank=True, default=dict)),
                ("conflicts", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="game_import_drafts",
                        to="accounts.user",
                    ),
                ),
                (
                    "game",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="import_drafts",
                        to="catalog.game",
                    ),
                ),
                (
                    "version",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="import_drafts",
                        to="catalog.gameversion",
                    ),
                ),
            ],
            options={
                "verbose_name": "Черновик импорта игры",
                "verbose_name_plural": "Черновики импорта игр",
                "db_table": "pipeline_game_import_draft",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["package_hash", "created_at"],
                        name="pipeline_draft_pkg_created_idx",
                    )
                ],
            },
        ),
    ]
