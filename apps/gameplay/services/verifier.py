"""Deterministic heuristic verifier baseline (§2.12.6)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from apps.gameplay.models import GameResult


@dataclass(frozen=True)
class Verdict:
    accepted: bool
    level: str
    flags: tuple[str, ...]
    quarantined: bool


def _profile(game, version) -> dict[str, Any]:
    verification = (version.manifest or {}).get("verification")
    if isinstance(verification, dict) and isinstance(verification.get("profile"), dict):
        return cast(dict[str, Any], verification["profile"])
    if isinstance(game.verification_profile, dict):
        return cast(dict[str, Any], game.verification_profile)
    return {}


def verify(
    *,
    game,
    version,
    event_log: object,
    value: int,
    duration_ms: int,
    is_test: bool,
) -> Verdict:
    """Apply declared bounds; suspicious results are quarantined, not deleted."""
    if is_test:
        return Verdict(True, GameResult.TRUST_CLIENT_REPORTED, (), False)
    profile = _profile(game, version)
    if not profile or not isinstance(event_log, dict):
        return Verdict(True, GameResult.TRUST_CLIENT_REPORTED, (), False)

    flags: list[str] = []
    seconds = max(duration_ms, 1000) / 1000
    max_points = profile.get("maxPointsPerSecond")
    if isinstance(max_points, (int, float)) and max_points > 0 and value / seconds > max_points:
        flags.append("points_per_second")

    max_idle = profile.get("maxIdleGapMs")
    events = event_log.get("events")
    if isinstance(max_idle, int) and max_idle >= 0 and isinstance(events, list):
        previous_t = 0
        max_gap = 0
        for event in events:
            if not isinstance(event, dict) or not isinstance(event.get("t"), int):
                continue
            current_t = event["t"]
            max_gap = max(max_gap, current_t - previous_t)
            previous_t = current_t
        if max_gap > max_idle:
            flags.append("idle_gap")

    verification = (version.manifest or {}).get("verification")
    schema = verification.get("eventSchema") if isinstance(verification, dict) else None
    if isinstance(schema, dict) and isinstance(events, list):
        validator = Draft202012Validator(schema)
        for event in events:
            try:
                if next(validator.iter_errors(event), None) is not None:
                    flags.append("event_schema")
                    break
            except Exception:  # noqa: BLE001 - malformed manifest schema is a config error
                flags.append("event_schema")
                break

    if flags:
        return Verdict(False, GameResult.TRUST_CLIENT_REPORTED, tuple(flags), True)

    max_level = game.trust_level_max
    level = (
        GameResult.TRUST_HEURISTIC_VALIDATED
        if max_level
        in {
            GameResult.TRUST_HEURISTIC_VALIDATED,
            GameResult.TRUST_REPLAY_VERIFIED,
            GameResult.TRUST_SERVER_AUTHORITATIVE,
        }
        else GameResult.TRUST_CLIENT_REPORTED
    )
    return Verdict(True, level, (), False)
