from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_sdk_is_nonempty_and_exposes_public_api() -> None:
    sdk = (ROOT / "sdk/1.1.0/ba-sdk.js").read_text(encoding="utf-8")
    assert "BreaktimeArcade" in sdk
    assert '"ba-sdk"' in sdk
    assert "submitResult" in sdk
    assert "newSession" in sdk
    assert "const PROTOCOL = 1" in sdk


def test_sdk_does_not_use_forbidden_browser_storage_or_navigation() -> None:
    sdk = (ROOT / "sdk/1.1.0/ba-sdk.js").read_text(encoding="utf-8")
    for forbidden in (
        "localStorage",
        "sessionStorage",
        "indexedDB",
        "document.cookie",
        "top.location",
        "parent.location",
        "parent.document",
    ):
        assert forbidden not in sdk


def test_host_protocol_has_validation_and_relay_markers() -> None:
    host = (ROOT / "static/src/js/host_protocol.js").read_text(encoding="utf-8")
    assert "HostBridge" in host
    assert "iframe.contentWindow" in host
    assert "iframeOrigin" in host
    assert "ba:submit" in host
    assert "ba:leaderboard:data" in host
    assert "ba:storage:data" in host
    assert "validatePayload" in host


def test_player_uses_existing_portal_apis() -> None:
    player = (ROOT / "static/src/js/player.js").read_text(encoding="utf-8")
    assert "/api/v1/sessions" in player
    assert "/api/v1/games/" in player
    assert "Idempotency-Key" in player
    assert "HostBridge" in player
