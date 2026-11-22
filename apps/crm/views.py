"""Представления CRM.

Вход в CRM использует штатный вход персонала из ``apps.accounts`` вместе с
обязательной TOTP 2FA (``StaffTwoFactorMiddleware``). Отдельной формы входа в
CRM нет; неавторизованные и не-персонал направляются в штатный поток.

Мастер добавления игры (§2.14.5) хранит состояние в ``GameImportDraft`` и
выполняет intake/validation/import через общий сервис пайплайна. Публикация и
откат требуют явного step-up (пароль + TOTP) и остаются POST+CSRF.
"""

from __future__ import annotations

from urllib.parse import urlencode
from uuid import UUID

from django.contrib import messages
from django.contrib.auth import logout as auth_logout
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseRedirect,
)
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts.models import StaffRole, User
from apps.catalog.models import Game, GameVersion, Genre, Tag
from apps.crm.decorators import role_required, staff_required
from apps.crm.forms import StepUpForm, ZipUploadForm
from apps.crm.models import AdminAuditLog
from apps.crm.permissions import (
    ANALYTICS_VIEW,
    AUDIT_VIEW,
    CONTENT_MANAGE,
    GAMES_IMPORT,
    GAMES_PUBLISH,
    GAMES_VIEW,
    MODERATION_MANAGE,
    USERS_MANAGE,
    role_home_name,
)
from apps.crm.services.access import safe_next_path
from apps.crm.services.audit import record_audit
from apps.crm.services.dashboard import dashboard_stats
from apps.crm.services.exports import ReportFormatError, report_response
from apps.crm.services.games import (
    GameCard,
    build_game_list_page,
    load_game_card,
    parse_filters,
)
from apps.crm.services.imports import (
    build_diff,
    get_draft,
    publish_readiness,
    updated_fields,
    upload_package,
)
from apps.crm.services.reports import diagnostic_rows
from apps.crm.services.staff import change_staff_role, set_staff_active
from apps.crm.services.step_up import (
    confirm_step_up,
    is_step_up_valid,
    mark_step_up,
)
from apps.i18n.services.language_registry import get_active_language_codes_safely
from apps.moderation.models import Complaint
from apps.moderation.services.complaints import (
    assign_complaint,
    reject_complaint,
    resolve_complaint,
)
from apps.moderation.services.ratings import set_rating_visibility
from apps.pipeline.models import GameImportDraft
from apps.pipeline.services.artifacts import ArtifactError
from apps.pipeline.services.publishing import publish_version
from apps.pipeline.services.rollback import rollback_version
from apps.ratings.models import GameRatingVote

_ACTION_ERRORS = {
    "V_VERSION_NOT_IN_GAME": "Версия не принадлежит этой игре.",
    "V_VALIDATION_BLOCKED": "Публикация заблокирована отчётом валидации.",
    "V_AUTOTEST_FAILED": "Автотест версии не пройден.",
    "VERSION_NOT_FOUND": "Версия не найдена.",
}

_STEP_UP_ERRORS = {
    "not_staff": "Недостаточно прав для подтверждения операции.",
    "invalid_credentials": "Неверный пароль или код TOTP. Изменения не применены.",
    "step_up_required": "Требуется подтверждение паролем и кодом TOTP.",
}
_STEP_UP_REQUIRED = _STEP_UP_ERRORS["step_up_required"]


def _language_code(request: HttpRequest) -> str:
    return str(getattr(request, "LANGUAGE_CODE", "en"))


def _staff_user(request: HttpRequest) -> User | None:
    user = request.user
    return user if isinstance(user, User) else None


def _safe_crm_next(request: HttpRequest) -> str:
    """Only same-site paths may be carried into the staff login flow."""
    return safe_next_path(str(request.GET.get("next") or ""))


def login_view(request: HttpRequest) -> HttpResponse | HttpResponseRedirect:
    """Send visitors to the existing staff login/2FA flow (§2.16.1)."""
    user = request.user
    if user.is_authenticated and getattr(user, "is_staff", False):
        home = role_home_name(user)
        if home is None:
            return TemplateResponse(
                request,
                "crm/forbidden.html",
                {"title": "Недостаточно прав · CRM"},
                status=403,
            )
        return HttpResponseRedirect(reverse(home))
    query = urlencode({"next": _safe_crm_next(request)})
    return HttpResponseRedirect(f"{reverse('accounts:login')}?{query}")


