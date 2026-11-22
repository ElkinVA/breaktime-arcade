"""Public complaint intake payload (§2.23 ``POST /reports``)."""

from __future__ import annotations

from rest_framework import serializers  # type: ignore[import-untyped]

from apps.moderation.models import Complaint


class ComplaintCreateSerializer(serializers.Serializer):
    """A complaint names a game and, optionally, one of its rating votes."""

    game_id = serializers.CharField(max_length=40)
    rating_id = serializers.UUIDField(required=False, allow_null=True)
    category = serializers.ChoiceField(choices=Complaint.CATEGORY_CHOICES)
    subject = serializers.CharField(max_length=255)
