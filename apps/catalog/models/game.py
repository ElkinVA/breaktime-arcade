from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.fields import UUID7, CitextField
from apps.core.ids import uuid7


class Game(models.Model):
    """Игра-картридж. technical_id и host_label неизменяемы (§2.4.1)."""

    STATUS_DRAFT = "draft"
    STATUS_REVIEW = "review"
    STATUS_PUBLISHED = "published"
    STATUS_HIDDEN = "hidden"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Черновик"),
        (STATUS_REVIEW, "На проверке"),
        (STATUS_PUBLISHED, "Опубликована"),
        (STATUS_HIDDEN, "Скрыта"),
        (STATUS_ARCHIVED, "Архив"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    technical_id = CitextField(
        max_length=40,
        unique=True,
        help_text="Неизменяемый код из манифеста. Regex: ^[a-z][a-z0-9_]{1,38}[a-z0-9]$",
    )
    host_label = CitextField(
        max_length=63,
        unique=True,
        help_text="DNS-метка игрового origin. Неизменяема.",
    )
    slug = CitextField(
        max_length=128,
        unique=True,
        help_text="Публичный адрес игры на портале. Локализуется.",
    )
    primary_genre = models.ForeignKey(
        "catalog.Genre",
        on_delete=models.PROTECT,
        related_name="primary_games",
    )
    additional_genres = models.ManyToManyField(
        "catalog.Genre",
        through="catalog.GameGenre",
        related_name="additional_games",
        blank=True,
    )
    tags = models.ManyToManyField(
        "catalog.Tag",
        through="catalog.GameTag",
        related_name="games",
        blank=True,
    )
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True
    )
    current_version = models.ForeignKey(
        "catalog.GameVersion",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="current_for_games",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    publish_at = models.DateTimeField(null=True, blank=True, help_text="Запланированная публикация")

    # Настройки из манифеста (P — платформа, только чтение)
    min_session_seconds = models.PositiveIntegerField(default=15)
    max_session_seconds = models.PositiveIntegerField(default=1800)
    pause_on_blur = models.BooleanField(default=True)
    mobile_support = models.BooleanField(default=True)
    orientation = models.CharField(max_length=16, default="any")
    estimated_play_minutes = models.PositiveSmallIntegerField(default=5)
    default_language = models.CharField(max_length=8, default="en")
    accent_color = models.CharField(max_length=7, default="#39ff88")
    capabilities = models.JSONField(default=dict, blank=True)
    verification_profile = models.JSONField(default=dict, blank=True)

    # Правила счёта
    score_type = models.CharField(max_length=16, default="integer")
    score_unit = models.CharField(max_length=16, default="points")
    score_direction = models.CharField(max_length=16, default="higher_is_better")
    score_min_value = models.IntegerField(default=0)
    score_max_value = models.IntegerField(default=100000)
    score_schema_version = models.PositiveSmallIntegerField(default=1)

    # Таблица рекордов
    leaderboard_epoch = models.PositiveSmallIntegerField(default=1)
    leaderboard_enabled = models.BooleanField(default=True)
    leaderboard_only_verified = models.BooleanField(default=False)

    # Настройки доверия и голосования (C — только CRM)
    rating_min_playtime_seconds = models.PositiveIntegerField(default=120)
    verifier_slug = models.CharField(max_length=64, blank=True)
    trust_level_max = models.CharField(max_length=32, default="heuristic_validated")

    # Поля, переопределённые в CRM (не затираются при импорте)
    overridden_fields = models.JSONField(default=list, blank=True)
    credits = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "catalog_game"
        verbose_name = "Игра"
        verbose_name_plural = "Игры"

    def __str__(self) -> str:
        return self.technical_id

    IDENTITY_FIELDS = ("technical_id", "host_label")
    PUBLISHED_STATUSES = {STATUS_PUBLISHED, STATUS_HIDDEN, STATUS_ARCHIVED}

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Keep identity immutable after first publication; never reuse it."""
        if not self._state.adding and self.pk is not None:
            update_fields = kwargs.get("update_fields")
            names = set(update_fields) if update_fields is not None else set(self.IDENTITY_FIELDS)
            fields_to_check = {field for field in self.IDENTITY_FIELDS if field in names}
            if fields_to_check:
                previous = (
                    type(self)
                    .objects.filter(pk=self.pk)
                    .values("published_at", "status", *fields_to_check)
                    .first()
                )
                published = previous is not None and (
                    previous["published_at"] is not None
                    or previous["status"] in self.PUBLISHED_STATUSES
                )
                if published:
                    for field in fields_to_check:
                        if getattr(self, field) != previous[field]:
                            raise ValidationError(
                                f"Game.{field} is immutable after publication",
                                code="game_identity_immutable",
                            )
        super().save(*args, **kwargs)
