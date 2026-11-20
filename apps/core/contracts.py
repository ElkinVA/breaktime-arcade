"""Семантические проверки контрактов этапа 0.

JSON Schema проверяет структуру; этот модуль — только правила, которые
не выражаются стандартной схемой: membership языков, количество alt,
монотонность eventLog, размеры gzip и направления сообщений.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from django.conf import settings
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

SCHEMA_DIR = Path(settings.BASE_DIR) / "schemas"
MAX_EVENTLOG_EVENTS = 20_000
MAX_EVENTLOG_RAW_BYTES = 2 * 1024 * 1024
MAX_EVENTLOG_GZIP_BYTES = 256 * 1024

MESSAGE_SCHEMAS = {
    "ba:hello": "messages/ba_hello.json",
    "ba:submit": "messages/ba_submit.json",
    "ba:leaderboard": "messages/ba_leaderboard.json",
    "ba:storage": "messages/ba_storage.json",
    "ba:newSession": "messages/ba_new_session.json",
    "ba:exit": "messages/ba_exit.json",
    "ba:error": "messages/ba_error.json",
    "ba:context": "messages/ba_context.json",
    "ba:result": "messages/ba_result.json",
    "ba:leaderboard:data": "messages/ba_leaderboard_data.json",
    "ba:storage:data": "messages/ba_storage_data.json",
    "ba:session": "messages/ba_session.json",
    "ba:pause": "messages/ba_pause.json",
    "ba:resume": "messages/ba_resume.json",
}


def load_schema(relative_name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((SCHEMA_DIR / relative_name).read_text(encoding="utf-8"))
    return data


def _registry() -> Registry:
    registry = Registry()
    for path in SCHEMA_DIR.rglob("*.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        schema_id = schema.get("$id")
        if isinstance(schema_id, str):
            registry = registry.with_resource(
                schema_id,
                Resource.from_contents(schema, default_specification=DRAFT202012),
            )
    return registry


def validate_schema(relative_name: str, instance: Any) -> list[str]:
    schema = load_schema(relative_name)
    validator = Draft202012Validator(
        schema,
        registry=_registry(),
        format_checker=FormatChecker(),
    )
    return [error.message for error in validator.iter_errors(instance)]


def validate_manifest_semantics(
    manifest: Mapping[str, Any],
    catalog: Mapping[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    languages = manifest.get("supportedLanguages")
    default_language = manifest.get("defaultLanguage")
    if (
        isinstance(languages, list)
        and isinstance(default_language, str)
        and default_language not in languages
    ):
        errors.append("defaultLanguage must be present in supportedLanguages")

    assets = manifest.get("assets")
    if isinstance(assets, Mapping) and isinstance(default_language, str):
        critical = assets.get("critical")
        if isinstance(critical, list):
            expected_locale = f"locales/{default_language}.json"
            if expected_locale not in critical:
                errors.append(f"assets.critical must include {expected_locale}")

    score = manifest.get("score")
    if isinstance(score, Mapping):
        minimum = score.get("minValue")
        maximum = score.get("maxValue")
        if (
            isinstance(minimum, (int, float))
            and isinstance(maximum, (int, float))
            and minimum > maximum
        ):
            errors.append("score.minValue must be <= score.maxValue")

    limits = manifest.get("limits")
    if isinstance(limits, Mapping):
        minimum = limits.get("minPlaytimeSeconds")
        maximum = limits.get("maxSessionSeconds")
        if isinstance(minimum, int) and isinstance(maximum, int) and minimum > maximum:
            errors.append("limits.minPlaytimeSeconds must be <= maxSessionSeconds")

    leaderboard = manifest.get("leaderboard")
    if (
        isinstance(leaderboard, Mapping)
        and leaderboard.get("claimedVerification") == "replay_verified"
        and "verification" not in manifest
    ):
        errors.append("replay_verified requires verification block")

    if catalog is not None:
        images = assets.get("screenshots") if isinstance(assets, Mapping) else None
        alts = catalog.get("screenshotAlts")
        if isinstance(images, list) and isinstance(alts, list) and len(images) != len(alts):
            errors.append("catalog.screenshotAlts length must match assets.screenshots")

    return errors


def validate_catalog_semantics(
    manifest: Mapping[str, Any],
    catalog: Mapping[str, Any],
) -> list[str]:
    return validate_manifest_semantics(manifest, catalog)


def validate_eventlog_semantics(
    eventlog: Mapping[str, Any],
    event_kinds: Sequence[str],
    duration_ms: int | None = None,
) -> list[str]:
    errors: list[str] = []
    events = eventlog.get("events")
    if not isinstance(events, list):
        return ["events must be a list"]
    if len(events) > MAX_EVENTLOG_EVENTS:
        errors.append(f"eventLog has more than {MAX_EVENTLOG_EVENTS} events")

    allowed = set(event_kinds)
    previous_t = -1
    for index, event in enumerate(events):
        if not isinstance(event, Mapping):
            errors.append(f"event[{index}] must be an object")
            continue
        t = event.get("t")
        kind = event.get("k")
        if isinstance(t, int):
            if t < previous_t:
                errors.append(f"event[{index}].t must be monotonic")
            previous_t = max(previous_t, t)
            if duration_ms is not None and t > duration_ms + 1000:
                errors.append(f"event[{index}].t exceeds durationMs + 1000")
        else:
            errors.append(f"event[{index}].t must be an integer")
        if isinstance(kind, str) and kind not in allowed:
            errors.append(f"event[{index}].k is not declared in eventKinds")

    raw = json.dumps(eventlog, separators=(",", ":"), ensure_ascii=False).encode()
    if len(raw) > MAX_EVENTLOG_RAW_BYTES:
        errors.append("eventLog exceeds 2 MiB raw")
    compressed = gzip.compress(raw)
    if len(compressed) > MAX_EVENTLOG_GZIP_BYTES:
        errors.append("eventLog exceeds 256 KiB gzip")
    return errors


def validate_message_semantics(message: Mapping[str, Any]) -> list[str]:
    message_type = message.get("type")
    if not isinstance(message_type, str) or message_type not in MESSAGE_SCHEMAS:
        return ["message type is not in the App F allowlist"]
    return validate_schema(MESSAGE_SCHEMAS[message_type], message)
