"""Safe CSV/JSON exports of the local analytics snapshot (§2.18, §2.16.1).

The payload is deliberately narrow: aggregate counters and published game
identifiers only. It contains no account identifiers, emails, IP addresses,
package/runtime hashes, secrets or unpublished game data. CSV cells are
formula-neutralised before writing.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from apps.analytics.services.aggregates import AnalyticsSnapshot
from apps.core.services.export_safety import csv_cell

EXPORT_FORMATS = frozenset({"csv", "json"})
_CSV_HEADER = ("section", "item", "metric", "value")


class AnalyticsExportError(ValueError):
    """Unknown export format requested by the caller."""


def snapshot_payload(snapshot: AnalyticsSnapshot) -> dict[str, Any]:
    """Return the public, PII-free JSON structure behind the export."""
    return {
        "date_from": snapshot.date_from.isoformat(),
        "date_to": snapshot.date_to.isoformat(),
        "games": {
            "published": snapshot.published_games,
            "new_in_range": snapshot.new_games,
        },
        "sessions": {
            "total": snapshot.sessions,
            "user": snapshot.user_sessions,
            "guest": snapshot.guest_sessions,
            "finished": snapshot.finished_sessions,
            "completion_rate": snapshot.completion_rate,
        },
        "plays": snapshot.plays,
        "ratings": {
            "votes": snapshot.rating_votes,
            "average": snapshot.average_rating,
        },
        "complaints": {
            "total": snapshot.complaints,
            "open": snapshot.open_complaints,
            "resolved": snapshot.resolved_complaints,
        },
        "top_games": [
            {
                "technical_id": game.technical_id,
                "slug": game.slug,
                "sessions": game.sessions,
                "unique_sessions": game.unique_sessions,
                "completions": game.completions,
            }
            for game in snapshot.top_games
        ],
    }


def _metric_rows(snapshot: AnalyticsSnapshot) -> list[tuple[str, str, str, object]]:
    rows: list[tuple[str, str, str, object]] = [
        ("range", "", "date_from", snapshot.date_from.isoformat()),
        ("range", "", "date_to", snapshot.date_to.isoformat()),
        ("games", "", "published", snapshot.published_games),
        ("games", "", "new_in_range", snapshot.new_games),
        ("sessions", "", "total", snapshot.sessions),
        ("sessions", "", "user", snapshot.user_sessions),
        ("sessions", "", "guest", snapshot.guest_sessions),
        ("sessions", "", "finished", snapshot.finished_sessions),
        ("sessions", "", "completion_rate", snapshot.completion_rate),
        ("plays", "", "total", snapshot.plays),
        ("ratings", "", "votes", snapshot.rating_votes),
        ("ratings", "", "average", snapshot.average_rating),
        ("complaints", "", "total", snapshot.complaints),
        ("complaints", "", "open", snapshot.open_complaints),
        ("complaints", "", "resolved", snapshot.resolved_complaints),
    ]
    for game in snapshot.top_games:
        for metric, value in (
            ("slug", game.slug),
            ("sessions", game.sessions),
            ("unique_sessions", game.unique_sessions),
            ("completions", game.completions),
        ):
            rows.append(("top_games", game.technical_id, metric, value))
    return rows


def export_csv(snapshot: AnalyticsSnapshot) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(_CSV_HEADER)
    for row in _metric_rows(snapshot):
        writer.writerow([csv_cell(cell) for cell in row])
    return buffer.getvalue()


def _formula_safe_json(value: Any) -> Any:
    """Recursively neutralise formula-leading strings in the JSON payload."""
    if isinstance(value, str):
        return csv_cell(value)
    if isinstance(value, dict):
        return {key: _formula_safe_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_formula_safe_json(item) for item in value]
    return value


def export_json(snapshot: AnalyticsSnapshot) -> str:
    payload = _formula_safe_json(snapshot_payload(snapshot))
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def export_filename(snapshot: AnalyticsSnapshot, report_format: str) -> str:
    start = snapshot.date_from.isoformat()
    end = snapshot.date_to.isoformat()
    return f"analytics-{start}-{end}.{report_format}"


def render_export(
    snapshot: AnalyticsSnapshot,
    report_format: str,
) -> tuple[str, str, str]:
    """Return ``(content, content_type, filename)`` for a validated format."""
    normalised = report_format.strip().lower()
    if normalised not in EXPORT_FORMATS:
        raise AnalyticsExportError(normalised)
    if normalised == "csv":
        return (
            export_csv(snapshot),
            "text/csv; charset=utf-8",
            export_filename(snapshot, normalised),
        )
    return (
        export_json(snapshot),
        "application/json; charset=utf-8",
        export_filename(snapshot, normalised),
    )


__all__ = [
    "AnalyticsExportError",
    "EXPORT_FORMATS",
    "export_csv",
    "export_filename",
    "export_json",
    "render_export",
    "snapshot_payload",
]
