"""Storage API (§2.22/§2.23): ETag, If-Match, guest TTL."""

from __future__ import annotations

from rest_framework.permissions import AllowAny  # type: ignore[import-untyped]
from rest_framework.response import Response  # type: ignore[import-untyped]
from rest_framework.views import APIView  # type: ignore[import-untyped]

from apps.gameplay.api.throttling import (
    StorageSessionRateThrottle,
    SubjectScopedRateThrottle,
)
from apps.gameplay.api.views import CsrfEnforcedSessionAuthentication
from apps.gameplay.services.sessions import SessionError
from apps.gameplay.services.storage import get_storage, put_storage


def _error(exc: SessionError) -> Response:
    return Response({"code": exc.code, "message": exc.message}, status=exc.status)


def _etag(revision: int) -> str:
    return f'"{revision}"'


def _revision(payload: dict[str, object]) -> int:
    value = payload.get("revision", 0)
    return value if isinstance(value, int) else int(str(value))


MAX_STORAGE_BODY_BYTES = 128 * 1024


class GameStorageView(APIView):
    authentication_classes = [CsrfEnforcedSessionAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [StorageSessionRateThrottle, SubjectScopedRateThrottle]
    throttle_scope = "storage"

    def get(self, request, game_id: str):
        try:
            payload = get_storage(request, game_id)
        except SessionError as exc:
            return _error(exc)
        response = Response(payload)
        response["ETag"] = _etag(_revision(payload))
        return response

    def put(self, request, game_id: str):
        content_length = int(request.META.get("CONTENT_LENGTH") or 0)
        if content_length > MAX_STORAGE_BODY_BYTES:
            return Response(
                {"code": "E_STORAGE_QUOTA", "message": "Storage quota exceeded"},
                status=413,
            )
        if not isinstance(request.data, dict):
            return Response(
                {"code": "E_INVALID_REQUEST", "message": "Storage data must be an object"},
                status=400,
            )
        try:
            payload = put_storage(
                request,
                game_id,
                data=request.data,
                if_match=request.headers.get("If-Match", ""),
            )
        except SessionError as exc:
            return _error(exc)
        response = Response(payload)
        response["ETag"] = _etag(_revision(payload))
        return response