@require_POST
def logout_view(request: HttpRequest) -> HttpResponseRedirect:
    """Log the staff session out; the base layout posts here with CSRF."""
    auth_logout(request)
    return HttpResponseRedirect(reverse("crm:login"))


@role_required(ANALYTICS_VIEW)
def dashboard(request: HttpRequest) -> TemplateResponse:
    return TemplateResponse(
        request,
        "crm/dashboard.html",
        {
            "title": "CRM",
            "stats": dashboard_stats(),
        },
    )


@role_required(GAMES_VIEW)
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


@role_required(GAMES_VIEW)
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


def _authorize_step_up(request: HttpRequest) -> tuple[bool, str]:
    """Allow an explicit password + TOTP or a still-valid prior elevation.

    When credentials are sent they are always authoritative: an invalid pair
    fails the action even if the session was elevated earlier.
    """
    password = str(request.POST.get("password") or "")
    code = str(
        request.POST.get("totp_code") or request.POST.get("totp") or request.POST.get("code") or ""
    )
    if password or code:
        user = _staff_user(request)
        if user is None:
            return False, _STEP_UP_ERRORS["not_staff"]
        result = confirm_step_up(user, password, code)
        if not result.ok:
            return False, _STEP_UP_ERRORS.get(result.reason, _STEP_UP_ERRORS["invalid_credentials"])
        mark_step_up(request.session)
        return True, ""
    if is_step_up_valid(request.session):
        return True, ""
    return False, _STEP_UP_REQUIRED


def _step_up_redirect(next_url: str) -> HttpResponseRedirect:
    query = urlencode({"next": safe_next_path(next_url)})
    return redirect(f"{reverse('crm:step_up')}?{query}")


@role_required(GAMES_PUBLISH)
@require_POST
def game_publish(request: HttpRequest, game_id: UUID) -> HttpResponseRedirect:
    """Safe publish entry point: POST + CSRF + step-up; the service validates."""
    game = get_object_or_404(Game, pk=game_id)
    version = _posted_version(request, game)
    if version is None:
        messages.error(request, _ACTION_ERRORS["VERSION_NOT_FOUND"])
        return redirect("crm:game_detail", game_id=game.id)

    allowed, reason = _authorize_step_up(request)
    if not allowed:
        messages.error(request, reason)
        if reason == _STEP_UP_REQUIRED:
            return _step_up_redirect(reverse("crm:game_detail", args=[game.id]))
        return redirect("crm:game_detail", game_id=game.id)

    before = {
        "status": game.status,
        "current_version_id": str(game.current_version_id) if game.current_version_id else None,
    }
    with transaction.atomic():
        result = publish_version(game, version)
        if result.ok:
            record_audit(
                actor=_staff_user(request),
                action=AdminAuditLog.ACTION_GAME_PUBLISHED,
                object_type="game",
                object_id=game.id,
                before=before,
                after={
                    "status": game.status,
                    "current_version_id": str(version.id),
                    "semver": version.semver,
                },
                ip=request.META.get("REMOTE_ADDR"),
            )
    if result.ok:
        messages.success(request, f"Версия {version.semver} опубликована.")
    else:
        messages.error(
            request,
            _ACTION_ERRORS.get(result.reason, "Не удалось опубликовать версию."),
        )
    return redirect("crm:game_detail", game_id=game.id)


