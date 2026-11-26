"""Server-authoritative Live Room state (ADR-LIVE-ROOM-001)."""

from __future__ import annotations

import uuid

from django.db import models

from apps.core.fields import UUID7
from apps.core.ids import uuid7
from apps.core.models.base import TimeStampedModel


class Room(TimeStampedModel):
    STATUS_LOBBY = "lobby"
    STATUS_ACTIVE = "active"
    STATUS_FINISHED = "finished"
    STATUS_ABANDONED = "abandoned"
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = [
        (STATUS_LOBBY, "Lobby"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_FINISHED, "Finished"),
        (STATUS_ABANDONED, "Abandoned"),
        (STATUS_EXPIRED, "Expired"),
    ]

    SUBJECT_USER = "user"
    SUBJECT_ANON = "anon"
    SUBJECT_CHOICES = [(SUBJECT_USER, "User"), (SUBJECT_ANON, "Guest")]

    code = models.CharField(max_length=8, unique=True)
    game = models.ForeignKey("catalog.Game", on_delete=models.PROTECT, related_name="rooms")
    game_version = models.ForeignKey(
        "catalog.GameVersion", on_delete=models.PROTECT, related_name="rooms"
    )
    host_subject_type = models.CharField(max_length=8, choices=SUBJECT_CHOICES)
    host_subject_id = models.UUIDField()
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_LOBBY, db_index=True
    )
    max_players = models.PositiveSmallIntegerField(default=12)
    # Server-only state. It may contain roles, words and vote identities; it is
    # never serialized directly. Snapshot code is the only read boundary.
    state = models.JSONField(default=dict)
    version = models.PositiveIntegerField(default=1)
    expires_at = models.DateTimeField(db_index=True)
    last_activity_at = models.DateTimeField(db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "rooms_room"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "expires_at"])]

    def __str__(self) -> str:
        return f"{self.code} ({self.status})"


class RoomMember(TimeStampedModel):
    ROLE_HOST = "host"
    ROLE_PLAYER = "player"
    ROLE_CHOICES = [(ROLE_HOST, "Host"), (ROLE_PLAYER, "Player")]

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="members")
    subject_type = models.CharField(max_length=8, choices=Room.SUBJECT_CHOICES)
    subject_id = models.UUIDField()
    name = models.CharField(max_length=24)
    role = models.CharField(max_length=8, choices=ROLE_CHOICES, default=ROLE_PLAYER)
    ready = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField()

    class Meta:
        db_table = "rooms_member"
        constraints = [
            models.UniqueConstraint(
                fields=["room", "subject_type", "subject_id"],
                name="uq_room_member_subject",
            )
        ]
        indexes = [models.Index(fields=["room", "active"])]

    def __str__(self) -> str:
        return f"{self.name} @ {self.room.code}"


class RoomCommand(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="commands")
    member = models.ForeignKey(
        RoomMember, on_delete=models.SET_NULL, null=True, related_name="commands"
    )
    request_id = models.UUIDField()
    command = models.CharField(max_length=32)

    class Meta:
        db_table = "rooms_command"
        constraints = [
            models.UniqueConstraint(fields=["room", "request_id"], name="uq_room_command_request")
        ]

    def __str__(self) -> str:
        return f"{self.command} {self.request_id}"
