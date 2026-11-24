"""Safe rollback to a previously published version (§2.14.9, directive §4.2).

A rollback is not a way around publication checks: the target must already
appear in the append-only publication history, must pass validation and the
autotest gate, and must use the same score rules as the current published
version. The game status (including hidden/archived) is preserved; rollback
never re-publishes a hidden card by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction

from apps.catalog.models import Game, GameVersion
from apps.pipeline.services.publishing import (
    _autotest_passed,
    _record_publication,
    _validation_blockers,
)

ROLLBACK_STATUSES = {Game.STATUS_PUBLISHED, Game.STATUS_HIDDEN, Game.STATUS_ARCHIVED}


@dataclass(slots=True)
class RollbackResult:
    ok: bool
    reason: str = ""
    game: Game | None = None
    version: GameVersion | None = None


def _was_published(game: Game, target: GameVersion) -> bool:
    from apps.crm.models import AdminAuditLog

    return AdminAuditLog.objects.filter(
        action=AdminAuditLog.ACTION_GAME_PUBLISHED,
        object_type="game",
        object_id=game.id,
        after_data__current_version_id=str(target.id),
    ).exists()


def _score_rules(version: GameVersion) -> tuple[str, int]:
    manifest = version.manifest or {}
    score = manifest.get("score") if isinstance(manifest, dict) else None
    if not isinstance(score, dict):
        score = {}
    direction = str(score.get("direction", "higher_is_better"))
    raw_schema = score.get("schemaVersion", 1)
    # Match the importer's coercion: only JSON numbers become schema versions.
    schema_version = int(raw_schema) if isinstance(raw_schema, (int, float)) else 1
    return direction, schema_version


def _current_score_rules(game: Game) -> tuple[str, int]:
    """Rules of the current published version; Game fields only as a fallback."""
    if game.current_version is not None:
        return _score_rules(game.current_version)
    return game.score_direction, game.score_schema_version


def rollback_version(
    game: Game,
    target: GameVersion,
    *,
    actor: Any | None = None,
    ip: str | None = None,
) -> RollbackResult:
    if target.game_id != game.id:
        return RollbackResult(ok=False, reason="V_VERSION_NOT_IN_GAME", game=game, version=target)
    with transaction.atomic():
        locked = Game.objects.select_for_update().get(pk=game.pk)
        if locked.status not in ROLLBACK_STATUSES:
            return RollbackResult(
                ok=False, reason="V_GAME_NOT_PUBLISHED", game=game, version=target
            )
        if not _was_published(locked, target):
            return RollbackResult(ok=False, reason="V_NOT_PUBLISHED", game=game, version=target)
        if _validation_blockers(target):
            return RollbackResult(
                ok=False, reason="V_VALIDATION_BLOCKED", game=game, version=target
            )
        if not _autotest_passed(target):
            return RollbackResult(ok=False, reason="V_AUTOTEST_FAILED", game=game, version=target)
        target_direction, target_schema = _score_rules(target)
        current_direction, current_schema = _current_score_rules(locked)
        if target_direction != current_direction or target_schema != current_schema:
            return RollbackResult(
                ok=False, reason="V_SCORE_RULES_CHANGED", game=game, version=target
            )

        before = {
            "status": locked.status,
            "current_version_id": (
                str(locked.current_version_id) if locked.current_version_id else None
            ),
        }
        locked.current_version = target
        locked.save(update_fields=["current_version", "updated_at"])
        _record_publication(
            action="game.rolled_back",
            game=locked,
            version=target,
            before=before,
            actor=actor,
            ip=ip,
        )
    game.refresh_from_db()
    return RollbackResult(ok=True, game=game, version=target)
