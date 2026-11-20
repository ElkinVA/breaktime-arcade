from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.fields import UUID7
from apps.core.ids import uuid7


class GameStorage(models.Model):
    """Один JSONB-документ на (игра, субъект) (§2.22).

    Guest rows expire after 90 days of inactivity; user rows live until account
    deletion. ``bytes`` is recomputed by a DB trigger from the JSON text and
    capped at 64 KiB; the service additionally enforces key/depth limits.
    """

    SUBJECT_USER = "user"
    SUBJECT_ANON = "anon"
    SUBJECT_CHOICES = [
        (SUBJECT_USER, "Пользователь"),
        (SUBJECT_ANON, "Гость"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    game = models.ForeignKey(
        "catalog.Game",
        on_delete=models.PROTECT,
        related_name="storage_documents",
    )
    subject_type = models.CharField(max_length=8, choices=SUBJECT_CHOICES)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="game_storage",
    )
    anon = models.ForeignKey(
        "accounts.AnonymousIdentity",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="game_storage",
    )
    data = models.JSONField(default=dict, blank=True)
    bytes = models.PositiveIntegerField(default=0)
    revision = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gameplay_storage"
        verbose_name = "Хранилище игры"
        verbose_name_plural = "Хранилища игр"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(subject_type="user", user__isnull=False, anon__isnull=True)
                    | models.Q(subject_type="anon", anon__isnull=False, user__isnull=True)
                ),
                name="ck_gameplay_storage_subject",
            ),
            models.CheckConstraint(
                condition=models.Q(bytes__lte=65536),
                name="ck_gameplay_storage_bytes",
            ),
            models.UniqueConstraint(
                fields=["game", "user"],
                condition=models.Q(subject_type="user"),
                name="uq_gameplay_storage_user",
            ),
            models.UniqueConstraint(
                fields=["game", "anon"],
                condition=models.Q(subject_type="anon"),
                name="uq_gameplay_storage_anon",
            ),
        ]
        indexes = [
            models.Index(fields=["expires_at"], name="ix_gameplay_storage_expiry"),
        ]

    def __str__(self) -> str:
        return f"{self.game_id} {self.subject_type} r{self.revision}"
