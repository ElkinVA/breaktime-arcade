"""Staff role and status changes with lockout protection (§2.16, §2.16.1).

Only an owner may mutate staff accounts. Every change requires step-up in the
view layer, is serialized with ``SELECT ... FOR UPDATE`` and is appended to the
audit trail inside the same transaction. Two invariants are enforced here:

* an actor cannot demote or deactivate themselves (self-lockout);
* the last active owner cannot be demoted or deactivated.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import StaffRole, User
from apps.crm.models import AdminAuditLog
from apps.crm.permissions import USERS_MANAGE, has_capability, valid_roles
from apps.crm.services.audit import record_audit


@dataclass(frozen=True, slots=True)
class StaffChangeResult:
    ok: bool
    reason: str = ""
    audit: AdminAuditLog | None = None


def _locked_target(
    target_id: UUID,
    actor_id: UUID,
) -> tuple[User | None, User | None, list[User]]:
    """Lock the target, the actor and all active owners in a stable order."""
    rows = list(
        User.objects.select_for_update()
        .filter(
            Q(pk=target_id)
            | Q(pk=actor_id)
            | Q(is_staff=True, is_active=True, crm_role=StaffRole.OWNER)
        )
        .order_by("id")
    )
    target = next((row for row in rows if row.pk == target_id), None)
    locked_actor = next((row for row in rows if row.pk == actor_id), None)
    owners = [
        row for row in rows if row.is_staff and row.is_active and row.crm_role == StaffRole.OWNER
    ]
    return target, locked_actor, owners


def _guard(actor: User, target: User) -> str:
    if not has_capability(actor, USERS_MANAGE):
        return "forbidden"
    if not target.is_staff:
        return "not_staff"
    if actor.pk == target.pk:
        return "self_lockout"
    return ""


def _snapshot(user: User) -> dict[str, object]:
    return {"crm_role": user.crm_role, "is_active": user.is_active}


def change_staff_role(
    *,
    actor: User,
    target_id: UUID,
    role: str,
    ip: str | None = None,
    reason: str = "",
) -> StaffChangeResult:
    """Assign a TZ role to a staff account, guarding the last owner."""
    if role not in valid_roles():
        return StaffChangeResult(ok=False, reason="invalid_role")
    with transaction.atomic():
        target, locked_actor, active_owners = _locked_target(target_id, actor.pk)
        if target is None or locked_actor is None:
            return StaffChangeResult(ok=False, reason="not_found")
        guard = _guard(locked_actor, target)
        if guard:
            return StaffChangeResult(ok=False, reason=guard)
        if target.crm_role == role:
            return StaffChangeResult(ok=False, reason="no_change")
        if (
            target.crm_role == StaffRole.OWNER
            and target.is_active
            and role != StaffRole.OWNER
            and len(active_owners) <= 1
        ):
            return StaffChangeResult(ok=False, reason="last_owner")

        before = _snapshot(target)
        target.crm_role = role
        target.updated_at = timezone.now()
        target.save(update_fields=["crm_role", "updated_at"])
        audit = record_audit(
            actor=actor,
            action=AdminAuditLog.ACTION_STAFF_ROLE_CHANGED,
            object_type="user",
            object_id=target.pk,
            before=before,
            after=_snapshot(target),
            reason=reason,
            ip=ip,
        )
    return StaffChangeResult(ok=True, audit=audit)


def set_staff_active(
    *,
    actor: User,
    target_id: UUID,
    is_active: bool,
    ip: str | None = None,
    reason: str = "",
) -> StaffChangeResult:
    """Activate/deactivate a staff account, guarding the last owner."""
    with transaction.atomic():
        target, locked_actor, active_owners = _locked_target(target_id, actor.pk)
        if target is None or locked_actor is None:
            return StaffChangeResult(ok=False, reason="not_found")
        guard = _guard(locked_actor, target)
        if guard:
            return StaffChangeResult(ok=False, reason=guard)
        if target.is_active == is_active:
            return StaffChangeResult(ok=False, reason="no_change")
        if (
            not is_active
            and target.crm_role == StaffRole.OWNER
            and target.is_active
            and len(active_owners) <= 1
        ):
            return StaffChangeResult(ok=False, reason="last_owner")

        before = _snapshot(target)
        target.is_active = is_active
        target.updated_at = timezone.now()
        target.save(update_fields=["is_active", "updated_at"])
        audit = record_audit(
            actor=actor,
            action=(
                AdminAuditLog.ACTION_STAFF_ACTIVATED
                if is_active
                else AdminAuditLog.ACTION_STAFF_DEACTIVATED
            ),
            object_type="user",
            object_id=target.pk,
            before=before,
            after=_snapshot(target),
            reason=reason,
            ip=ip,
        )
    return StaffChangeResult(ok=True, audit=audit)


__all__ = ["StaffChangeResult", "change_staff_role", "set_staff_active"]
