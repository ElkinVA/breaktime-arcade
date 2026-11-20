"""Request-id, клиентский IP, заголовки безопасности и CSP с nonce (§2.20)."""

from __future__ import annotations

import ipaddress
import secrets
import uuid
from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse

from apps.core.logging import set_request_id

GetResponse = Callable[[HttpRequest], HttpResponse]


class ClientIPMiddleware:
    """Use nginx's X-Forwarded-For only when the peer is a trusted proxy.

    nginx overwrites XFF with ``$remote_addr``; Gunicorn does not rewrite
    ``REMOTE_ADDR``, so Django would otherwise see the proxy address for every
    client and IP rate limits would be global. Trust is limited to configured
    private proxy networks, so a direct client cannot spoof the header.
    """

    def __init__(self, get_response: GetResponse) -> None:
        self.get_response = get_response

    @staticmethod
    def _is_trusted_proxy(value: str) -> bool:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            return False
        return any(address in network for network in settings.BA_TRUSTED_PROXY_NETWORKS)

    def __call__(self, request: HttpRequest) -> HttpResponse:
        remote = request.META.get("REMOTE_ADDR", "")
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded and self._is_trusted_proxy(remote):
            candidate = forwarded.split(",")[-1].strip()
            try:
                ipaddress.ip_address(candidate)
            except ValueError:
                pass
            else:
                request.META["REMOTE_ADDR"] = candidate
        return self.get_response(request)


class RequestIDMiddleware:
    def __init__(self, get_response: GetResponse) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.request_id = rid  # type: ignore[attr-defined]
        set_request_id(rid)
        response = self.get_response(request)
        response["X-Request-ID"] = rid
        return response


class SecurityHeadersMiddleware:
    def __init__(self, get_response: GetResponse) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        response.setdefault("Permissions-Policy", settings.BA_PERMISSIONS_POLICY)
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if getattr(settings, "BA_NOINDEX", False):
            response.setdefault("X-Robots-Tag", "noindex, nofollow")
        return response


class ContentSecurityPolicyMiddleware:
    def __init__(self, get_response: GetResponse) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        nonce = secrets.token_urlsafe(16)
        request.csp_nonce = nonce  # type: ignore[attr-defined]
        response = self.get_response(request)
        directives = dict(settings.BA_CSP_DIRECTIVES)
        directives["script-src"] = f"{directives['script-src']} 'nonce-{nonce}'"
        response["Content-Security-Policy"] = "; ".join(
            f"{key} {value}" for key, value in directives.items()
        )
        return response
