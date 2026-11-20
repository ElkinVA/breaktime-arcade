"""Rating API (§2.9/§2.23)."""

from __future__ import annotations

from rest_framework.permissions import AllowAny  # type: ignore[import-untyped]
from rest_framework.response import Response  # type: ignore[import-untyped]
from rest_framework.views import APIView  # type: ignore[import-untyped]

from apps.catalog.models import Game
from apps.gameplay.api.throttling import SubjectScopedRateThrottle
from apps.gameplay.api.views import CsrfEnforcedSessionAuthentication
from apps.gameplay.services.sessions import SessionError
from apps.ratings.api.serializers import RatingVoteSerializer
from apps.ratings.services.aggregates import summary
from apps.ratings.services.voting import vote


def _error(exc: SessionError) -> Response:
    return Response({"code": exc.code, "message": exc.message}, status=exc.status)


class RatingView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [SubjectScopedRateThrottle]
    throttle_scope = "rating_read"

    def get(self, request, game_id: str):
        game = Game.objects.filter(technical_id=game_id, status=Game.STATUS_PUBLISHED).first()
        if game is None:
            return Response(
                {"code": "E_SESSION_INVALID", "message": "Game is not available"},
                status=404,
            )
        return Response(summary(game, request.user))


class RatingVoteView(APIView):
    authentication_classes = [CsrfEnforcedSessionAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [SubjectScopedRateThrottle]
    throttle_scope = "rating"

    def post(self, request, game_id: str):
        serializer = RatingVoteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"code": "E_INVALID_REQUEST", "message": "Invalid request"},
                status=400,
            )
        try:
            payload = vote(request, game_id, serializer.validated_data["value"])
        except SessionError as exc:
            return _error(exc)
        return Response(payload)
