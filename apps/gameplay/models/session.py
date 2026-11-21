from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7
from apps.core.ids import uuid7


class GameSession(models.Model):
    """Серверная игровая сессия (§2.12.1–2.12.4).

    Subject хранится как (subject_type, subject_id) без FK: это техническое
    решение до закрытия DB-001 (удаление пользователя/XOR). GameResult,
    leaderboard и storage в этот срез не входят.
    """

    STATE_CREATED = "created"
    STATE_ACTIVE = "active"
    STATE_FINISHED = "finished"
    STATE_EXPIRED = "expired"
    STATE_ABORTED = "aborted"
    STATE_CHOICES = [
        (STATE_CREATED, "Создана"),
        (STATE_ACTIVE, "Активна"),
        (STATE_FINISHED, "Завершена"),
        (STATE_EXPIRED, "Истекла"),
        (STATE_ABORTED, "Прервана"),
    ]

    MODE_USER = "user"
    MODE_GUEST = "guest"
    MODE_PREVIEW = "preview"
    MODE_AUTOTEST = "autotest"
    MODE_CHOICES = [
        (MODE_USER, "Пользователь"),
        (MODE_GUEST, "Гость"),
        (MODE_PREVIEW, "Предпросмотр"),
        (MODE_AUTOTEST, "Автотест"),
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
    game = models.ForeignKey(
        "catalog.Game",
        on_delete=models.PROTECT,
        related_name="sessions",
    )
    game_version = models.ForeignKey(
        "catalog.GameVersion",
        on_delete=models.PROTECT,
        related_name="sessions",
    )
    subject_type = models.CharField(max_length=8, choices=SUBJECT_CHOICES)
    subject_id = models.UUIDField(db_index=True)
    mode = models.CharField(max_length=16, choices=MODE_CHOICES)
    state = models.CharField(
        max_length=16,
        choices=STATE_CHOICES,
        default=STATE_CREATED,
        db_index=True,
    )
    ticket_hash = models.CharField(  # noqa: DJ001 - NULL means the ticket was used
        max_length=64, unique=True, null=True, blank=True
    )
    ticket_expires_at = models.DateTimeField(null=True, blank=True)
    binding_nonce_hash = models.CharField(max_length=64, blank=True, default="")
    seed = models.CharField(max_length=64)
    max_session_seconds = models.PositiveIntegerField(default=1800)
    credited_ms = models.PositiveBigIntegerField(default=0)
    activated_at = models.DateTimeField(null=True, blank=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gameplay_session"
        verbose_name = "Игровая сессия"
        verbose_name_plural = "Игровые сессии"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    state__in=["created", "active", "finished", "expired", "aborted"]
                ),
                name="ck_gameplay_session_state",
            ),
            models.CheckConstraint(
                condition=models.Q(mode__in=["user", "guest", "preview", "autotest"]),
                name="ck_gameplay_session_mode",
            ),
            models.CheckConstraint(
                condition=models.Q(subject_type__in=["user", "anon", "deleted"]),
                name="ck_gameplay_session_subject",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(subject_type="deleted")
                    | models.Q(mode="user", subject_type="user")
                    | models.Q(mode="guest", subject_type="anon")
                    | models.Q(mode="preview", subject_type__in=["user", "anon"])
                    | models.Q(mode="autotest", subject_type="user")
                ),
                name="ck_gameplay_session_mode_subject",
            ),
            models.CheckConstraint(
                condition=models.Q(max_session_seconds__lte=7200),
                name="ck_gameplay_session_max_seconds",
            ),
        ]
        indexes = [
            models.Index(
                fields=["game", "subject_type", "subject_id", "state"],
                name="ix_gameplay_session_subject",
            ),
            models.Index(fields=["state", "created_at"], name="ix_gameplay_session_state"),
        ]

    def __str__(self) -> str:
        return f"{self.game_id} {self.mode} {self.state} {self.id}"
