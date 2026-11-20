"""Гостевая идентичность: подписанная cookie + серверный token_hash."""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from apps.accounts.models import AnonymousIdentity

logger = logging.getLogger(__name__)

COOKIE_NAME = "ba_anon"
COOKIE_MAX_AGE = 90 * 24 * 60 * 60
SIGNING_SALT = "ba.anonymous"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _decode(value: str) -> str | None:
    try:
        payload = signing.loads(value, salt=SIGNING_SALT)
    except signing.BadSignature:
        return None
    if not isinstance(payload, str):
        return None
    parts = payload.split(":")
    if len(parts) != 3 or parts[0] != "v1":
        return None
    return payload


def _encode(identity_id: str) -> str:
    return signing.dumps(f"v1:{identity_id}:{int(time.time())}", salt=SIGNING_SALT, compress=True)


def get_anonymous_identity(request: HttpRequest) -> AnonymousIdentity | None:
    """Return the current non-expired guest identity without creating one."""
    token = request.COOKIES.get(COOKIE_NAME, "")
    if not token or _decode(token) is None:
        return None
    return AnonymousIdentity.objects.filter(
        token_hash=_hash(token),
        expires_at__gt=timezone.now(),
    ).first()


def get_or_create_anonymous_identity(
    request: HttpRequest,
    response: HttpResponse | None = None,
) -> AnonymousIdentity:
    token = request.COOKIES.get(COOKIE_NAME, "")
    payload = _decode(token) if token else None
    if payload is not None:
        token_hash = _hash(token)
        identity = AnonymousIdentity.objects.filter(
            token_hash=token_hash,
            expires_at__gt=timezone.now(),
        ).first()
        if identity is not None:
            now = timezone.now()
            if now - identity.last_seen_at > timedelta(hours=1):
                identity.last_seen_at = now
                identity.expires_at = now + timedelta(seconds=COOKIE_MAX_AGE)
                identity.save(update_fields=["last_seen_at", "expires_at"])
            return identity

    now = timezone.now()
    identity = AnonymousIdentity.objects.create(
        token_hash=secrets.token_hex(32),
        expires_at=now + timedelta(seconds=COOKIE_MAX_AGE),
    )
    new_token = _encode(str(identity.id))
    identity.token_hash = _hash(new_token)
    identity.save(update_fields=["token_hash"])
    if response is not None:
        response.set_cookie(
            COOKIE_NAME,
            new_token,
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            secure=not settings.DEBUG,
            samesite="Lax",
        )
    logger.info("account.anonymous.created", extra={"anon_id": str(identity.id)})
    return identity
