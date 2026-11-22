"""Complaint queue model (§2.16.2 «Жалобы», §2.23 ``POST /reports``).

A complaint always names the game it concerns and may additionally point at a
specific rating vote. The reporter is kept while the account exists; deleting
an account clears the link (``SET NULL``) so the moderation history and the
underlying game/rating evidence survive, matching the retention policy. The
rating link is also nullable because deleting an account removes its votes.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.fields import UUID7
from apps.core.ids import uuid7


class Complaint(models.Model):
    """Жалоба на игру или оценку, обрабатываемая модератором."""

    TARGET_GAME = "game"
    TARGET_RATING = "rating"
    TARGET_CHOICES = [
        (TARGET_GAME, "Игра"),
        (TARGET_RATING, "Оценка"),
    ]

    STATUS_NEW = "new"
    STATUS_ASSIGNED = "assigned"
    STATUS_RESOLVED = "resolved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_NEW, "Новая"),
        (STATUS_ASSIGNED, "Назначена"),
        (STATUS_RESOLVED, "Решена"),
        (STATUS_REJECTED, "Отклонена"),
    ]
    CLOSED_STATUSES = frozenset({STATUS_RESOLVED, STATUS_REJECTED})

    CATEGORY_SPAM = "spam"
    CATEGORY_ABUSE = "abuse"
    CATEGORY_INCORRECT = "incorrect"
    CATEGORY_OTHER = "other"
    CATEGORY_CHOICES = [
        (CATEGORY_SPAM, "Спам"),
        (CATEGORY_ABUSE, "Оскорбления"),
        (CATEGORY_INCORRECT, "Недостоверная информация"),
        (CATEGORY_OTHER, "Другое"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    target_type = models.CharField(
        max_length=16,
        choices=TARGET_CHOICES,
        default=TARGET_GAME,
        db_index=True,
    )
    game = models.ForeignKey(
        "catalog.Game",
        on_delete=models.PROTECT,
        related_name="complaints",
    )
    rating = models.ForeignKey(
        "ratings.GameRatingVote",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="complaints",
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="filed_complaints",
    )
    category = models.CharField(
        max_length=16,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_OTHER,
    )
    subject = models.CharField(max_length=255)
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_NEW,
        db_index=True,
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_complaints",
    )
    resolution = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "moderation_complaint"
        ordering = ["-created_at", "-id"]
        verbose_name = "Жалоба"
        verbose_name_plural = "Жалобы"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(target_type="game", rating__isnull=True)
                    | models.Q(target_type="rating")
                ),
                name="ck_moderation_complaint_target",
            ),
            models.CheckConstraint(
                condition=(models.Q(status__in=["new", "assigned"]) | ~models.Q(resolution="")),
                name="ck_moderation_complaint_resolution",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "created_at"], name="ix_complaint_status_created"),
            models.Index(fields=["target_type", "game"], name="ix_complaint_target"),
        ]

    def __str__(self) -> str:
        return f"{self.get_target_type_display()} {self.game_id} [{self.status}]"


__all__ = ["Complaint"]