@role_required(GAMES_PUBLISH)
@require_POST
def game_rollback(request: HttpRequest, game_id: UUID) -> HttpResponseRedirect:
    """Safe rollback entry point: POST + CSRF + step-up, atomic in the service."""
    game = get_object_or_404(Game, pk=game_id)
    version = _posted_version(request, game)
    if version is None:
        messages.error(request, _ACTION_ERRORS["VERSION_NOT_FOUND"])
        return redirect("crm:game_detail", game_id=game.id)

    allowed, reason = _authorize_step_up(request)
    if not allowed:
        messages.error(request, reason)
        if reason == _STEP_UP_REQUIRED:
            return _step_up_redirect(reverse("crm:game_detail", args=[game.id]))
        return redirect("crm:game_detail", game_id=game.id)

    before = {
        "status": game.status,
        "current_version_id": str(game.current_version_id) if game.current_version_id else None,
    }
    with transaction.atomic():
        result = rollback_version(game, version)
        if result.ok:
            record_audit(
                actor=_staff_user(request),
                action=AdminAuditLog.ACTION_GAME_ROLLED_BACK,
                object_type="game",
                object_id=game.id,
                before=before,
                after={
                    "status": game.status,
                    "current_version_id": str(version.id),
                    "semver": version.semver,
                },
                ip=request.META.get("REMOTE_ADDR"),
            )
    if result.ok:
        messages.success(request, f"Выполнен откат к версии {version.semver}.")
    else:
        messages.error(request, _ACTION_ERRORS.get(result.reason, "Не удалось выполнить откат."))
    return redirect("crm:game_detail", game_id=game.id)


# --- Мастер добавления игры (§2.14.5) -----------------------------------


def _attach_upload_alias(request: HttpRequest) -> None:
    """Accept common field names without weakening the form contract."""
    if "package" in request.FILES:
        return
    for alias in ("file", "zip_file", "zip"):
        upload = request.FILES.get(alias)
        if upload is not None:
            request.FILES["package"] = upload
            return


def _target_game(request: HttpRequest) -> Game | None:
    raw = str(request.POST.get("game_id") or request.GET.get("game_id") or "").strip()
    if not raw:
        return None
    try:
        game_id = UUID(raw)
    except ValueError:
        raise Http404("Invalid game id") from None
    return get_object_or_404(Game, pk=game_id)


def _draft_or_404(draft_id: UUID) -> GameImportDraft:
    draft = get_draft(draft_id)
    if draft is None:
        raise Http404("Draft not found")
    return draft


def _render_upload(
    request: HttpRequest,
    *,
    form: ZipUploadForm,
    target_game: Game | None,
) -> TemplateResponse:
    recent = GameImportDraft.objects.select_related("game", "version").order_by("-created_at")[:10]
    return TemplateResponse(
        request,
        "crm/wizard/step1_upload.html",
        {
            "title": "Добавить игру · CRM",
            "form": form,
            "target_game": target_game,
            "recent_drafts": recent,
            "current_step": 1,
        },
    )


@role_required(GAMES_IMPORT)
@require_http_methods(["GET", "POST"])
def wizard_upload(request: HttpRequest) -> TemplateResponse | HttpResponseRedirect:
    """Step 1: accept a ZIP and persist the shared pipeline draft."""
    target_game = _target_game(request)
    if request.method == "GET":
        return _render_upload(request, form=ZipUploadForm(), target_game=target_game)

    _attach_upload_alias(request)
    form = ZipUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return _render_upload(request, form=form, target_game=target_game)

    upload = form.cleaned_data["package"]
    try:
        data = upload.read()
    except OSError:
        messages.error(request, "Не удалось прочитать загруженный файл.")
        return _render_upload(request, form=form, target_game=target_game)

    try:
        result = upload_package(
            data,
            original_filename=str(upload.name or ""),
            created_by=_staff_user(request),
            target_game=target_game,
        )
    except ArtifactError as exc:
        messages.error(request, f"Хранилище пакета недоступно: {exc.code}.")
        return _render_upload(request, form=form, target_game=target_game)

    if result.status == "rejected":
        messages.error(request, "Пакет отклонён. Откройте отчёт для диагностики.")
    elif result.status == "duplicate":
        messages.info(request, "Этот пакет уже импортирован; показана существующая версия.")
    else:
        messages.success(request, "Пакет импортирован. Проверьте анализ и карточку.")
    return redirect("crm:wizard_analysis", draft_id=result.draft.id)


