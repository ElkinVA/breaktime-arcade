"""Least-privilege capability matrix for CRM staff roles (§2.16).

The four TZ roles are stored in ``User.crm_role``. Capabilities are checked by
CRM views/decorators and mirror §2.16:

* owner — everything, including staff roles and publication;
* editor — games, import/update wizard, content, genres/tags/translations;
* moderator — moderation of ratings, nicknames, results and complaints;
* observer — read-only statistics and journals.

No capability implies another; a roleless staff account has no CRM access.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from apps.accounts.models import StaffRole

# Capability identifiers are stable strings so they can be audited/logged.
GAMES_VIEW = "games.view"
GAMES_IMPORT = "games.import"
GAMES_PUBLISH = "games.publish"
USERS_MANAGE = "users.manage"
CONTENT_MANAGE = "content.manage"
MODERATION_MANAGE = "moderation.manage"
ANALYTICS_VIEW = "analytics.view"
AUDIT_VIEW = "audit.view"

ALL_CAPABILITIES = frozenset(
    {
        GAMES_VIEW,
        GAMES_IMPORT,
        GAMES_PUBLISH,
        USERS_MANAGE,
        CONTENT_MANAGE,
        MODERATION_MANAGE,
        ANALYTICS_VIEW,
        AUDIT_VIEW,
    }
)

ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    StaffRole.OWNER: ALL_CAPABILITIES,
    StaffRole.EDITOR: frozenset({GAMES_VIEW, GAMES_IMPORT, CONTENT_MANAGE}),
    StaffRole.MODERATOR: frozenset({MODERATION_MANAGE}),
    StaffRole.OBSERVER: frozenset({ANALYTICS_VIEW, AUDIT_VIEW}),
}

ROLE_HOME_NAMES: dict[str, str] = {
    StaffRole.OWNER: "crm:dashboard",
    StaffRole.EDITOR: "crm:games",
    StaffRole.MODERATOR: "crm:moderation",
    StaffRole.OBSERVER: "crm:dashboard",
}


def is_staff_user(user: Any) -> bool:
    """Return ``True`` only for authenticated Django staff accounts."""
    return bool(getattr(user, "is_authenticated", False) and getattr(user, "is_staff", False))


def active_role(user: Any) -> str:
    """Return the CRM role for a staff account, or ``""`` when unavailable."""
    if not is_staff_user(user):
        return ""
    role = str(getattr(user, "crm_role", "") or "")
    return role if role in ROLE_CAPABILITIES else ""


def capabilities_for(user: Any) -> frozenset[str]:
    """Return the capability set granted to ``user`` (empty when denied)."""
    role = active_role(user)
    return ROLE_CAPABILITIES.get(role, frozenset())


def has_capability(user: Any, capability: str) -> bool:
    """True when the account is staff, has a role and is granted the capability."""
    return capability in capabilities_for(user)


def has_any_capability(user: Any, capabilities: Iterable[str]) -> bool:
    granted = capabilities_for(user)
    return any(capability in granted for capability in capabilities)


def role_home_name(user: Any) -> str | None:
    """Django URL name of the landing screen for ``user``'s role."""
    return ROLE_HOME_NAMES.get(active_role(user))


def valid_roles() -> tuple[str, ...]:
    return tuple(ROLE_CAPABILITIES)


__all__ = [
    "ALL_CAPABILITIES",
    "ANALYTICS_VIEW",
    "AUDIT_VIEW",
    "CONTENT_MANAGE",
    "GAMES_IMPORT",
    "GAMES_PUBLISH",
    "GAMES_VIEW",
    "MODERATION_MANAGE",
    "ROLE_CAPABILITIES",
    "ROLE_HOME_NAMES",
    "USERS_MANAGE",
    "active_role",
    "capabilities_for",
    "has_any_capability",
    "has_capability",
    "is_staff_user",
    "role_home_name",
    "valid_roles",
]
