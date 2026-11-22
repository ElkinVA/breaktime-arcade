"""Complaint intake and queue decisions (§2.16.2 «Жалобы», §2.23).

Complaints are created through the public ``POST /api/v1/reports`` endpoint and
processed by moderators/owners in the CRM. Assignment, resolution and rejection
require the ``moderation.manage`` capability, are serialized with a row lock
and append an immutable :class:`AdminAuditLog` entry in the same transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Game
from apps.crm.models import AdminAuditLog
from apps.crm.permissions import MODERATION_MANAGE, has_capability
from apps.crm.services.audit import record_audit
from apps.moderation.models import Complaint
from apps.ratings.models import GameRatingVote

_MAX_SUBJECT_LENGTH = 255


@dataclass(frozen=True, slots=True)
class ComplaintResult:
    """Outcome of a complaint intake or queue decision."""

    ok: bool
    reason: str = ""
    complaint: Complaint | None = None
    audit: AdminAuditLog | None = None


def _snapshot(complaint: Complaint) -> dict[str, object]:
    return {
        "status": complaint.status,
        "assigned_to_id": str(complaint.assigned_to_id) if complaint.assigned_to_id else None,
        "resolution": complaint.resolution,
        "resolved_at": complaint.resolved_at.isoformat() if complaint.resolved_at else None,
    }


def create_complaint(
    *,
    game: Game,
    reporter: User | None,
    subject: str,
    category: str = Complaint.CATEGORY_OTHER,
    rating: GameRatingVote | None = None,
) -> ComplaintResult:
    """Persist a complaint about a game or one of its rating votes.

    The caller (public API) resolves the game and rating first, so a mismatch
    here means an invalid request rather than a server error.
    """
    cleaned_subject = (subject or "").strip()
    if not cleaned_subject:
        return ComplaintResult(ok=False, reason="subject_required")
    if len(cleaned_subject) > _MAX_SUBJECT_LENGTH:
        return ComplaintResult(ok=False, reason="subject_too_long")
    if category not in {choice for choice, _label in Complaint.CATEGORY_CHOICES}:
        return ComplaintResult(ok=False, reason="invalid_category")
    if rating is not None and rating.game_id != game.pk:
        return ComplaintResult(ok=False, reason="invalid_rating")

    complaint = Complaint.objects.create(
        target_type=Complaint.TARGET_RATING if rating is not None else Complaint.TARGET_GAME,
        game=game,
        rating=rating,
        reporter=reporter if reporter is not None and reporter.is_authenticated else None,
        category=category,
        subject=cleaned_subject,
        status=Complaint.STATUS_NEW,
    )
    return ComplaintResult(ok=True, complaint=complaint)


def _locked_complaint(complaint_id: UUID) -> Complaint | None:
    return Complaint.objects.select_for_update().filter(pk=complaint_id).first()


def assign_complaint(
    *,
    actor: User | None,
    complaint_id: UUID,
    assignee_id: UUID | None = None,
    ip: str | None = None,
) -> ComplaintResult:
    """Assign an open complaint to an active moderator/owner."""
    if not has_capability(actor, MODERATION_MANAGE) or actor is None:
        return ComplaintResult(ok=False, reason="forbidden")

    with transaction.atomic():
        complaint = _locked_complaint(complaint_id)
        if complaint is None:
            return ComplaintResult(ok=False, reason="not_found")
        if complaint.status in Complaint.CLOSED_STATUSES:
            return ComplaintResult(ok=False, reason="closed")

        if assignee_id is None or assignee_id == actor.pk:
            assignee: User | None = actor
        else:
            assignee = User.objects.filter(
                pk=assignee_id,
                is_staff=True,
                is_active=True,
            ).first()
        if assignee is None:
            return ComplaintResult(ok=False, reason="assignee_not_found")
        if not has_capability(assignee, MODERATION_MANAGE):
            return ComplaintResult(ok=False, reason="invalid_assignee")
        same_assignee = (
            complaint.status == Complaint.STATUS_ASSIGNED
            and complaint.assigned_to_id == assignee.pk
        )
        if same_assignee:
            return ComplaintResult(ok=False, reason="no_change", complaint=complaint)

        before = _snapshot(complaint)
        complaint.assigned_to = assignee
        complaint.status = Complaint.STATUS_ASSIGNED
        complaint.save(update_fields=["assigned_to", "status", "updated_at"])
        audit = record_audit(
            actor=actor,
            action=AdminAuditLog.ACTION_COMPLAINT_ASSIGNED,
            object_type="complaint",
            object_id=complaint.pk,
            before=before,
            after=_snapshot(complaint),
            ip=ip,
        )
    return ComplaintResult(ok=True, complaint=complaint, audit=audit)


def _close_complaint(
    *,
    actor: User | None,
    complaint_id: UUID,
    resolution: str,
    status: str,
    action: str,
    ip: str | None,
) -> ComplaintResult:
    if not has_capability(actor, MODERATION_MANAGE) or actor is None:
        return ComplaintResult(ok=False, reason="forbidden")
    cleaned_resolution = (resolution or "").strip()
    if not cleaned_resolution:
        return ComplaintResult(ok=False, reason="resolution_required")

    with transaction.atomic():
        complaint = _locked_complaint(complaint_id)
        if complaint is None:
            return ComplaintResult(ok=False, reason="not_found")
        if complaint.status in Complaint.CLOSED_STATUSES:
            return ComplaintResult(ok=False, reason="closed", complaint=complaint)

        before = _snapshot(complaint)
        complaint.status = status
        complaint.resolution = cleaned_resolution
        complaint.resolved_at = timezone.now()
        complaint.save(update_fields=["status", "resolution", "resolved_at", "updated_at"])
        audit = record_audit(
            actor=actor,
            action=action,
            object_type="complaint",
            object_id=complaint.pk,
            before=before,
            after=_snapshot(complaint),
            reason=cleaned_resolution,
            ip=ip,
        )
    return ComplaintResult(ok=True, complaint=complaint, audit=audit)


def resolve_complaint(
    *,
    actor: User | None,
    complaint_id: UUID,
    resolution: str,
    ip: str | None = None,
) -> ComplaintResult:
    """Close a complaint as resolved with a mandatory resolution note."""
    return _close_complaint(
        actor=actor,
        complaint_id=complaint_id,
        resolution=resolution,
        status=Complaint.STATUS_RESOLVED,
        action=AdminAuditLog.ACTION_COMPLAINT_RESOLVED,
        ip=ip,
    )


def reject_complaint(
    *,
    actor: User | None,
    complaint_id: UUID,
    resolution: str,
    ip: str | None = None,
) -> ComplaintResult:
    """Close a complaint as rejected with a mandatory resolution note."""
    return _close_complaint(
        actor=actor,
        complaint_id=complaint_id,
        resolution=resolution,
        status=Complaint.STATUS_REJECTED,
        action=AdminAuditLog.ACTION_COMPLAINT_REJECTED,
        ip=ip,
    )


__all__ = [
    "ComplaintResult",
    "assign_complaint",
    "create_complaint",
    "reject_complaint",
    "resolve_complaint",
]