@role_required(GAMES_VIEW)
def wizard_analysis(request: HttpRequest, draft_id: UUID) -> TemplateResponse:
    """Step 2: structured validation analysis for the persisted draft."""
    draft = _draft_or_404(draft_id)
    report = draft.validation_report if isinstance(draft.validation_report, dict) else {}
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    return TemplateResponse(
        request,
        "crm/wizard/step2_analysis.html",
        {
            "title": "Анализ пакета · CRM",
            "draft": draft,
            "diagnostics": diagnostic_rows(draft),
            "report_ok": bool(report.get("ok", False)),
            "summary": summary,
            "current_step": 2,
            "can_continue": draft.version is not None and bool(report.get("ok", False)),
        },
    )


@role_required(GAMES_VIEW)
def wizard_card(request: HttpRequest, draft_id: UUID) -> TemplateResponse:
    """Step 3: imported card fields and the CRM/package diff."""
    draft = _draft_or_404(draft_id)
    manifest = draft.manifest if isinstance(draft.manifest, dict) else {}
    return TemplateResponse(
        request,
        "crm/wizard/step3_card.html",
        {
            "title": "Карточка · CRM",
            "draft": draft,
            "manifest": manifest,
            "game": draft.game,
            "version": draft.version,
            "diff_rows": build_diff(draft),
            "applied_fields": updated_fields(draft),
            "current_step": 3,
            "can_continue": draft.version is not None,
        },
    )


@role_required(GAMES_VIEW)
def wizard_check(request: HttpRequest, draft_id: UUID) -> TemplateResponse:
    """Step 4: autotest/injection reports and publish readiness."""
    draft = _draft_or_404(draft_id)
    autotest = draft.e2e_report if isinstance(draft.e2e_report, dict) else {}
    injection = draft.injection_report if isinstance(draft.injection_report, dict) else {}
    checks = autotest.get("checks") if isinstance(autotest.get("checks"), list) else []
    readiness = publish_readiness(draft)
    return TemplateResponse(
        request,
        "crm/wizard/step4_check.html",
        {
            "title": "Проверка · CRM",
            "draft": draft,
            "autotest": autotest,
            "checks": checks,
            "injection": injection,
            "readiness": readiness,
            "current_step": 4,
        },
    )


def _draft_version(request: HttpRequest, draft: GameImportDraft) -> GameVersion | None:
    raw = str(request.POST.get("version_id") or "").strip()
    if raw and draft.game is not None:
        try:
            return draft.game.versions.filter(pk=raw).first()
        except ValidationError, ValueError:
            return None
    return draft.version


@role_required(GAMES_PUBLISH)
@require_http_methods(["GET", "POST"])
def wizard_publish(request: HttpRequest, draft_id: UUID) -> TemplateResponse | HttpResponseRedirect:
    """Step 5: explicit step-up confirmation, then atomic publication."""
    draft = _draft_or_404(draft_id)
    error = ""
    if request.method == "POST":
        allowed, reason = _authorize_step_up(request)
        if not allowed:
            error = reason
        else:
            version = _draft_version(request, draft)
            if version is None or draft.game is None:
                error = _ACTION_ERRORS["VERSION_NOT_FOUND"]
            else:
                game = draft.game
                before = {
                    "status": game.status,
                    "current_version_id": (
                        str(game.current_version_id) if game.current_version_id else None
                    ),
                }
                with transaction.atomic():
                    result = publish_version(game, version)
                    if result.ok:
                        draft.status = GameImportDraft.STATUS_PUBLISHED
                        draft.save(update_fields=["status", "updated_at"])
                        record_audit(
                            actor=_staff_user(request),
                            action=AdminAuditLog.ACTION_GAME_PUBLISHED,
                            object_type="game",
                            object_id=game.id,
                            before=before,
                            after={
                                "status": game.status,
                                "current_version_id": str(version.id),
                                "semver": version.semver,
                            },
                            ip=request.META.get("REMOTE_ADDR"),
                        )
                if result.ok:
                    messages.success(request, f"Версия {version.semver} опубликована.")
                    return redirect("crm:game_detail", game_id=game.id)
                error = _ACTION_ERRORS.get(result.reason, "Не удалось опубликовать версию.")
    return TemplateResponse(
        request,
        "crm/wizard/step5_publish.html",
        {
            "title": "Публикация · CRM",
            "draft": draft,
            "readiness": publish_readiness(draft),
            "error": error,
            "form": StepUpForm(),
            "current_step": 5,
        },
    )


