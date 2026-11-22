"""Publication of an immutable version (§2.14.9).

Publication is a single atomic switch of ``Game.current_version``. A version
is publishable only when validation has no blockers and the autotest report is
green; an owner override requires an explicit ``force`` flag and is recorded
in the draft/version reports by the CRM layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Game, GameVersion


@dataclass(slots=True)
class PublishResult:
    ok: bool
    reason: str = ""
    game: Game | None = None
    version: GameVersion | None = None


def _validation_blockers(version: GameVersion) -> int:
    report = version.validation_report or {}
    summary = report.get("summary") if isinstance(report, dict) else None
    if isinstance(summary, dict):
        value = summary.get("blocker", 0)
        if isinstance(value, int):
            return value
    return 0 if report.get("ok", True) else 1


def _autotest_passed(version: GameVersion) -> bool:
    report = version.e2e_report or {}
    return bool(report.get("passed"))


def publish_version(
    game: Game,
    version: GameVersion,
    *,
    force: bool = False,
    now: datetime | None = None,
) -> PublishResult:
    if version.game_id != game.id:
        return PublishResult(ok=False, reason="V_VERSION_NOT_IN_GAME", game=game, version=version)
    if not force:
        if _validation_blockers(version):
            return PublishResult(
                ok=False, reason="V_VALIDATION_BLOCKED", game=game, version=version
            )
        if not _autotest_passed(version):
            return PublishResult(ok=False, reason="V_AUTOTEST_FAILED", game=game, version=version)

    timestamp = now or timezone.now()
    with transaction.atomic():
        locked = Game.objects.select_for_update().get(pk=game.pk)
        locked.current_version = version
        locked.status = Game.STATUS_PUBLISHED
        if locked.published_at is None:
            locked.published_at = timestamp
        locked.save(update_fields=["current_version", "status", "published_at", "updated_at"])
    game.refresh_from_db()
    return PublishResult(ok=True, game=game, version=version)


def schedule_publish(
    game: Game,
    version: GameVersion,
    publish_at: datetime,
) -> PublishResult:
    """Set a future ``publish_at``; a Celery beat task performs the switch."""
    if version.game_id != game.id:
        return PublishResult(ok=False, reason="V_VERSION_NOT_IN_GAME", game=game, version=version)
    if not _autotest_passed(version):
        return PublishResult(ok=False, reason="V_AUTOTEST_FAILED", game=game, version=version)
    with transaction.atomic():
        locked = Game.objects.select_for_update().get(pk=game.pk)
        locked.publish_at = publish_at
        locked.save(update_fields=["publish_at", "updated_at"])
    game.refresh_from_db()
    return PublishResult(ok=True, game=game, version=version)
