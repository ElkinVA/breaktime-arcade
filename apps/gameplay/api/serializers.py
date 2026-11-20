from __future__ import annotations

from rest_framework import serializers  # type: ignore[import-untyped]


class SessionCreateSerializer(serializers.Serializer):
    game_id = serializers.CharField(max_length=40)


class SessionActivateSerializer(serializers.Serializer):
    ticket = serializers.CharField(min_length=16, max_length=256)
    binding_nonce = serializers.CharField(min_length=16, max_length=256)