@staff_required
@require_http_methods(["GET", "POST"])
def step_up(request: HttpRequest) -> TemplateResponse | HttpResponseRedirect:
    """Explicit password + TOTP elevation page used before sensitive actions."""
    next_url = safe_next_path(str(request.POST.get("next") or request.GET.get("next") or ""))
    data = request.POST.copy() if request.method == "POST" else None
    if data is not None and not data.get("totp_code"):
        alias = data.get("totp") or data.get("code")
        if alias:
            data["totp_code"] = alias
    form = StepUpForm(data, initial={"next": next_url})
    error = ""
    if request.method == "POST" and form.is_valid():
        user = _staff_user(request)
        if user is None:
            error = _STEP_UP_ERRORS["not_staff"]
        else:
            result = confirm_step_up(
                user,
                str(form.cleaned_data["password"]),
                str(form.cleaned_data["totp_code"]),
            )
            if result.ok:
                mark_step_up(request.session)
                messages.success(request, "Step-up подтверждён. Действие доступно.")
                return redirect(next_url)
            error = _STEP_UP_ERRORS.get(result.reason, _STEP_UP_ERRORS["invalid_credentials"])
    elif request.method == "POST":
        error = "Проверьте пароль и шестизначный код TOTP."
    return TemplateResponse(
        request,
        "crm/wizard/step_up.html",
        {
            "title": "Подтверждение · CRM",
            "form": form,
            "next": next_url,
            "error": error,
        },
    )


@role_required(GAMES_VIEW)
@require_GET
def wizard_report(request: HttpRequest, draft_id: UUID) -> HttpResponse:
    """Staff-only JSON/CSV report download with a fixed safe filename."""
    draft = _draft_or_404(draft_id)
    token = str(request.GET.get("format") or "json").strip().lower()
    try:
        return report_response(draft, token)
    except ReportFormatError:
        return HttpResponseBadRequest("Unsupported report format")


_STAFF_ERRORS = {
    "not_found": "Сотрудник не найден.",
    "not_staff": "Целевой аккаунт не является сотрудником.",
    "invalid_role": "Неизвестная роль.",
    "self_lockout": "Нельзя изменить собственную роль или статус.",
    "last_owner": "Нельзя оставить CRM без активного владельца.",
    "no_change": "Изменений нет.",
    "forbidden": "Недостаточно прав для изменения сотрудников.",
}


@role_required(USERS_MANAGE)
@require_http_methods(["GET", "POST"])
def staff_management(request: HttpRequest) -> TemplateResponse | HttpResponseRedirect:
    """List staff and assign/deactivate roles with mandatory step-up (§2.16)."""
    if request.method == "POST":
        allowed, reason = _authorize_step_up(request)
        if not allowed:
            messages.error(request, reason)
            if reason == _STEP_UP_REQUIRED:
                return _step_up_redirect(reverse("crm:staff"))
            return redirect("crm:staff")

        actor = _staff_user(request)
        if actor is None:
            messages.error(request, _STEP_UP_ERRORS["not_staff"])
            return redirect("crm:staff")

        target_id = _posted_user_id(request)
        if target_id is None:
            messages.error(request, _STAFF_ERRORS["not_found"])
            return redirect("crm:staff")

        action = str(request.POST.get("action") or "")
        ip = request.META.get("REMOTE_ADDR")
        if action == "role":
            result = change_staff_role(
                actor=actor,
                target_id=target_id,
                role=str(request.POST.get("role") or ""),
                ip=ip,
            )
        elif action == "active":
            raw_active = str(request.POST.get("active") or "").strip().lower()
            if raw_active not in {"0", "1", "false", "true"}:
                messages.error(request, "Некорректный статус сотрудника.")
                return redirect("crm:staff")
            result = set_staff_active(
                actor=actor,
                target_id=target_id,
                is_active=raw_active in {"1", "true"},
                ip=ip,
            )
        else:
            messages.error(request, "Неизвестное действие.")
            return redirect("crm:staff")

        if result.ok:
            messages.success(request, "Изменения сохранены и записаны в журнал аудита.")
        else:
            messages.error(request, _STAFF_ERRORS.get(result.reason, "Изменение отклонено."))
        return redirect("crm:staff")

    staff_users = User.objects.filter(is_staff=True).order_by("login")
    return TemplateResponse(
        request,
        "crm/staff/list.html",
        {
            "title": "Сотрудники · CRM",
            "staff_users": staff_users,
            "roles": StaffRole.choices,
        },
    )


