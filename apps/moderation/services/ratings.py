"""Manual rating moderation (§2.9 item 4, §2.16.2 «Оценки»).

Hiding a vote keeps the row intact and only flips ``is_valid``; the denormalised
aggregate is recalculated transactionally, so catalog cards, the game detail
page and rating sorts immediately reflect the decision. Every change is
appended to the immutable CRM audit log with the mandatory reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.crm.models import AdminAuditLog
from apps.crm.permissions import MODERATION_MANAGE, has_capability
from apps.crm.services.audit import record_audit
from apps.ratings.models import GameRatingVote
from apps.ratings.services.aggregates import recalculate


@dataclass(frozen=True, slots=True)
class RatingModerationResult:
    """Outcome of a rating visibility decision."""

    ok: bool
    reason: str = ""
    vote: GameRatingVote | None = None
    audit: AdminAuditLog | None = None


def _snapshot(vote: GameRatingVote) -> dict[str, object]:
    return {
        "is_valid": vote.is_valid,
        "reason": vote.reason,
        "moderated_by_id": str(vote.moderated_by_id) if vote.moderated_by_id else None,
        "moderated_at": vote.moderated_at.isoformat() if vote.moderated_at else None,
    }


def set_rating_visibility(
    *,
    actor: User | None,
    vote_id: UUID,
    visible: bool,
    reason: str,
    ip: str | None = None,
) -> RatingModerationResult:
    """Hide (``visible=False``) or restore a rating with an audited reason.

    Defence in depth: the caller is checked again here even though the CRM view
    is already protected by ``role_required(MODERATION_MANAGE)``. A missing
    reason never changes state. Hiding is idempotent: repeating the same
    decision returns ``no_change`` and writes no audit row.
    """
    if not has_capability(actor, MODERATION_MANAGE):
        return RatingModerationResult(ok=False, reason="forbidden")
    cleaned_reason = (reason or "").strip()
    if not cleaned_reason:
        return RatingModerationResult(ok=False, reason="reason_required")
    if len(cleaned_reason) > 255:
        return RatingModerationResult(ok=False, reason="reason_too_long")

    with transaction.atomic():
        vote = (
            GameRatingVote.objects.select_for_update()
            .select_related("game")
            .filter(pk=vote_id)
            .first()
        )
        if vote is None:
            return RatingModerationResult(ok=False, reason="not_found")
        if vote.is_valid == visible:
            return RatingModerationResult(ok=False, reason="no_change", vote=vote)

        before = _snapshot(vote)
        vote.is_valid = visible
        vote.moderated_by = actor
        vote.reason = cleaned_reason
        vote.moderated_at = timezone.now()
        vote.save(update_fields=["is_valid", "moderated_by", "reason", "moderated_at"])
        recalculate(vote.game)
        audit = record_audit(
            actor=actor,
            action=(
                AdminAuditLog.ACTION_RATING_RESTORED
                if visible
                else AdminAuditLog.ACTION_RATING_HIDDEN
            ),
            object_type="rating",
            object_id=vote.pk,
            before=before,
            after=_snapshot(vote),
            reason=cleaned_reason,
            ip=ip,
        )
    return RatingModerationResult(ok=True, vote=vote, audit=audit)


__all__ = ["RatingModerationResult", "set_rating_visibility"]
