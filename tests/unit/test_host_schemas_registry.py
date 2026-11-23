from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "generate_host_schemas",
    ROOT / "scripts" / "generate_host_schemas.py",
)
assert SPEC is not None and SPEC.loader is not None
generate_host_schemas = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generate_host_schemas)

GENERATED = ROOT / "static" / "src" / "js" / "host_schemas.generated.js"


def _walk_keywords(schema: dict[str, Any]) -> None:
    for key, value in schema.items():
        assert key in generate_host_schemas.ALLOWED_KEYWORDS, key
        if key == "properties":
            for property_schema in value.values():
                _walk_keywords(property_schema)
        elif key == "items" or (key == "additionalProperties" and isinstance(value, dict)):
            _walk_keywords(value)


def test_generated_registry_matches_message_schemas() -> None:
    expected = generate_host_schemas.render_registry()
    actual = GENERATED.read_text(encoding="utf-8")
    assert actual == expected, (
        "static/src/js/host_schemas.generated.js diverges from schemas/messages/*.json; "
        "run `python3 scripts/generate_host_schemas.py`"
    )


def test_registry_contains_only_game_to_host_messages() -> None:
    registry = generate_host_schemas.build_registry()
    assert registry.types == [
        "ba:error",
        "ba:exit",
        "ba:hello",
        "ba:leaderboard",
        "ba:newSession",
        "ba:storage",
        "ba:submit",
    ]
    for host_message in ("ba:context", "ba:result", "ba:session", "ba:leaderboard:data"):
        assert host_message not in registry.payloads


def test_registry_is_flattened_into_the_js_keyword_subset() -> None:
    registry = generate_host_schemas.build_registry()
    _walk_keywords(registry.envelope)
    for payload in registry.payloads.values():
        _walk_keywords(payload)


def test_flattener_rejects_unsupported_keywords() -> None:
    with pytest.raises(generate_host_schemas.SchemaError, match="pattern"):
        generate_host_schemas._flatten(
            {"type": "string", "pattern": "^x$"}, ROOT / "schemas" / "messages"
        )
