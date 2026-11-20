from __future__ import annotations

from uuid import UUID

from rest_framework.authentication import SessionAuthentication  # type: ignore[import-untyped]
from rest_framework.permissions import AllowAny  # type: ignore[import-untyped]
from rest_framework.response import Response  # type: ignore[import-untyped]
from rest_framework.views import APIView  # type: ignore[import-untyped]

from apps.gameplay.api.serializers import (
    SessionActivateSerializer,
    SessionCreateSerializer,
)
from apps.gameplay.api.throttling import SubjectScopedRateThrottle
from apps.gameplay.services.sessions import (
    SessionError,
    activate_session,
    create_session,
    heartbeat,
)


class CsrfEnforcedSessionAuthentication(SessionAuthentication):
    """Session auth that also enforces CSRF for anonymous guest requests."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            self.enforce_csrf(request)
        return result


def _fail(response: Response, exc: SessionError) -> Response:
    """Fill an existing response so cookies set on it survive the error path."""
    response.status_code = exc.status
    response.data = {"code": exc.code, "message": exc.message}
    return response


def _error(exc: SessionError) -> Response:
    return _fail(Response(), exc)


def _invalid_request() -> SessionError:
    return SessionError("E_INVALID_REQUEST", "Invalid request", 400)


class SessionCreateView(APIView):
    authentication_classes = [CsrfEnforcedSessionAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [SubjectScopedRateThrottle]
    throttle_scope = "sessions"

    def post(self, request):
        response = Response(status=201)
        serializer = SessionCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _fail(response, _invalid_request())
        try:
            session, ticket, expires_at = create_session(
                request,
                response,
                game_id=serializer.validated_data["game_id"],
            )
        except SessionError as exc:
            return _fail(response, exc)
        response.data = {
            "session_id": str(session.id),
            "ticket": ticket,
            "expires_at": expires_at.isoformat(),
        }
        return response


class SessionActivateView(APIView):
    authentication_classes = [CsrfEnforcedSessionAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [SubjectScopedRateThrottle]
    throttle_scope = "sessions"

    def post(self, request, session_id: UUID):
        serializer = SessionActivateSerializer(data=request.data)
        if not serializer.is_valid():
            return _error(_invalid_request())
        try:
            context = activate_session(
                request,
                session_id,
                ticket=serializer.validated_data["ticket"],
                binding_nonce=serializer.validated_data["binding_nonce"],
            )
        except SessionError as exc:
            return _error(exc)
        return Response({"context": context})


class SessionHeartbeatView(APIView):
    authentication_classes = [CsrfEnforcedSessionAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [SubjectScopedRateThrottle]
    throttle_scope = "heartbeat"

    def post(self, request, session_id: UUID):
        try:
            heartbeat(request, session_id)
        except SessionError as exc:
            return _error(exc)
        return Response(status=204)