def _posted_user_id(request: HttpRequest) -> UUID | None:
    raw = str(request.POST.get("user_id") or "").strip()
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


@role_required(CONTENT_MANAGE)
def content_overview(request: HttpRequest) -> TemplateResponse:
    """Read-only content overview for editors/owners (genres and tags)."""
    return TemplateResponse(
        request,
        "crm/content.html",
        {
            "title": "Контент · CRM",
            "genres": Genre.objects.all()[:100],
            "tags": Tag.objects.all()[:100],
        },
    )


_MODERATION_ERRORS = {
    "forbidden": "Недостаточно прав для модерации.",
    "not_found": "Запись не найдена.",
    "reason_required": "Укажите причину решения.",
    "reason_too_long": "Причина слишком длинная (максимум 255 символов).",
    "no_change": "Статус уже установлен.",
    "closed": "Жалоба уже закрыта.",
    "assignee_not_found": "Сотрудник для назначения не найден.",
    "invalid_assignee": "Назначать жалобу можно только модератору или владельцу.",
    "resolution_required": "Укажите решение по жалобе.",
}


def _moderation_step_up_redirect(request: HttpRequest) -> HttpResponseRedirect | None:
    """Require an explicit password + TOTP elevation before a decision."""
    allowed, reason = _authorize_step_up(request)
    if allowed:
        return None
    messages.error(request, reason)
    if reason == _STEP_UP_REQUIRED:
        return _step_up_redirect(reverse("crm:moderation"))
    return redirect("crm:moderation")


@role_required(MODERATION_MANAGE)
def moderation_queue(request: HttpRequest) -> TemplateResponse:
    """Rating and complaint queues for moderators/owners (§2.16.2)."""
    votes = (
        GameRatingVote.objects.select_related("game", "user", "moderated_by")
        .order_by("-created_at")
        .all()[:100]
    )
    complaints = (
        Complaint.objects.select_related("game", "rating", "reporter", "assigned_to")
        .order_by("-created_at")
        .all()[:100]
    )
    assignees = User.objects.filter(
        is_staff=True,
        is_active=True,
        crm_role__in=[StaffRole.OWNER, StaffRole.MODERATOR],
    ).order_by("login")
    return TemplateResponse(
        request,
        "crm/moderation.html",
        {
            "title": "Модерация · CRM",
            "votes": votes,
            "complaints": complaints,
            "assignees": assignees,
        },
    )


def _rating_visibility_view(
    request: HttpRequest,
    vote_id: UUID,
    *,
    visible: bool,
) -> HttpResponseRedirect:
    refused = _moderation_step_up_redirect(request)
    if refused is not None:
        return refused
    actor = _staff_user(request)
    result = set_rating_visibility(
        actor=actor,
        vote_id=vote_id,
        visible=visible,
        reason=str(request.POST.get("reason") or ""),
        ip=request.META.get("REMOTE_ADDR"),
    )
    if result.ok:
        messages.success(
            request,
            "Оценка восстановлена." if visible else "Оценка скрыта.",
        )
    else:
        messages.error(request, _MODERATION_ERRORS.get(result.reason, "Решение отклонено."))
    return redirect("crm:moderation")


@role_required(MODERATION_MANAGE)
@require_POST
def rating_hide(request: HttpRequest, vote_id: UUID) -> HttpResponseRedirect:
    """Hide a rating with a mandatory reason; the vote row is preserved."""
    return _rating_visibility_view(request, vote_id, visible=False)


