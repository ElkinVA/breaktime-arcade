"""Представления CRM.

Вход в CRM использует штатный вход персонала из ``apps.accounts`` вместе с
обязательной TOTP 2FA (``StaffTwoFactorMiddleware``). Отдельной формы входа в
CRM нет; неавторизованные и не-персонал направляются в штатный поток.
"""

from __future__ import annotations

from urllib.parse import urlencode
from uuid import UUID

from django.contrib import messages
from django.contrib.auth import logout as auth_logout
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.catalog.models import Game, GameVersion
from apps.crm.decorators import staff_required
from apps.crm.services.dashboard import dashboard_stats
from apps.crm.services.games import (
    GameCard,
    build_game_list_page,
    load_game_card,
    parse_filters,
)
from apps.i18n.services.language_registry import get_active_language_codes_safely
from apps.pipeline.services.publishing import publish_version
from apps.pipeline.services.rollback import rollback_version

_ACTION_ERRORS = {
    "V_VERSION_NOT_IN_GAME": "Версия не принадлежит этой игре.",
    "V_VALIDATION_BLOCKED": "Публикация заблокирована отчётом валидации.",
    "V_AUTOTEST_FAILED": "Автотест версии не пройден.",
    "VERSION_NOT_FOUND": "Версия не найдена.",
}


def _language_code(request: HttpRequest) -> str:
    return str(getattr(request, "LANGUAGE_CODE", "en"))


def _safe_crm_next(request: HttpRequest) -> str:
    """Only same-site paths may be carried into the staff login flow."""
    default = reverse("crm:dashboard")
    candidate = str(request.GET.get("next") or "")
    if candidate.startswith("/") and not candidate.startswith("//"):
        return candidate
    return default


def login_view(request: HttpRequest) -> HttpResponseRedirect:
    """Send visitors to the existing staff login/2FA flow (§2.16.1)."""
    user = request.user
    if user.is_authenticated and getattr(user, "is_staff", False):
        return HttpResponseRedirect(reverse("crm:dashboard"))
    query = urlencode({"next": _safe_crm_next(request)})
    return HttpResponseRedirect(f"{reverse('accounts:login')}?{query}")


@require_POST
def logout_view(request: HttpRequest) -> HttpResponseRedirect:
    """Log the staff session out; the base layout posts here with CSRF."""
    auth_logout(request)
    return HttpResponseRedirect(reverse("crm:login"))


@staff_required
def dashboard(request: HttpRequest) -> TemplateResponse:
    return TemplateResponse(
        request,
        "crm/dashboard.html",
        {
            "title": "CRM",
            "stats": dashboard_stats(),
        },
    )


@staff_required
def games_list(request: HttpRequest) -> TemplateResponse:
    """Staff inventory list with counters and status/genre filters (§2.16.2)."""
    filters = parse_filters(request.GET)
    page = build_game_list_page(
        filters,
        get_active_language_codes_safely(),
        language_code=_language_code(request),
    )
    return TemplateResponse(
        request,
        "crm/games/list.html",
        {"title": "Игры · CRM", "page": page},
    )


@staff_required
def game_detail(request: HttpRequest, game_id: UUID) -> TemplateResponse:
    """Game card with status, current version and immutable version history."""
    card: GameCard | None = load_game_card(
        game_id,
        get_active_language_codes_safely(),
        language_code=_language_code(request),
    )
    if card is None:
        raise Http404("Game not found")
    return TemplateResponse(
        request,
        "crm/games/detail.html",
        {"title": f"{card.title} · CRM", "card": card},
    )


def _posted_version(request: HttpRequest, game: Game) -> GameVersion | None:
    raw = str(request.POST.get("version_id") or "").strip()
    if not raw:
        return None
    try:
        return game.versions.get(pk=raw)
    except GameVersion.DoesNotExist, ValidationError, ValueError:
        return None


@staff_required
@require_POST
def game_publish(request: HttpRequest, game_id: UUID) -> HttpResponseRedirect:
    """Safe publish entry point: POST + CSRF, validation checked by the service."""
    game = get_object_or_404(Game, pk=game_id)
    version = _posted_version(request, game)
    if version is None:
        messages.error(request, _ACTION_ERRORS["VERSION_NOT_FOUND"])
        return redirect("crm:game_detail", game_id=game.id)
    result = publish_version(game, version)
    if result.ok:
        messages.success(request, f"Версия {version.semver} опубликована.")
    else:
        messages.error(
            request,
            _ACTION_ERRORS.get(result.reason, "Не удалось опубликовать версию."),
        )
    return redirect("crm:game_detail", game_id=game.id)


@staff_required
@require_POST
def game_rollback(request: HttpRequest, game_id: UUID) -> HttpResponseRedirect:
    """Safe rollback entry point: POST + CSRF, atomic switch in the service."""
    game = get_object_or_404(Game, pk=game_id)
    version = _posted_version(request, game)
    if version is None:
        messages.error(request, _ACTION_ERRORS["VERSION_NOT_FOUND"])
        return redirect("crm:game_detail", game_id=game.id)
    result = rollback_version(game, version)
    if result.ok:
        messages.success(request, f"Выполнен откат к версии {version.semver}.")
    else:
        messages.error(request, _ACTION_ERRORS.get(result.reason, "Не удалось выполнить откат."))
    return redirect("crm:game_detail", game_id=game.id)
