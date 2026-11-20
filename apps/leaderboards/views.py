"""Public leaderboard API (§2.11, §2.23)."""

from __future__ import annotations

from rest_framework.permissions import AllowAny  # type: ignore[import-untyped]
from rest_framework.response import Response  # type: ignore[import-untyped]
from rest_framework.views import APIView  # type: ignore[import-untyped]

from apps.catalog.models import Game
from apps.gameplay.api.throttling import SubjectScopedRateThrottle
from apps.leaderboards.services.queries import get_leaderboard, get_personal_best

ALLOWED_LIMITS = {10, 100}


def _published_game(game_id: str) -> Game | None:
    return Game.objects.filter(technical_id=game_id, status=Game.STATUS_PUBLISHED).first()


def _error(code: str, message: str, status: int) -> Response:
    return Response({"code": code, "message": message}, status=status)


class LeaderboardView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [SubjectScopedRateThrottle]
    throttle_scope = "leaderboard_read"

    def get(self, request, game_id: str):
        raw_limit = request.query_params.get("limit", "10")
        try:
            limit = int(raw_limit)
        except ValueError:
            return _error("E_INVALID_REQUEST", "Invalid request", 400)
        if limit not in ALLOWED_LIMITS:
            return _error("E_INVALID_REQUEST", "Invalid request", 400)

        game = _published_game(game_id)
        if game is None:
            return _error("E_SESSION_INVALID", "Game is not available", 404)
        return Response(get_leaderboard(game, limit=limit, user=request.user))


class MyBestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [SubjectScopedRateThrottle]
    throttle_scope = "leaderboard_read"

    def get(self, request, game_id: str):
        if not request.user or not request.user.is_authenticated:
            return _error("E_AUTH_REQUIRED", "Authentication required", 403)
        game = _published_game(game_id)
        if game is None:
            return _error("E_SESSION_INVALID", "Game is not available", 404)
        return Response(get_personal_best(game, request.user))
