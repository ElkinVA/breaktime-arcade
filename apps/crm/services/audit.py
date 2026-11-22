"""Append-only CRM audit writes (§2.16.1).

Callers wrap the privileged action and :func:`record_audit` in the same
database transaction so a failed audit write rolls the action back. The raw
client IP is never stored; only a SHA-256 hash is kept (TZ ``ip_hash``).
"""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

from apps.accounts.models import User
from apps.crm.models import AdminAuditLog


def hash_ip(value: str | None) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode()).hexdigest()


def record_audit(
    *,
    actor: User | None,
    action: str,
    object_type: str,
    object_id: UUID | None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str = "",
    ip: str | None = None,
) -> AdminAuditLog:
    """Append one audit row. Errors propagate so callers can roll back."""
    return AdminAuditLog.objects.create(
        actor=actor,
        action=action,
        object_type=object_type,
        object_id=object_id,
        before_data=before,
        after_data=after,
        reason=reason,
        ip_hash=hash_ip(ip),
    )


__all__ = ["hash_ip", "record_audit"]
