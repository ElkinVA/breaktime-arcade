from __future__ import annotations

import json

from rest_framework import serializers  # type: ignore[import-untyped]

from apps.core.contracts import validate_schema

MAX_EVENT_LOG_BYTES = 2 * 1024 * 1024
MAX_EVENT_LOG_EVENTS = 20_000


class SessionCreateSerializer(serializers.Serializer):
    game_id = serializers.CharField(max_length=40)


class SessionActivateSerializer(serializers.Serializer):
    ticket = serializers.CharField(min_length=16, max_length=256)
    binding_nonce = serializers.CharField(min_length=16, max_length=256)


class SessionResultSerializer(serializers.Serializer):
    value = serializers.IntegerField()
    durationMs = serializers.IntegerField(min_value=0)
    eventLog = serializers.JSONField(required=False)
    seed = serializers.CharField(required=False, allow_blank=True, max_length=128)
    clientMeta = serializers.JSONField(required=False)

    def validate_eventLog(self, value: object) -> object:
        """§2.12.7 limits; the payload is accepted but not persisted yet."""
        if value is None:
            return value
        if not isinstance(value, dict):
            raise serializers.ValidationError("eventLog must be an object")
        events = value.get("events", [])
        if not isinstance(events, list) or len(events) > MAX_EVENT_LOG_EVENTS:
            raise serializers.ValidationError("eventLog has too many events")
        try:
            encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        except UnicodeEncodeError:
            # json.loads accepts lone surrogates; they are not valid UTF-8.
            raise serializers.ValidationError("eventLog contains invalid Unicode") from None
        if len(encoded) > MAX_EVENT_LOG_BYTES:
            raise serializers.ValidationError("eventLog is too large")
        schema_errors = validate_schema("eventlog.json", value)
        if schema_errors:
            raise serializers.ValidationError("eventLog does not match schema")
        return value
