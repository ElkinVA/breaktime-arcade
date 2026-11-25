"""CRM glue for the game import wizard (§2.14.4–§2.14.7).

The existing pipeline service owns intake, validation, diff computation and
idempotent import. This module only adapts its persisted draft for the wizard:
the upload entry point, the diff projection and the publish-readiness view.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from apps.accounts.models import User
from apps.catalog.models import Game, GameVersion
from apps.pipeline.models import GameImportDraft
from apps.pipeline.services.importer import ImportResult, import_package
from apps.pipeline.services.publishing import autotest_passed


def upload_package(
    data: bytes,
    *,
    original_filename: str = "",
    created_by: User | None = None,
    target_game: Game | None = None,
) -> ImportResult:
    """Run the shared ZIP pipeline exactly as the public entry point does."""
    return import_package(
        data,
        original_filename=original_filename[:255],
        created_by=created_by,
        target_game=target_game,
    )


def get_draft(draft_id: UUID) -> GameImportDraft | None:
    return GameImportDraft.objects.select_related("game", "version").filter(pk=draft_id).first()


def _display(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError, ValueError:
        return str(value)


def _conflict_items(draft: GameImportDraft) -> list[Any]:
    conflicts = draft.conflicts
    if isinstance(conflicts, list) and conflicts:
        return conflicts
    report = draft.import_report
    if isinstance(report, dict):
        stored = report.get("conflicts")
        if isinstance(stored, list):
            return stored
    return []


def build_diff(draft: GameImportDraft) -> list[dict[str, str]]:
    """Project persisted import conflicts into table rows.

    Overridden CRM fields keep their value; the package value is shown as the
    incoming side together with the resolution recorded by the importer.
    """
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in _conflict_items(draft):
        if not isinstance(item, dict):
            continue
        scope = str(item.get("scope") or "")
        field = str(item.get("field") or "")
        key = (scope, field)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "scope": scope,
                "field": field,
                "current": _display(item.get("current")),
                "incoming": _display(item.get("incoming")),
                "resolution": str(item.get("resolution") or "keep"),
            }
        )
    return rows


def updated_fields(draft: GameImportDraft) -> list[str]:
    report = draft.import_report
    if not isinstance(report, dict):
        return []
    fields = report.get("updated_fields")
    if not isinstance(fields, list):
        return []
    return [str(field) for field in fields]


def _version_blockers(version: GameVersion) -> int:
    report = version.validation_report or {}
    summary = report.get("summary") if isinstance(report, dict) else None
    if isinstance(summary, dict):
        value = summary.get("blocker", 0)
        if isinstance(value, int):
            return value
    return 0 if report.get("ok", True) else 1


def _autotest_passed(version: GameVersion) -> bool:
    return autotest_passed(version)


@dataclass(frozen=True, slots=True)
class PublishReadiness:
    """Everything step 5 needs to decide whether publishing is offered."""

    ready: bool
    reasons: tuple[str, ...]
    blockers: int
    autotest_passed: bool
    is_current: bool
    version: GameVersion | None


def publish_readiness(draft: GameImportDraft) -> PublishReadiness:
    version = draft.version
    game = draft.game
    if version is None or game is None:
        return PublishReadiness(
            ready=False,
            reasons=("Версия ещё не импортирована.",),
            blockers=0,
            autotest_passed=False,
            is_current=False,
            version=None,
        )
    blockers = _version_blockers(version)
    autotest_passed = _autotest_passed(version)
    is_current = game.current_version_id == version.id
    reasons: list[str] = []
    if blockers:
        reasons.append(f"Валидация содержит блокирующие ошибки: {blockers}.")
    if not autotest_passed:
        reasons.append("Автотест версии не пройден.")
    if is_current:
        reasons.append("Эта версия уже опубликована.")
    return PublishReadiness(
        ready=not reasons,
        reasons=tuple(reasons),
        blockers=blockers,
        autotest_passed=autotest_passed,
        is_current=is_current,
        version=version,
    )
