"""Public complaint intake (§2.23 ``POST /reports``).

Guests may report a published game or a rating; the authenticated account is
stored as the reporter when present. CSRF is enforced for both session-auth and
anonymous writes, and the subject-scoped throttle prevents complaint flooding.
"""

from __future__ import annotations

from rest_framework.permissions import AllowAny  # type: ignore[import-untyped]
from rest_framework.response import Response  # type: ignore[import-untyped]
from rest_framework.views import APIView  # type: ignore[import-untyped]

from apps.accounts.models import User
from apps.catalog.models import Game
from apps.gameplay.api.throttling import SubjectScopedRateThrottle
from apps.gameplay.api.views import CsrfEnforcedSessionAuthentication
from apps.moderation.api.serializers import ComplaintCreateSerializer
from apps.moderation.services.complaints import create_complaint
from apps.ratings.models import GameRatingVote


def _invalid_request(message: str = "Invalid request") -> Response:
    return Response({"code": "E_INVALID_REQUEST", "message": message}, status=400)


class ComplaintCreateView(APIView):
    authentication_classes = [CsrfEnforcedSessionAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [SubjectScopedRateThrottle]
    throttle_scope = "reports"

    def post(self, request):
        serializer = ComplaintCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _invalid_request()

        data = serializer.validated_data
        game = Game.objects.filter(
            technical_id=data["game_id"],
            status=Game.STATUS_PUBLISHED,
        ).first()
        if game is None:
            return _invalid_request()

        rating = None
        rating_id = data.get("rating_id")
        if rating_id is not None:
            rating = GameRatingVote.objects.filter(pk=rating_id, game=game).first()
            if rating is None:
                return _invalid_request()

        reporter = request.user if isinstance(request.user, User) else None
        result = create_complaint(
            game=game,
            reporter=reporter if reporter is not None and reporter.is_authenticated else None,
            subject=str(data["subject"]),
            category=str(data["category"]),
            rating=rating,
        )
        if not result.ok or result.complaint is None:
            return _invalid_request()
        complaint = result.complaint
        return Response(
            {
                "id": str(complaint.id),
                "status": complaint.status,
                "created_at": complaint.created_at.isoformat(),
            },
            status=201,
        )
