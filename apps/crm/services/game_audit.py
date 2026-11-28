"""Read-only per-game change history for the CRM game card (§2.16.2).

The section is a projection of ``AdminAuditLog`` rows written by publishing and
rollback. It performs no writes and exposes no moderation controls.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.core.paginator import Page, Paginator
from django.db.models import QuerySet

from apps.catalog.models import Game
from apps.crm.models import AdminAuditLog

AUDIT_PAGE_SIZE = 25


@dataclass(frozen=True)
class AuditRow:
    """One audit entry displayed by the read-only game card section."""

    action: str
    action_label: str
    actor_login: str | None
    occurred_at: datetime


@dataclass(frozen=True)
class GameAudit:
    """Bounded audit history page for one game card."""

    rows: tuple[AuditRow, ...]
    page_obj: Page[AdminAuditLog]

    @property
    def empty(self) -> bool:
        return not self.rows


def _page_number(raw: Any) -> int:
    """Blank, non-integer and non-positive input maps to the first page."""
    if raw is None:
        return 1
    value = str(raw).strip()
    if not value:
        return 1
    try:
        number = int(value)
    except ValueError:
        return 1
    return number if number >= 1 else 1


def _audit_queryset(game: Game) -> QuerySet[AdminAuditLog]:
    return (
        AdminAuditLog.objects.filter(
            object_type="game",
            object_id=game.id,
        )
        .select_related("actor")
        .order_by("-created_at", "-id")
    )


def build_game_audit(
    game: Game,
    *,
    page: Any = None,
    per_page: int = AUDIT_PAGE_SIZE,
) -> GameAudit:
    """Return a bounded, newest-first audit page for ``game``.

    Filtering by both ``object_type`` and ``object_id`` is the same query
    shape used by the publish-history check in
    :func:`apps.pipeline.services.rollback._was_published`.
    """
    page_obj: Page[AdminAuditLog] = Paginator(_audit_queryset(game), per_page).get_page(
        _page_number(page)
    )
    rows = tuple(
        AuditRow(
            action=entry.action,
            action_label=entry.get_action_display(),
            actor_login=entry.actor.login if entry.actor is not None else None,
            occurred_at=entry.created_at,
        )
        for entry in page_obj.object_list
    )
    return GameAudit(rows=rows, page_obj=page_obj)


__all__ = ["AUDIT_PAGE_SIZE", "AuditRow", "GameAudit", "build_game_audit"]
