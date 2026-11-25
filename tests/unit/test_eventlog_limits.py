"""eventLog limits are measured in UTF-8 bytes, not characters (§2.12.7)."""

from __future__ import annotations

import pytest
from rest_framework import serializers  # type: ignore[import-untyped]

from apps.gameplay.api.serializers import MAX_EVENT_LOG_BYTES, SessionResultSerializer


def test_eventlog_size_limit_counts_utf8_bytes() -> None:
    # Four-byte characters stay below the limit in Python characters but not
    # on the wire, so a character count would let this payload through.
    payload = {
        "v": 1,
        "seed": "seed",
        "events": [{"t": 0, "kind": "tick", "text": "😀" * (MAX_EVENT_LOG_BYTES // 4 + 100)}],
    }

    with pytest.raises(serializers.ValidationError) as exc:
        SessionResultSerializer().validate_eventLog(payload)

    assert "too large" in str(exc.value.detail[0])
