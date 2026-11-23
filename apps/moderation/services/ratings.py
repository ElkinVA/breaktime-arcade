"""Manual rating moderation (§2.9 item 4, §2.16.2 «Оценки»).

Hiding a vote keeps the row intact and only flips ``is_valid``; the denormalised
aggregate is recalculated transactionally, so catalog cards, the game detail
page and rating sorts immediately reflect the decision. Every change is
appended to the immutable CRM audit log with the mandatory reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import Avg, Count, Q, QuerySet
from django.utils import timezone

from apps.accounts.models import User
from apps.crm.models import AdminAuditLog
from apps.crm.permissions import MODERATION_MANAGE, has_capability
from apps.crm.services.audit import record_audit
from apps.ratings.models import GameRatingVote
from apps.ratings.services.aggregates import recalculate

STATUS_VALID = "valid"
STATUS_HIDDEN = "hidden"
RATING_STATUS_CHOICES = (
    (STATUS_VALID, "Допущена"),
    (STATUS_HIDDEN, "Скрыта"),
)
_RATING_STATUSES = frozenset(code for code, _label in RATING_STATUS_CHOICES)
RATING_VALUE_CHOICES = tuple(range(1, 6))


@dataclass(frozen=True, slots=True)
class RatingModerationResult:
    """Outcome of a rating visibility decision."""

    ok: bool
    reason: str = ""
    vote: GameRatingVote | None = None
    audit: AdminAuditLog | None = None


@dataclass(frozen=True, slots=True)
class RatingFilters:
    """Validated CRM rating queue filters. Unknown values are ignored."""

    game: str = ""
    value: int | None = None
    status: str = ""


@dataclass(frozen=True, slots=True)
class RatingSummary:
    """Average and per-value counts over the filtered vote rows."""

    count: int
    average: float
    distribution: dict[int, int]


def parse_rating_filters(params: Any) -> RatingFilters:
    """Read game/value/visibility filters; reject values outside the domain."""
    game = str(params.get("game") or "").strip()
    raw_value = str(params.get("value") or "").strip()
    value = int(raw_value) if raw_value.isdecimal() and 1 <= int(raw_value) <= 5 else None
    status = str(params.get("status") or "").strip().lower()
    if status not in _RATING_STATUSES:
        status = ""
    return RatingFilters(game=game, value=value, status=status)


def filter_rating_votes(filters: RatingFilters) -> QuerySet[GameRatingVote]:
    """Queue rows matching the filters, newest first, relations prefetched."""
    queryset = GameRatingVote.objects.select_related("game", "user", "moderated_by")
    if filters.game:
        queryset = queryset.filter(game__technical_id=filters.game)
    if filters.value is not None:
        queryset = queryset.filter(value=filters.value)
    if filters.status == STATUS_VALID:
        queryset = queryset.filter(is_valid=True)
    elif filters.status == STATUS_HIDDEN:
        queryset = queryset.filter(is_valid=False)
    # ``id`` is a UUIDv7, so it breaks equal-timestamp ties in insertion order
    # and keeps a page boundary stable while the moderator navigates.
    return queryset.order_by("-created_at", "-id")


def summarize_rating_votes(queryset: QuerySet[GameRatingVote]) -> RatingSummary:
    """Compute count/average/distribution in a single aggregate query."""
    row = queryset.order_by().aggregate(
        count=Count("id"),
        average=Avg("value"),
        **{f"value_{star}": Count("id", filter=Q(value=star)) for star in RATING_VALUE_CHOICES},
    )
    average = float(row["average"]) if row["average"] is not None else 0.0
    distribution = {star: int(row[f"value_{star}"] or 0) for star in RATING_VALUE_CHOICES}
    return RatingSummary(count=int(row["count"] or 0), average=average, distribution=distribution)


def rating_game_options() -> tuple[str, ...]:
    """Distinct technical ids that have votes, in a single ordered query."""
    return tuple(
        GameRatingVote.objects.order_by("game__technical_id")
        .values_list("game__technical_id", flat=True)
        .distinct()
    )


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


__all__ = [
    "RATING_STATUS_CHOICES",
    "RATING_VALUE_CHOICES",
    "RatingFilters",
    "RatingModerationResult",
    "RatingSummary",
    "filter_rating_votes",
    "parse_rating_filters",
    "rating_game_options",
    "set_rating_visibility",
    "summarize_rating_votes",
]
