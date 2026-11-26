from __future__ import annotations

import json

from rest_framework import serializers  # type: ignore[import-untyped]

MAX_COMMAND_PAYLOAD_BYTES = 2048


class RoomCreateSerializer(serializers.Serializer):
    game_id = serializers.CharField(max_length=40)
    max_players = serializers.IntegerField(min_value=4, max_value=12, default=12)
    undercover_count = serializers.IntegerField(min_value=1, max_value=3, default=1)
    mr_white = serializers.BooleanField(default=False)
    category_id = serializers.CharField(max_length=32, required=False, allow_blank=True)
    name = serializers.CharField(max_length=24, required=False, allow_blank=True)


class RoomJoinSerializer(serializers.Serializer):
    code = serializers.CharField(min_length=4, max_length=8)
    name = serializers.CharField(max_length=24, required=False, allow_blank=True)


class RoomCommandSerializer(serializers.Serializer):
    command = serializers.CharField(max_length=32)
    payload = serializers.JSONField(default=dict)
    requestId = serializers.UUIDField()
    expectedVersion = serializers.IntegerField(min_value=0)

    def validate_payload(self, value: object) -> dict[str, object]:
        if not isinstance(value, dict):
            raise serializers.ValidationError("payload must be an object")
        try:
            encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise serializers.ValidationError("payload is not valid UTF-8 JSON") from exc
        if len(encoded) > MAX_COMMAND_PAYLOAD_BYTES:
            raise serializers.ValidationError("payload is too large")
        return value