@role_required(MODERATION_MANAGE)
@require_POST
def rating_restore(request: HttpRequest, vote_id: UUID) -> HttpResponseRedirect:
    """Restore a hidden rating with a mandatory reason."""
    return _rating_visibility_view(request, vote_id, visible=True)


def _complaint_error_redirect(request: HttpRequest, reason: str) -> HttpResponseRedirect:
    messages.error(request, _MODERATION_ERRORS.get(reason, "Решение отклонено."))
    return redirect("crm:moderation")


def _posted_assignee_id(request: HttpRequest) -> tuple[UUID | None, bool]:
    """Return ``(assignee_id, valid)``; empty means "assign to the actor"."""
    raw = str(request.POST.get("assignee_id") or request.POST.get("user_id") or "").strip()
    if not raw:
        return None, True
    try:
        return UUID(raw), True
    except ValueError:
        return None, False


@role_required(MODERATION_MANAGE)
@require_POST
def complaint_assign(request: HttpRequest, complaint_id: UUID) -> HttpResponseRedirect:
    """Assign or reassign an open complaint to a moderator/owner."""
    refused = _moderation_step_up_redirect(request)
    if refused is not None:
        return refused
    assignee_id, valid = _posted_assignee_id(request)
    if not valid:
        return _complaint_error_redirect(request, "assignee_not_found")
    result = assign_complaint(
        actor=_staff_user(request),
        complaint_id=complaint_id,
        assignee_id=assignee_id,
        ip=request.META.get("REMOTE_ADDR"),
    )
    if result.ok:
        messages.success(request, "Жалоба назначена.")
        return redirect("crm:moderation")
    return _complaint_error_redirect(request, result.reason)


@role_required(MODERATION_MANAGE)
@require_POST
def complaint_resolve(request: HttpRequest, complaint_id: UUID) -> HttpResponseRedirect:
    """Resolve a complaint with a mandatory resolution note."""
    refused = _moderation_step_up_redirect(request)
    if refused is not None:
        return refused
    result = resolve_complaint(
        actor=_staff_user(request),
        complaint_id=complaint_id,
        resolution=str(request.POST.get("resolution") or ""),
        ip=request.META.get("REMOTE_ADDR"),
    )
    if result.ok:
        messages.success(request, "Жалоба решена.")
        return redirect("crm:moderation")
    return _complaint_error_redirect(request, result.reason)


@role_required(MODERATION_MANAGE)
@require_POST
def complaint_reject(request: HttpRequest, complaint_id: UUID) -> HttpResponseRedirect:
    """Reject a complaint with a mandatory resolution note."""
    refused = _moderation_step_up_redirect(request)
    if refused is not None:
        return refused
    result = reject_complaint(
        actor=_staff_user(request),
        complaint_id=complaint_id,
        resolution=str(request.POST.get("resolution") or ""),
        ip=request.META.get("REMOTE_ADDR"),
    )
    if result.ok:
        messages.success(request, "Жалоба отклонена.")
        return redirect("crm:moderation")
    return _complaint_error_redirect(request, result.reason)


@role_required(AUDIT_VIEW)
def audit_log(request: HttpRequest) -> TemplateResponse:
    """Read-only privileged-action journal for owners/observers."""
    rows = AdminAuditLog.objects.select_related("actor")[:200]
    return TemplateResponse(
        request,
        "crm/audit.html",
        {"title": "Журнал аудита · CRM", "rows": rows},
    )


__all__ = [
    "audit_log",
    "complaint_assign",
    "complaint_reject",
    "complaint_resolve",
    "content_overview",
    "dashboard",
    "game_detail",
    "game_publish",
    "game_rollback",
    "games_list",
    "login_view",
    "logout_view",
    "moderation_queue",
    "rating_hide",
    "rating_restore",
    "staff_management",
    "step_up",
    "wizard_analysis",
    "wizard_card",
    "wizard_check",
    "wizard_publish",
    "wizard_report",
    "wizard_upload",
]
