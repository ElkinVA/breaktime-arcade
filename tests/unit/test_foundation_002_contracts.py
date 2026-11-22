from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.conf import settings

from apps.core.contracts import (
    MESSAGE_SCHEMAS,
    load_schema,
    validate_catalog_semantics,
    validate_eventlog_semantics,
    validate_manifest_semantics,
    validate_message_semantics,
)

ROOT = Path(settings.BASE_DIR)


def base_manifest() -> dict[str, Any]:
    return {
        "cartridge": 1,
        "id": "neon_snake",
        "version": "1.0.0",
        "sdkVersion": "^1.0",
        "protocol": 1,
        "name": "Neon Snake",
        "entry": "index.html",
        "genre": "arcade",
        "tags": ["reflex"],
        "supportedLanguages": ["en", "de"],
        "defaultLanguage": "en",
        "mobileSupport": True,
        "orientation": "any",
        "estimatedPlayMinutes": 6,
        "theme": {"accent": "#39FF88"},
        "score": {
            "type": "integer",
            "unit": "points",
            "direction": "higher_is_better",
            "minValue": 0,
            "maxValue": 100000,
            "schemaVersion": 1,
        },
        "limits": {
            "minPlaytimeSeconds": 15,
            "maxSessionSeconds": 1800,
            "pauseOnBlur": True,
        },
        "capabilities": {
            "wasm": False,
            "pointerLock": False,
            "storage": "sdk",
            "externalOrigins": [],
        },
        "leaderboard": {"enabled": True, "claimedVerification": "heuristic_validated"},
        "verification": {
            "profile": {"maxPointsPerSecond": 60, "maxIdleGapMs": 5000},
            "eventKinds": ["start", "submit"],
            "eventSchema": {"type": "object"},
        },
        "assets": {
            "cover": "assets/cover.webp",
            "screenshots": ["assets/screen-1.webp", "assets/screen-2.webp"],
            "critical": [
                "index.html",
                "css/style.css",
                "js/ba-sdk.js",
                "js/rng.js",
                "js/game.js",
                "locales/en.json",
            ],
            "criticalPathBytes": 1000,
        },
        "credits": [{"author": "A", "license": "CC0-1.0", "aiGenerated": True}],
    }


def catalog() -> dict[str, Any]:
    return {
        "name": "Neon Snake",
        "shortDescription": "Neon",
        "description": "x" * 300,
        "instructions": "Use arrows.",
        "controls": "Arrows.",
        "seoTitle": "Neon Snake",
        "seoDescription": "Neon Snake game",
        "coverAlt": "Cover",
        "screenshotAlts": ["one", "two"],
    }


def envelope(
    message_type: str,
    source: str = "ba-sdk",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "source": source,
        "protocol": 1,
        "type": message_type,
        "requestId": "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c11",
        "sessionId": "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c12",
        "payload": payload or {},
    }


def test_all_message_schemas_load_and_validate_samples() -> None:
    eventlog = {
        "v": 1,
        "seed": "seed",
        "events": [{"t": 0, "k": "start", "d": {}}],
    }
    samples = {
        "ba:hello": envelope("ba:hello"),
        "ba:submit": envelope(
            "ba:submit",
            payload={"value": 1, "durationMs": 1000, "eventLog": eventlog, "seed": "seed"},
        ),
        "ba:leaderboard": envelope("ba:leaderboard", payload={"limit": 10}),
        "ba:storage": envelope("ba:storage", payload={"op": "get", "key": "save.v1"}),
        "ba:newSession": envelope("ba:newSession"),
        "ba:exit": envelope("ba:exit"),
        "ba:error": envelope("ba:error", payload={"code": "E_INTERNAL"}),
        "ba:context": envelope(
            "ba:context",
            source="ba-host",
            payload={
                "sessionId": "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c12",
                "gameId": "neon_snake",
                "gameVersion": "1.0.0",
                "mode": "guest",
                "nickname": None,
                "language": "en",
                "fallbackLanguage": "en",
                "strings": {},
                "score": {},
                "limits": {},
                "trustLevel": "client_reported",
                "seed": "seed",
            },
        ),
        "ba:result": envelope(
            "ba:result",
            source="ba-host",
            payload={
                "status": "guest",
                "rank": None,
                "isPersonalBest": False,
                "isRecord": False,
                "trustLevel": "client_reported",
            },
        ),
        "ba:leaderboard:data": envelope(
            "ba:leaderboard:data",
            source="ba-host",
            payload={"entries": [], "myRank": None},
        ),
        "ba:storage:data": envelope("ba:storage:data", source="ba-host", payload={"value": {}}),
        "ba:session": envelope(
            "ba:session",
            source="ba-host",
            payload={"sessionId": "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c13", "seed": "new"},
        ),
        "ba:pause": envelope("ba:pause", source="ba-host"),
        "ba:resume": envelope("ba:resume", source="ba-host"),
    }
    assert set(samples) == set(MESSAGE_SCHEMAS)
    for type_name, sample in samples.items():
        assert validate_message_semantics(sample) == [], type_name


