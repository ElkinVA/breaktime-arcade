"""Validation/import report rendering for the CRM wizard (§2.14.7).

Reports are built from persisted draft/version JSON only: no filesystem paths
and no server secrets are included. CSV cells are neutralised against
spreadsheet formula injection, and every download is served as a fixed-name
attachment by the export layer.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from apps.pipeline.models import GameImportDraft

REPORT_FORMATS = frozenset({"json", "csv"})
_CSV_COLUMNS = ("code", "severity", "file", "message", "hint")
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def report_payload(draft: GameImportDraft) -> dict[str, Any]:
    """Return the safe JSON structure behind the report download."""
    return {
        "draft": {
            "id": str(draft.id),
            "status": draft.status,
            "original_filename": draft.original_filename,
            "size_bytes": draft.size_bytes,
            "created_at": draft.created_at.isoformat() if draft.created_at else None,
        },
        "package": {"package_hash": draft.package_hash},
        "validation": draft.validation_report or {},
        "import": draft.import_report or {},
        "injection": draft.injection_report or {},
        "autotest": draft.e2e_report or {},
        "conflicts": draft.conflicts or [],
    }


def _diagnostics(draft: GameImportDraft) -> list[dict[str, Any]]:
    report = draft.validation_report
    if isinstance(report, dict):
        items = report.get("diagnostics")
        if isinstance(items, list) and items:
            return [item for item in items if isinstance(item, dict)]
    stored = draft.diagnostics
    if isinstance(stored, list):
        return [item for item in stored if isinstance(item, dict)]
    return []


def diagnostic_rows(draft: GameImportDraft) -> list[dict[str, str]]:
    """Normalise persisted diagnostics for the wizard table."""
    rows: list[dict[str, str]] = []
    for item in _diagnostics(draft):
        rows.append(
            {
                "code": _safe_text(item.get("code")),
                "severity": _safe_text(item.get("severity")),
                "file": _safe_text(item.get("file")),
                "message": _safe_text(item.get("message")),
                "hint": _safe_text(item.get("hint")),
            }
        )
    return rows


def _safe_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError, ValueError:
        return str(value)


def csv_cell(value: object) -> str:
    """Neutralise spreadsheet formulas while preserving normal text."""
    text = _safe_text(value)
    if text.startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


def report_json(draft: GameImportDraft) -> str:
    return json.dumps(report_payload(draft), ensure_ascii=False, indent=2, sort_keys=True)


def report_csv(draft: GameImportDraft) -> str:
    """Render one diagnostic per row; user-controlled cells are neutralised."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(_CSV_COLUMNS)
    for item in _diagnostics(draft):
        writer.writerow(
            [
                csv_cell(item.get("code")),
                csv_cell(item.get("severity")),
                csv_cell(item.get("file")),
                csv_cell(item.get("message")),
                csv_cell(item.get("hint")),
            ]
        )
    return buffer.getvalue()


def render_report(draft: GameImportDraft, report_format: str) -> tuple[str, str]:
    """Return ``(content, content_type)`` for a validated format token."""
    if report_format == "csv":
        return report_csv(draft), "text/csv; charset=utf-8"
    return report_json(draft), "application/json; charset=utf-8"
