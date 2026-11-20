"""Журнал входов/2FA без plaintext login и IP."""

from __future__ import annotations

import hashlib
import logging

from django.db import DatabaseError

from apps.accounts.models import LoginEvent, User

logger = logging.getLogger(__name__)


def _hash(value: str | None) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode()).hexdigest()


def record_login_event(
    *,
    event: str,
    user: User | None = None,
    subject: str = "",
    ip: str | None = None,
) -> None:
    try:
        LoginEvent.objects.create(
            user=user,
            subject_hash=_hash(subject.lower() if subject else ""),
            event=event,
            ip_hash=_hash(ip),
        )
    except DatabaseError:
        # Аудит не должен ломать вход; ошибка остаётся в логах.
        logger.warning("account.audit.record_failed", exc_info=True)
