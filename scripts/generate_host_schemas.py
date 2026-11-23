#!/usr/bin/env python3
# ruff: noqa: T201
"""Generate the JS host-side schema registry from schemas/messages/*.json.

The message schemas are the source of truth. Each file uses ``allOf`` plus
``$ref`` (to ``_envelope.json`` and ``schemas/eventlog.json``); the host JS
validator supports only a small keyword subset, so those constructs are
flattened here into plain objects.

Usage:
  python3 scripts/generate_host_schemas.py            # rewrite the artifact
  python3 scripts/generate_host_schemas.py --check    # fail if out of date
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, NamedTuple

ROOT = Path(__file__).resolve().parents[1]
MESSAGES_DIR = ROOT / "schemas" / "messages"
OUTPUT = ROOT / "static" / "src" / "js" / "host_schemas.generated.js"

# Keywords understood by validateSchema() in static/src/js/host_protocol.js.
ALLOWED_KEYWORDS = frozenset(
    {
        "type",
        "const",
        "enum",
        "required",
        "properties",
        "additionalProperties",
        "minLength",
        "maxLength",
        "format",
        "minimum",
        "maximum",
        "items",
        "maxItems",
    }
)


class SchemaError(ValueError):
    """Raised when a message schema cannot be flattened into the JS subset."""


class Registry(NamedTuple):
    protocol: int
    types: list[str]
    envelope: dict[str, Any]
    payloads: dict[str, dict[str, Any]]


def _load(path: Path, cache: dict[Path, dict[str, Any]]) -> dict[str, Any]:
    if path not in cache:
        cache[path] = json.loads(path.read_text(encoding="utf-8"))
    return cache[path]


def _merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if key == "properties":
            properties = dict(merged.get("properties", {}))
            for name, schema in value.items():
                properties[name] = _merge(properties.get(name, {}), schema)
            merged["properties"] = properties
        elif key == "required":
            merged["required"] = list(dict.fromkeys([*merged.get("required", []), *value]))
        elif key == "additionalProperties":
            previous = merged.get("additionalProperties")
            if previous is False or value is False:
                merged[key] = False
            elif isinstance(previous, dict) and isinstance(value, dict):
                merged[key] = _merge(previous, value)
            else:
                merged[key] = value
        else:
            merged[key] = value
    return merged


def _flatten_children(
    node: dict[str, Any],
    base_dir: Path,
    *,
    stack: frozenset[Path],
    cache: dict[Path, dict[str, Any]],
) -> dict[str, Any]:
    out = dict(node)
    if "properties" in out:
        out["properties"] = {
            name: _flatten(schema, base_dir, stack=stack, cache=cache)
            for name, schema in out["properties"].items()
        }
    if "items" in out:
        out["items"] = _flatten(out["items"], base_dir, stack=stack, cache=cache)
    if isinstance(out.get("additionalProperties"), dict):
        out["additionalProperties"] = _flatten(
            out["additionalProperties"], base_dir, stack=stack, cache=cache
        )
    return {key: value for key, value in out.items() if key in ALLOWED_KEYWORDS}


def _flatten(
    node: Any,
    base_dir: Path,
    *,
    stack: frozenset[Path] = frozenset(),
    cache: dict[Path, dict[str, Any]] | None = None,
) -> Any:
    if cache is None:
        cache = {}
    if isinstance(node, list):
        return [_flatten(item, base_dir, stack=stack, cache=cache) for item in node]
    if not isinstance(node, dict):
        return node

    result: dict[str, Any] = {}
    if "$ref" in node:
        ref = node["$ref"]
        if not isinstance(ref, str):
            raise SchemaError("$ref must be a string")
        target = (base_dir / ref).resolve()
        if target in stack:
            raise SchemaError(f"circular $ref: {target}")
        document = _load(target, cache)
        result = _merge(
            result,
            _flatten(document, target.parent, stack=stack | {target}, cache=cache),
        )
        node = {key: value for key, value in node.items() if key != "$ref"}

    if "allOf" in node:
        for part in node["allOf"]:
            result = _merge(result, _flatten(part, base_dir, stack=stack, cache=cache))
        node = {key: value for key, value in node.items() if key != "allOf"}

    return _merge(
        result,
        _flatten_children(node, base_dir, stack=stack, cache=cache),
    )


def build_registry(messages_dir: Path = MESSAGES_DIR) -> Registry:
    cache: dict[Path, dict[str, Any]] = {}
    envelope_path = messages_dir / "_envelope.json"
    envelope = _flatten(_load(envelope_path, cache), messages_dir, cache=cache)
    protocol = envelope.get("properties", {}).get("protocol", {}).get("const")
    if protocol is None:
        raise SchemaError("_envelope.json must define properties.protocol.const")

    payloads: dict[str, dict[str, Any]] = {}
    for path in sorted(messages_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        document = _load(path, cache)
        title = document.get("title")
        if not isinstance(title, str) or not title:
            raise SchemaError(f"{path.name} must define a title")
        full = _flatten(document, messages_dir, stack=frozenset({path.resolve()}), cache=cache)
        properties = full.get("properties", {})
        source = properties.get("source", {})
        # The host validates game -> host messages only; host -> game schemas
        # (ba:context, ba:result, ...) declare ``source: ba-host``. ``ba:error``
        # travels in both directions and carries no source const.
        if source.get("const") == "ba-host":
            continue
        payload = properties.get("payload")
        if not isinstance(payload, dict):
            raise SchemaError(f"{path.name} must define properties.payload")
        payloads[title] = payload

    return Registry(
        protocol=int(protocol),
        types=sorted(payloads),
        envelope=envelope,
        payloads=payloads,
    )


def _freeze_object(schema: dict[str, Any], indent: int) -> str:
    pad = "    " * indent
    raw = json.dumps(schema, indent=4, ensure_ascii=False, sort_keys=False)
    lines = raw.splitlines()
    if len(lines) == 1:
        return f"Object.freeze({raw})"
    body = "\n".join(pad + line for line in lines[1:-1])
    return f"Object.freeze({{\n{body}\n{pad}}})"


def render_registry(registry: Registry | None = None) -> str:
    registry = registry or build_registry()
    lines = [
        "/* GENERATED FILE - DO NOT EDIT.",
        " * Source of truth: schemas/messages/*.json (with $ref to schemas/eventlog.json).",
        " * Regenerate with: python3 scripts/generate_host_schemas.py",
        " */",
        "",
        f"export const PROTOCOL = {registry.protocol};",
        "",
        "export const SDK_MESSAGE_TYPES = Object.freeze([",
        *[f'    "{name}",' for name in registry.types],
        "]);",
        "",
        f"export const ENVELOPE_SCHEMA = {_freeze_object(registry.envelope, 0)};",
        "",
        "export const SDK_MESSAGE_SCHEMAS = Object.freeze({",
    ]
    for name in registry.types:
        lines.append(f'    "{name}": {_freeze_object(registry.payloads[name], 1)},')
    lines.extend(["})", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the artifact is stale")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)

    rendered = render_registry()
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        if current != rendered:
            print(f"{args.output} is out of date", file=sys.stderr)
            return 1
        return 0
    args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
