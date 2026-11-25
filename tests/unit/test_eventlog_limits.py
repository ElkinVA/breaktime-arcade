"""eventLog limits are measured in UTF-8 bytes, not characters (§2.12.7)."""

from __future__ import annotations

import json

import pytest
from rest_framework import serializers  # type: ignore[import-untyped]

from apps.core.contracts import validate_eventlog_semantics
from apps.gameplay.api.serializers import MAX_EVENT_LOG_BYTES, SessionResultSerializer


def _payload_of_size(size: int) -> dict[str, object]:
    payload: dict[str, object] = {
        "v": 1,
        "seed": "seed",
        "events": [{"t": 0, "k": "tick", "d": {"text": ""}}],
    }
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    text = "a" * (size - len(encoded))
    events = payload["events"]
    assert isinstance(events, list)
    events[0]["d"]["text"] = text  # type: ignore[index]
    return payload


def test_exact_eventlog_boundary_is_accepted_and_one_byte_over_is_rejected() -> None:
    at_limit = _payload_of_size(MAX_EVENT_LOG_BYTES)
    assert (
        len(json.dumps(at_limit, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        == MAX_EVENT_LOG_BYTES
    )

    assert SessionResultSerializer().validate_eventLog(at_limit) is at_limit
    with pytest.raises(serializers.ValidationError) as exc:
        SessionResultSerializer().validate_eventLog(_payload_of_size(MAX_EVENT_LOG_BYTES + 1))
    assert "too large" in str(exc.value.detail[0])


def test_eventlog_size_limit_counts_utf8_bytes() -> None:
    # Four-byte characters stay below the limit in Python characters but not
    # on the wire, so a character count would let this payload through.
    payload = {
        "v": 1,
        "seed": "seed",
        "events": [
            {
                "t": 0,
                "k": "tick",
                "d": {"text": "😀" * (MAX_EVENT_LOG_BYTES // 4 + 100)},
            }
        ],
    }

    with pytest.raises(serializers.ValidationError) as exc:
        SessionResultSerializer().validate_eventLog(payload)

    assert "too large" in str(exc.value.detail[0])


def test_lone_surrogate_is_a_validation_error_not_a_crash() -> None:
    payload = {"v": 1, "seed": "\ud800", "events": []}

    with pytest.raises(serializers.ValidationError) as exc:
        SessionResultSerializer().validate_eventLog(payload)

    assert "invalid Unicode" in str(exc.value.detail[0])


def test_semantic_validator_reports_lone_surrogate() -> None:
    eventlog = {"v": 1, "seed": "\ud800", "events": []}

    errors = validate_eventlog_semantics(eventlog, ["tick"])

    assert "eventLog contains invalid Unicode" in errors