def test_message_direction_is_enforced() -> None:
    assert validate_message_semantics(envelope("ba:hello", source="ba-host")) != []


def test_external_schema_uses_session_id_camel_case_only() -> None:
    envelope_schema = json.dumps(load_schema("messages/_envelope.json"))
    assert '"sessionId"' in envelope_schema
    assert '"session_id"' not in envelope_schema
    assert "sessionId" in envelope_schema


def test_manifest_semantics_requires_default_language_in_supported() -> None:
    value = base_manifest()
    value["defaultLanguage"] = "fr"
    assert validate_manifest_semantics(value)


def test_manifest_semantics_requires_default_locale_in_critical_path() -> None:
    value = base_manifest()
    value["assets"]["critical"].remove("locales/en.json")
    assert validate_manifest_semantics(value)


def test_catalog_alt_count_must_match_screenshots() -> None:
    assert validate_catalog_semantics(base_manifest(), catalog()) == []
    value = catalog()
    value["screenshotAlts"] = ["one"]
    assert validate_catalog_semantics(base_manifest(), value)


def test_eventlog_semantics_monotonic_and_event_kinds() -> None:
    value = {
        "v": 1,
        "seed": "seed",
        "events": [{"t": 10, "k": "start", "d": {}}, {"t": 5, "k": "submit", "d": {}}],
    }
    errors = validate_eventlog_semantics(value, ["start", "submit"], duration_ms=1000)
    assert any("monotonic" in error for error in errors)

    value["events"][1]["k"] = "unknown"
    errors = validate_eventlog_semantics(value, ["start", "submit"], duration_ms=1000)
    assert any("eventKinds" in error for error in errors)


def test_eventlog_semantics_rejects_too_late_event() -> None:
    value = {
        "v": 1,
        "seed": "seed",
        "events": [{"t": 5001, "k": "start", "d": {}}],
    }
    errors = validate_eventlog_semantics(value, ["start"], duration_ms=1000)
    assert any("durationMs" in error for error in errors)


def test_schema_files_are_draft_2020_12() -> None:
    from jsonschema import Draft202012Validator

    for path in (ROOT / "schemas").rglob("*.json"):
        Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))


def test_project_schema_contains_all_required_relations() -> None:
    ddl = (ROOT / "docs/foundation/ba_schema.sql").read_text(encoding="utf-8")
    required = {
        "accounts_user",
        "accounts_recovery_code",
        "accounts_profile",
        "accounts_nickname_history",
        "accounts_nickname_reservation",
        "accounts_email",
        "accounts_anonymous_identity",
        "i18n_language",
        "i18n_translation_entry",
        "catalog_genre",
        "catalog_genre_translation",
        "catalog_tag",
        "catalog_tag_translation",
        "catalog_game",
        "catalog_game_version",
        "catalog_game_translation",
        "catalog_game_import_draft",
        "catalog_game_additional_genre",
        "catalog_game_tag",
        "catalog_game_asset",
        "i18n_game_locale_override",
        "ratings_vote",
        "ratings_aggregate",
        "play_user_game_playtime",
        "gameplay_session",
        "gameplay_result",
        "leaderboards_entry",
        "gameplay_play_credit",
        "gameplay_daily_stats",
        "gameplay_storage",
        "content_page",
        "content_page_translation",
        "content_legal_document",
        "content_legal_document_version",
        "content_user_legal_acceptance",
        "content_cookie_consent",
        "content_seo_settings",
        "content_redirect",
        "content_ad_slot",
        "analytics_event",
        "security_event",
        "admin_audit_log",
        "moderation_action",
        "moderation_report",
        "crm_backup_run",
        "theme_token_set",
        "theme_site_settings",
    }
    for table in required:
        assert f"CREATE TABLE {table}" in ddl, table
    assert "session_id" in ddl
    assert "sessionId" not in ddl


def test_drafts_and_mappings_are_present_and_marked() -> None:
    checks = {
        "docs/contracts/BA-SDK-1.1_DRAFT.md": "DRAFT — НЕ УТВЕРЖДЕНО ВЛАДЕЛЬЦЕМ",
        "docs/contracts/BA-ENV-1.1_DRAFT.md": "DRAFT — НЕ УТВЕРЖДЕНО ВЛАДЕЛЬЦЕМ",
        "docs/contracts/SESSION_ID_PROTOCOL.md": "sessionId",
        "docs/contracts/MESSAGE_PROTOCOL.md": "ba:leaderboard:data",
        "docs/contracts/APP_J_FIELD_MAPPING.md": "GameVersion.manifest",
        "docs/contracts/CONTRADICTIONS.md": "C-001",
        "docs/audits/BA-GAME-2.2_COMPARISON.md": "каноническим выбран **вариант A**",
        "docs/foundation/DB_SCHEMA.md": "GameStorage",
        "docs/foundation/ERD.md": "erDiagram",
    }
    for path, marker in checks.items():
        assert marker in (ROOT / path).read_text(encoding="utf-8"), path
