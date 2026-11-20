from __future__ import annotations

from rest_framework import serializers  # type: ignore[import-untyped]


class RatingVoteSerializer(serializers.Serializer):
    value = serializers.IntegerField(min_value=1, max_value=5)
