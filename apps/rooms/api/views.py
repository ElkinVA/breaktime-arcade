from __future__ import annotations

import logging
from uuid import UUID

from rest_framework.authentication import SessionAuthentication  # type: ignore[import-untyped]
from rest_framework.exceptions import ParseError  # type: ignore[import-untyped]
from rest_framework.parsers import JSONParser  # type: ignore[import-untyped]
from rest_framework.permissions import AllowAny  # type: ignore[import-untyped]
from rest_framework.response import Response  # type: ignore[import-untyped]
from rest_framework.views import APIView  # type: ignore[import-untyped]

from apps.gameplay.api.throttling import IpRateThrottle, SubjectScopedRateThrottle
from apps.gameplay.api.views import CsrfEnforcedSessionAuthentication
from apps.rooms.api.serializers import (
    RoomCommandSerializer,
    RoomCreateSerializer,
    RoomJoinSerializer,
)
from apps.rooms.services.rooms import (
    RoomError,
    RoomStale,
    create_room,
    execute_command,
    join_room,
    leave_room,
    read_room,
    snapshot,
)

logger = logging.getLogger("apps.rooms")


class RoomIpThrottle(IpRateThrottle):
    scope = "rooms_ip"


class RoomJSONParser(JSONParser):
    def parse(self, stream, media_type=None, parser_context=None):
        try:
            return super().parse(stream, media_type, parser_context)
        except RecursionError as exc:
            raise ParseError("request nesting is too deep") from exc


class RoomAPIView(APIView):
    """Room payloads contain private roles, so never allow shared/browser caching."""

    parser_classes = [RoomJSONParser]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


def _error(exc: RoomError, response: Response | None = None, **extra: object) -> Response:
    target = response or Response()
    target.status_code = exc.status
    target.data = {"code": exc.code, "message": exc.message, **extra}
    return target


class RoomCreateView(RoomAPIView):
    authentication_classes = [CsrfEnforcedSessionAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [SubjectScopedRateThrottle, RoomIpThrottle]
    throttle_scope = "rooms_create"

    def post(self, request):
        serializer = RoomCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"code": "E_INVALID_REQUEST", "message": "Invalid request"}, status=400)
        data = serializer.validated_data
        response = Response(status=201)
        try:
            room, member = create_room(
                request,
                response,
                game_id=data["game_id"],
                max_players=data["max_players"],
                undercover_count=data["undercover_count"],
                mr_white=data["mr_white"],
                category_id=data.get("category_id") or None,
                name=data.get("name") or None,
                request_id=data.get("requestId"),
            )
        except RoomError as exc:
            logger.warning(
                "room.create",
                extra={
                    "event": "room.create",
                    "outcome": "error",
                    "error_code": exc.code,
                },
            )
            return _error(exc, response)
        response.data = snapshot(room, member)
        return response


class RoomJoinView(RoomAPIView):
    authentication_classes = [CsrfEnforcedSessionAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [RoomIpThrottle, SubjectScopedRateThrottle]
    throttle_scope = "rooms_join"

    def post(self, request):
        serializer = RoomJoinSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"code": "E_INVALID_REQUEST", "message": "Invalid request"}, status=400)
        data = serializer.validated_data
        response = Response()
        try:
            room, member = join_room(
                request,
                response,
                code=data["code"],
                name=data.get("name") or None,
            )
        except RoomError as exc:
            logger.info(
                "room.join",
                extra={
                    "event": "room.join",
                    "outcome": "error",
                    "error_code": exc.code,
                },
            )
            return _error(exc, response)
        response.status_code = 200
        response.data = snapshot(room, member)
        return response


class RoomDetailView(RoomAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [SubjectScopedRateThrottle]
    throttle_scope = "rooms_read"

    def get(self, request, room_id: UUID):
        try:
            return Response(read_room(request, room_id))
        except RoomError as exc:
            logger.info(
                "room.read",
                extra={
                    "event": "room.read",
                    "outcome": "error",
                    "error_code": exc.code,
                    "room_id": str(room_id),
                },
            )
            return _error(exc)


class RoomCommandView(RoomAPIView):
    authentication_classes = [CsrfEnforcedSessionAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [SubjectScopedRateThrottle]
    throttle_scope = "rooms_command"

    def post(self, request, room_id: UUID):
        serializer = RoomCommandSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"code": "E_INVALID_REQUEST", "message": "Invalid request"}, status=400)
        data = serializer.validated_data
        try:
            result = execute_command(
                request,
                room_id,
                command=data["command"],
                payload=data["payload"],
                request_id=data["requestId"],
                expected_version=data.get("expectedVersion"),
            )
        except RoomStale as exc:
            try:
                current = read_room(request, room_id)
            except RoomError:
                current = None
            return _error(exc, snapshot=current)
        except RoomError as exc:
            return _error(exc)
        return Response(result)


class RoomLeaveView(RoomAPIView):
    authentication_classes = [CsrfEnforcedSessionAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [SubjectScopedRateThrottle]
    throttle_scope = "rooms_command"

    def post(self, request, room_id: UUID):
        try:
            leave_room(request, room_id)
        except RoomError as exc:
            return _error(exc)
        return Response(status=204)
