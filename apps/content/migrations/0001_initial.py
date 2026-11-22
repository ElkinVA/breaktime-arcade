# Generated for ARCADE-P2-CONTENT-ANALYTICS-001.

import apps.core.fields
import apps.core.ids
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("i18n", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ContentPage",
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
                ("slug", apps.core.fields.CitextField(max_length=128, unique=True)),
                ("is_published", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Контентная страница",
                "verbose_name_plural": "Контентные страницы",
                "db_table": "content_page",
                "ordering": ["slug"],
            },
        ),
        migrations.CreateModel(
            name="ContentPageTranslation",
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
                ("title", models.CharField(max_length=200)),
                ("body", models.TextField(blank=True, default="")),
                ("seo_title", models.CharField(blank=True, default="", max_length=60)),
                (
                    "seo_description",
                    models.CharField(blank=True, default="", max_length=160),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "language",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="content_page_translations",
                        to="i18n.language",
                    ),
                ),
                (
                    "page",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="translations",
                        to="content.contentpage",
                    ),
                ),
            ],
            options={
                "verbose_name": "Перевод страницы",
                "verbose_name_plural": "Переводы страниц",
                "db_table": "content_page_translation",
                "ordering": ["page", "language__sort_order", "language__code"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("page", "language"),
                        name="uq_content_page_translation",
                    )
                ],
            },
        ),
    ]
