import apps.core.fields
import apps.core.ids
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("catalog", "0001_initial"),
        ("ratings", "0002_gameratingvote_ix_ratings_vote_user_changed"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Complaint",
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
                    "target_type",
                    models.CharField(
                        choices=[("game", "Игра"), ("rating", "Оценка")],
                        db_index=True,
                        default="game",
                        max_length=16,
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("spam", "Спам"),
                            ("abuse", "Оскорбления"),
                            ("incorrect", "Недостоверная информация"),
                            ("other", "Другое"),
                        ],
                        default="other",
                        max_length=16,
                    ),
                ),
                ("subject", models.CharField(max_length=255)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("new", "Новая"),
                            ("assigned", "Назначена"),
                            ("resolved", "Решена"),
                            ("rejected", "Отклонена"),
                        ],
                        db_index=True,
                        default="new",
                        max_length=16,
                    ),
                ),
                ("resolution", models.TextField(blank=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "assigned_to",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assigned_complaints",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "game",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="complaints",
                        to="catalog.game",
                    ),
                ),
                (
                    "rating",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="complaints",
                        to="ratings.gameratingvote",
                    ),
                ),
                (
                    "reporter",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="filed_complaints",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Жалоба",
                "verbose_name_plural": "Жалобы",
                "db_table": "moderation_complaint",
                "ordering": ["-created_at", "-id"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(target_type="game", rating__isnull=True)
                        | models.Q(target_type="rating"),
                        name="ck_moderation_complaint_target",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("status__in", ["new", "assigned"]))
                        | ~models.Q(("resolution", "")),
                        name="ck_moderation_complaint_resolution",
                    ),
                ],
                "indexes": [
                    models.Index(
                        fields=["status", "created_at"],
                        name="ix_complaint_status_created",
                    ),
                    models.Index(
                        fields=["target_type", "game"],
                        name="ix_complaint_target",
                    ),
                ],
            },
        ),
    ]
