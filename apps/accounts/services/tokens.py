"""Одноразовые токены email/password reset; в БД только хеш."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.utils import timezone

from apps.accounts.models import AccountToken, User


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def issue_token(
    user: User,
    purpose: str,
    *,
    ttl_seconds: int,
    email: str = "",
) -> str:
    raw = secrets.token_urlsafe(32)
    AccountToken.objects.create(
        user=user,
        purpose=purpose,
        email=email,
        token_hash=_hash(raw),
        expires_at=timezone.now() + timedelta(seconds=ttl_seconds),
    )
    return raw


def invalidate_tokens(user: User, purpose: str) -> int:
    """Гасит все неиспользованные токены назначения (например, перед новым)."""
    return AccountToken.objects.filter(
        user=user,
        purpose=purpose,
        used_at__isnull=True,
    ).update(used_at=timezone.now())


def find_token(raw: str, purpose: str) -> AccountToken | None:
    return AccountToken.objects.filter(
        token_hash=_hash(raw),
        purpose=purpose,
        used_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).first()


def consume_token(raw: str, purpose: str) -> AccountToken | None:
    now = timezone.now()
    token = (
        AccountToken.objects.select_for_update()
        .filter(
            token_hash=_hash(raw),
            purpose=purpose,
            used_at__isnull=True,
            expires_at__gt=now,
        )
        .first()
    )
    if token is None:
        return None
    token.used_at = now
    token.save(update_fields=["used_at"])
    return token
