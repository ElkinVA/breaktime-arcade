from __future__ import annotations

from rest_framework.throttling import ScopedRateThrottle  # type: ignore[import-untyped]

from apps.accounts.services.anonymous import get_anonymous_identity


class SubjectScopedRateThrottle(ScopedRateThrottle):
    """Scope throttle by subject; IP only as a fallback without a live guest identity.

    The guest bucket is keyed by the identity resolved from the signed cookie,
    never by the raw cookie value: an arbitrary or expired token must not mint
    a fresh bucket on every request. Unresolvable tokens fall back to IP.
    """

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = f"user:{request.user.pk}"
        else:
            identity = get_anonymous_identity(request)
            if identity is not None:
                ident = f"anon:{identity.id}"
            else:
                ident = "ip:" + self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}
