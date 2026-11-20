from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from django.conf import settings
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"


def load_schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def validate(name: str, instance: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(load_schema(name))
    return [error.message for error in validator.iter_errors(instance)]


def manifest() -> dict[str, Any]:
    return {
        "cartridge": 1,
        "id": "neon_snake",
        "version": "1.0.0",
        "sdkVersion": "^1.0",
        "protocol": 1,
        "name": "Neon Snake",
        "entry": "index.html",
        "genre": "arcade",
        "tags": ["reflex", "skill", "endless"],
        "supportedLanguages": ["en", "de", "nl", "ru", "fr", "es"],
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
        "leaderboard": {
            "enabled": True,
            "claimedVerification": "heuristic_validated",
        },
        "verification": {
            "profile": {"maxPointsPerSecond": 60, "maxIdleGapMs": 5000},
            "eventKinds": ["start", "eat", "turn", "level", "collide", "end"],
            "eventSchema": {"type": "object", "additionalProperties": True},
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
                "assets/font-main.woff2",
                "assets/sprite.webp",
            ],
            "criticalPathBytes": 900000,
        },
        "credits": [{"author": "Example", "license": "CC0-1.0", "aiGenerated": True}],
    }


def catalog() -> dict[str, Any]:
    return {
        "name": "Neon Snake",
        "shortDescription": "Neon snake",
        "description": "x" * 300,
        "instructions": "Use arrows.",
        "controls": "Arrows / swipe.",
        "seoTitle": "Neon Snake",
        "seoDescription": "Neon snake game",
        "coverAlt": "Neon snake cover",
        "screenshotAlts": ["screen one", "screen two"],
    }


def eventlog() -> dict[str, Any]:
    return {
        "v": 1,
        "seed": "abc",
        "events": [
            {"t": 0, "k": "start", "d": {}},
            {"t": 1530, "k": "eat", "d": {"x": 7, "y": 3}},
        ],
    }


def test_schema_files_are_valid_draft_2020_12() -> None:
    for name in ("manifest.json", "catalog.json", "eventlog.json"):
        Draft202012Validator.check_schema(load_schema(name))


def test_manifest_example_matches_contract() -> None:
    assert validate("manifest.json", manifest()) == []


def test_manifest_rejects_invalid_id() -> None:
    value = manifest()
    value["id"] = "Bad_ID"
    assert validate("manifest.json", value)


def test_manifest_rejects_external_origins() -> None:
    value = copy.deepcopy(manifest())
    value["capabilities"]["externalOrigins"] = ["https://evil.example"]
    assert validate("manifest.json", value)


def test_manifest_rejects_null_max_score() -> None:
    value = manifest()
    value["score"]["maxValue"] = None
    assert validate("manifest.json", value)


def test_catalog_example_matches_contract() -> None:
    assert validate("catalog.json", catalog()) == []


def test_catalog_rejects_too_short_description() -> None:
    value = catalog()
    value["description"] = "short"
    assert validate("catalog.json", value)


def test_eventlog_example_matches_contract() -> None:
    assert validate("eventlog.json", eventlog()) == []


def test_eventlog_rejects_negative_time() -> None:
    value = eventlog()
    value["events"][0]["t"] = -1
    assert validate("eventlog.json", value)


def test_drf_default_permission_is_deny_by_default() -> None:
    assert settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] == [
        "rest_framework.permissions.IsAuthenticated"
    ]
