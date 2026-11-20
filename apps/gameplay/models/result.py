from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.fields import UUID7
from apps.core.ids import uuid7


class GameResult(models.Model):
    """Результат партии (§2.12.5, §2.22).

    Subject follows DB-001: user / anon / deleted; for ``deleted`` both FKs are
    NULL and the row is kept anonymised. Guests do not get stored results
    (§2.12.5), the anon branch exists for completeness and future modes.
    """

    TRUST_CLIENT_REPORTED = "client_reported"
    TRUST_HEURISTIC_VALIDATED = "heuristic_validated"
    TRUST_REPLAY_VERIFIED = "replay_verified"
    TRUST_SERVER_AUTHORITATIVE = "server_authoritative"
    TRUST_CHOICES = [
        (TRUST_CLIENT_REPORTED, "Client reported"),
        (TRUST_HEURISTIC_VALIDATED, "Heuristic validated"),
        (TRUST_REPLAY_VERIFIED, "Replay verified"),
        (TRUST_SERVER_AUTHORITATIVE, "Server authoritative"),
    ]

    SUBJECT_USER = "user"
    SUBJECT_ANON = "anon"
    SUBJECT_DELETED = "deleted"
    SUBJECT_CHOICES = [
        (SUBJECT_USER, "Пользователь"),
        (SUBJECT_ANON, "Гость"),
        (SUBJECT_DELETED, "Удалён"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    session = models.OneToOneField(
        "gameplay.GameSession",
        on_delete=models.PROTECT,
        related_name="result",
    )
    game = models.ForeignKey(
        "catalog.Game",
        on_delete=models.PROTECT,
        related_name="results",
    )
    game_version = models.ForeignKey(
        "catalog.GameVersion",
        on_delete=models.PROTECT,
        related_name="results",
    )
    subject_type = models.CharField(max_length=8, choices=SUBJECT_CHOICES)
    # PROTECT: subject deletion goes through the explicit anonymisation flow
    # (DB-001), otherwise the XOR CHECK would break on SET_NULL.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="game_results",
    )
    anon = models.ForeignKey(
        "accounts.AnonymousIdentity",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="game_results",
    )
    epoch = models.PositiveSmallIntegerField()
    value = models.BigIntegerField()
    unit = models.CharField(max_length=16)
    duration_ms = models.PositiveBigIntegerField()
    trust_level = models.CharField(
        max_length=32,
        choices=TRUST_CHOICES,
        default=TRUST_CLIENT_REPORTED,
    )
    is_public = models.BooleanField(default=True)
    is_quarantined = models.BooleanField(default=False)
    is_test = models.BooleanField(default=False)
    idempotency_key = models.CharField(max_length=128)
    # Exactly the response returned for the first request (§2.12.5).
    response = models.JSONField(default=dict)
    verifier_flags = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "gameplay_result"
        verbose_name = "Результат игры"
        verbose_name_plural = "Результаты игр"
        constraints = [
            models.UniqueConstraint(
                fields=["session", "idempotency_key"],
                name="uq_gameplay_result_session_key",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(subject_type="user", user__isnull=False, anon__isnull=True)
                    | models.Q(subject_type="anon", anon__isnull=False, user__isnull=True)
                    | models.Q(subject_type="deleted", user__isnull=True, anon__isnull=True)
                ),
                name="ck_gameplay_result_subject",
            ),
            models.CheckConstraint(
                condition=models.Q(duration_ms__gte=0),
                name="ck_gameplay_result_duration",
            ),
        ]
        indexes = [
            models.Index(
                fields=["game", "user", "-value", "created_at"],
                condition=models.Q(is_public=True, is_quarantined=False, is_test=False),
                name="ix_gameplay_result_best_desc",
            ),
            models.Index(
                fields=["game", "user", "value", "created_at"],
                condition=models.Q(is_public=True, is_quarantined=False, is_test=False),
                name="ix_gameplay_result_best_asc",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.game_id} {self.subject_type} {self.value}"


class LeaderboardEntry(models.Model):
    """Текущий лучший результат пользователя в эпохе (§2.11)."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    game = models.ForeignKey(
        "catalog.Game",
        on_delete=models.PROTECT,
        related_name="leaderboard_entries",
    )
    epoch = models.PositiveSmallIntegerField()
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="leaderboard_entries",
    )
    best_result = models.ForeignKey(
        "gameplay.GameResult",
        on_delete=models.PROTECT,
        related_name="leaderboard_entries",
    )
    value = models.BigIntegerField()
    achieved_at = models.DateTimeField()
    is_public = models.BooleanField(default=True)
    trust_level = models.CharField(max_length=32, choices=GameResult.TRUST_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gameplay_leaderboard_entry"
        verbose_name = "Строка таблицы рекордов"
        verbose_name_plural = "Таблицы рекордов"
        constraints = [
            models.UniqueConstraint(
                fields=["game", "epoch", "user"],
                name="uq_leaderboard_game_epoch_user",
            ),
        ]
        indexes = [
            models.Index(
                fields=["game", "epoch", "-value", "achieved_at"],
                condition=models.Q(is_public=True),
                name="ix_leaderboard_best_desc",
            ),
            models.Index(
                fields=["game", "epoch", "value", "achieved_at"],
                condition=models.Q(is_public=True),
                name="ix_leaderboard_best_asc",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.game_id} {self.user_id} {self.value}"
