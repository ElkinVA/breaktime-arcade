"""Import diff and CRM override handling (§2.14.4, Приложение J)."""

from __future__ import annotations

from typing import Any

GAME_MANIFEST_FIELDS: dict[str, str] = {
    "mobile_support": "mobileSupport",
    "orientation": "orientation",
    "estimated_play_minutes": "estimatedPlayMinutes",
    "leaderboard_enabled": "leaderboardEnabled",
}
TRANSLATION_CATALOG_FIELDS: dict[str, str] = {
    "name": "name",
    "short_description": "shortDescription",
    "description": "description",
    "instructions": "instructions",
    "controls": "controls",
    "seo_title": "seoTitle",
    "seo_description": "seoDescription",
}


def conflict(
    *,
    scope: str,
    field: str,
    current: Any,
    incoming: Any,
) -> dict[str, Any]:
    return {
        "scope": scope,
        "field": field,
        "current": current,
        "incoming": incoming,
        "resolution": "keep",
    }


def translation_values(catalog: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field, source in TRANSLATION_CATALOG_FIELDS.items():
        value = catalog.get(source)
        if value is not None:
            values[field] = value
    return values


def split_updates(
    *,
    scope: str,
    current: dict[str, Any],
    incoming: dict[str, Any],
    overridden: set[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return fields to update and conflicts for overridden fields.

    Overridden fields are never overwritten: their CRM value is kept and the
    package value is recorded as a conflict for the CRM diff screen.
    """
    updates: dict[str, Any] = {}
    conflicts: list[dict[str, Any]] = []
    for field, value in incoming.items():
        if field in overridden:
            existing = current.get(field)
            if existing != value:
                conflicts.append(
                    conflict(scope=scope, field=field, current=existing, incoming=value)
                )
            continue
        if current.get(field) != value:
            updates[field] = value
    return updates, conflicts


def game_manifest_values(manifest: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field, source in GAME_MANIFEST_FIELDS.items():
        raw = manifest.get(source)
        if source == "leaderboardEnabled":
            leaderboard = manifest.get("leaderboard")
            raw = leaderboard.get("enabled") if isinstance(leaderboard, dict) else None
        if raw is not None:
            values[field] = raw
    theme = manifest.get("theme")
    if isinstance(theme, dict) and isinstance(theme.get("accent"), str):
        values["accent_color"] = theme["accent"]
    credits = manifest.get("credits")
    if isinstance(credits, list):
        values["credits"] = credits
    return values
