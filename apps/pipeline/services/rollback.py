"""Rollback to an earlier immutable version (§2.14.6, §2.14.9).

Rollback is the same atomic switch as publication; history is never rewritten
and ``published_at`` is preserved so the card keeps its original launch date.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from apps.catalog.models import Game, GameVersion


@dataclass(slots=True)
class RollbackResult:
    ok: bool
    reason: str = ""
    game: Game | None = None
    version: GameVersion | None = None


def rollback_version(game: Game, target: GameVersion) -> RollbackResult:
    if target.game_id != game.id:
        return RollbackResult(ok=False, reason="V_VERSION_NOT_IN_GAME", game=game, version=target)
    with transaction.atomic():
        locked = Game.objects.select_for_update().get(pk=game.pk)
        locked.current_version = target
        locked.status = Game.STATUS_PUBLISHED
        locked.save(update_fields=["current_version", "status", "updated_at"])
    game.refresh_from_db()
    return RollbackResult(ok=True, game=game, version=target)
