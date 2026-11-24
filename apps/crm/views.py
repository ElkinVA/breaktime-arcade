"""Представления CRM.

Вход в CRM использует штатный вход персонала из ``apps.accounts`` вместе с
обязательной TOTP 2FA (``StaffTwoFactorMiddleware``). Отдельной формы входа в
CRM нет; неавторизованные и не-персонал направляются в штатный поток.

Мастер добавления игры (§2.14.5) хранит состояние в ``GameImportDraft`` и
выполняет intake/validation/import через общий сервис пайплайна. Публикация и
откат требуют явного step-up (пароль + TOTP) и остаются POST+CSRF.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode
from uuid import UUID

from django.contrib import messages
from django.contrib.auth import logout as auth_logout
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseBase,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts.models import EmailAddress, StaffRole, User, UserProfile
from apps.accounts.services.profile import export_account_data
from apps.analytics.services.aggregates import (
    AnalyticsRangeError,
    build_snapshot,
    parse_date_range,
)
from apps.analytics.services.exports import AnalyticsExportError, render_export
from apps.catalog.models import Game, GameVersion, Genre, Tag
from apps.content.models import ContentPage
from apps.content.services.localization import create_translation, update_translation
from apps.content.services.pages import (
    PageValidationError,
    create_page,
    publish_page,
    save_page_translation,
    unpublish_page,
)
from apps.crm.decorators import role_required, staff_required
from apps.crm.forms import (
    ContentPageForm,
    ContentPageTranslationForm,
    GenreForm,
    GenreTranslationForm,
    StepUpForm,
    TagForm,
    TagTranslationForm,
    TranslationEntryCreateForm,
    TranslationEntryEditForm,
    ZipUploadForm,
)
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
from apps.crm.services.game_records import build_game_records
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
from apps.crm.services.seo_diagnostics import build_seo_diagnostics
from apps.crm.services.staff import change_staff_role, set_staff_active
from apps.crm.services.step_up import (
    confirm_step_up,
    is_step_up_valid,
    mark_step_up,
)
from apps.crm.services.taxonomy import (
    TranslationPayload,
    create_genre,
    create_tag,
    delete_genre,
    delete_tag,
    update_genre,
    update_tag,
)
from apps.crm.services.users import (
    MIN_SEARCH_LENGTH,
    UserFilters,
    current_leaderboard_entries,
    delete_customer,
    parse_user_filters,
    recent_results,
    search_users,
    toggle_user_active,
)
from apps.crm.services.version_downloads import (
    REPORT_FORMATS,
    REPORT_KINDS,
    ArtifactUnavailable,
    UnknownReport,
    package_response,
    runtime_response,
)
from apps.crm.services.version_downloads import (
    report_response as version_report_response,
)
from apps.i18n.models import Language, TranslationEntry
from apps.i18n.services.language_registry import get_active_language_codes_safely
from apps.moderation.models import Complaint
from apps.moderation.services.complaints import (
    assign_complaint,
    reject_complaint,
    resolve_complaint,
)
from apps.moderation.services.ratings import (
    RATING_STATUS_CHOICES,
    RATING_VALUE_CHOICES,
    filter_rating_votes,
    parse_rating_filters,
    rating_game_options,
    set_rating_visibility,
    summarize_rating_votes,
)
from apps.pipeline.models import GameImportDraft
from apps.pipeline.services.artifacts import ArtifactError
from apps.pipeline.services.publishing import publish_version
from apps.pipeline.services.rollback import rollback_version

_ACTION_ERRORS = {
    "V_VERSION_NOT_IN_GAME": "Версия не принадлежит этой игре.",
    "V_VALIDATION_BLOCKED": "Публикация заблокирована отчётом валидации.",
    "V_AUTOTEST_FAILED": "Автотест версии не пройден.",
    "V_NOT_PUBLISHED": "Откат возможен только на ранее опубликованную версию.",
    "V_GAME_NOT_PUBLISHED": "Откат недоступен для игры в текущем статусе.",
    "V_SCORE_RULES_CHANGED": (
        "Правила счёта отличаются; требуется решение владельца об эпохе рекордов."
    ),
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


@role_required(ANALYTICS_VIEW)
@require_GET
def analytics_dashboard(request: HttpRequest) -> HttpResponse:
    """Date-filtered local analytics built from existing platform records."""
    try:
        date_range = parse_date_range(request.GET)
    except AnalyticsRangeError as exc:
        return HttpResponseBadRequest(exc.message)
    snapshot = build_snapshot(date_range)
    return TemplateResponse(
        request,
        "crm/analytics.html",
        {
            "title": "Аналитика · CRM",
            "snapshot": snapshot,
            "date_from": date_range.start.isoformat(),
            "date_to": date_range.end.isoformat(),
        },
    )


@role_required(ANALYTICS_VIEW)
@require_GET
def analytics_export(request: HttpRequest) -> HttpResponse:
    """Safe CSV/JSON download of the same local snapshot (no PII/hashes)."""
    try:
        date_range = parse_date_range(request.GET)
    except AnalyticsRangeError as exc:
        return HttpResponseBadRequest(exc.message)
    snapshot = build_snapshot(date_range)
    report_format = str(request.GET.get("format") or "csv")
    try:
        content, content_type, filename = render_export(snapshot, report_format)
    except AnalyticsExportError:
        return HttpResponseBadRequest("Unsupported export format")
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


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
@require_GET
def seo_diagnostics(request: HttpRequest) -> TemplateResponse:
    """SEO diagnostics for published games with a per-language breakdown (§2.19)."""
    return TemplateResponse(
        request,
        "crm/seo_diagnostics.html",
        {
            "title": "SEO-диагностика · CRM",
            "diagnostics": build_seo_diagnostics(get_active_language_codes_safely()),
        },
    )


@role_required(GAMES_VIEW)
@require_GET
def game_detail(request: HttpRequest, game_id: UUID) -> TemplateResponse:
    """Game card: status, version history and read-only leaderboard records."""
    card: GameCard | None = load_game_card(
        game_id,
        get_active_language_codes_safely(),
        language_code=_language_code(request),
    )
    if card is None:
        raise Http404("Game not found")
    records = build_game_records(
        card.game,
        epoch=request.GET.get("epoch"),
        page=request.GET.get("page"),
    )
    return TemplateResponse(
        request,
        "crm/games/detail.html",
        {
            "title": f"{card.title} · CRM",
            "card": card,
            "records": records,
            # Keep the selected archive epoch while paging; the current epoch
            # is the default and needs no extra query parameter.
            "pagination_query": (
                "" if records.is_current_epoch else f"epoch={records.selected_epoch}"
            ),
        },
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

    result = publish_version(
        game,
        version,
        actor=_staff_user(request),
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

    result = rollback_version(
        game,
        version,
        actor=_staff_user(request),
        ip=request.META.get("REMOTE_ADDR"),
    )
    if result.ok:
        messages.success(request, f"Выполнен откат к версии {version.semver}.")
    else:
        messages.error(request, _ACTION_ERRORS.get(result.reason, "Не удалось выполнить откат."))
    return redirect("crm:game_detail", game_id=game.id)


def _version_or_404(game_id: UUID, version_id: UUID) -> GameVersion:
    version = (
        GameVersion.objects.select_related("game").filter(pk=version_id, game_id=game_id).first()
    )
    if version is None:
        raise Http404("Version not found")
    return version


def _download_step_up_guard(request: HttpRequest) -> HttpResponseRedirect | None:
    """Artifact downloads are sensitive: require a fresh elevation."""
    allowed, reason = _authorize_step_up(request)
    if allowed:
        return None
    messages.error(request, reason)
    return _step_up_redirect(request.get_full_path())


@role_required(GAMES_VIEW)
@require_GET
def version_package_download(
    request: HttpRequest, game_id: UUID, version_id: UUID
) -> HttpResponseBase:
    """Download the byte-for-byte original ZIP; staff role plus step-up."""
    version = _version_or_404(game_id, version_id)
    refused = _download_step_up_guard(request)
    if refused is not None:
        return refused
    try:
        return package_response(version)
    except ArtifactUnavailable:
        raise Http404("Package artifact not found") from None


@role_required(GAMES_VIEW)
@require_GET
def version_runtime_download(
    request: HttpRequest, game_id: UUID, version_id: UUID
) -> HttpResponseBase:
    """Download the published runtime tree as a zip; staff role plus step-up."""
    version = _version_or_404(game_id, version_id)
    refused = _download_step_up_guard(request)
    if refused is not None:
        return refused
    try:
        return runtime_response(version)
    except ArtifactUnavailable:
        raise Http404("Runtime artifact not found") from None


@role_required(GAMES_VIEW)
@require_GET
def version_report_download(
    request: HttpRequest,
    game_id: UUID,
    version_id: UUID,
    report_kind: str,
    report_format: str,
) -> HttpResponse:
    """Download a persisted per-version report as JSON or Markdown (§2.14.7)."""
    version = _version_or_404(game_id, version_id)
    kind = report_kind.strip().lower()
    token = report_format.strip().lower()
    if kind not in REPORT_KINDS:
        raise Http404("Report not found")
    if token not in REPORT_FORMATS:
        return HttpResponseBadRequest("Unsupported report format")
    try:
        return version_report_response(version, kind, token)
    except UnknownReport:
        raise Http404("Report not found") from None


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
                with transaction.atomic():
                    result = publish_version(
                        game,
                        version,
                        actor=_staff_user(request),
                        ip=request.META.get("REMOTE_ADDR"),
                    )
                    if result.ok:
                        draft.status = GameImportDraft.STATUS_PUBLISHED
                        draft.save(update_fields=["status", "updated_at"])
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


def _filter_choices(filters: UserFilters) -> dict[str, str]:
    return {
        "email_verified_choice": (
            "" if filters.email_verified is None else str(filters.email_verified).lower()
        ),
        "blocked_choice": "" if filters.blocked is None else str(filters.blocked).lower(),
    }


USERS_PAGE_SIZE = 50


def _customer_or_404(user_id: UUID) -> User:
    """Customer routes must never address staff/owner accounts or tombstones."""
    return get_object_or_404(User, pk=user_id, is_staff=False)


@role_required(USERS_MANAGE)
@require_GET
def users_list(request: HttpRequest) -> TemplateResponse:
    """Search and filter customer accounts (§2.16.2, "Пользователи")."""
    filters = parse_user_filters(request.GET)
    paginator = Paginator(search_users(filters), USERS_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return TemplateResponse(
        request,
        "crm/users/list.html",
        {
            "title": "Пользователи · CRM",
            "users": page_obj,
            "page_obj": page_obj,
            "pagination_query": params.urlencode(),
            "filters": filters,
            "search_min_length": MIN_SEARCH_LENGTH,
            **_filter_choices(filters),
        },
    )


def _user_action_redirect(user_id: UUID) -> HttpResponseRedirect:
    return redirect("crm:user_detail", user_id=user_id)


def _toggle_block(request: HttpRequest, user_id: UUID) -> HttpResponseRedirect:
    actor = _staff_user(request)
    if actor is None:
        messages.error(request, _STEP_UP_ERRORS["not_staff"])
        return redirect("crm:users")
    result = toggle_user_active(
        actor=actor,
        target_id=user_id,
        ip=request.META.get("REMOTE_ADDR"),
        reason=str(request.POST.get("reason") or "").strip()[:255],
    )
    if not result.ok:
        if result.reason == "not_found":
            messages.error(request, "Аккаунт не найден.")
            return redirect("crm:users")
        if result.reason == "already_deleted":
            messages.error(request, "Аккаунт уже удалён и не может быть разблокирован.")
        elif result.reason == "self_target":
            messages.error(request, "Нельзя заблокировать собственную учётную запись.")
        else:
            messages.error(request, "Операция недоступна.")
    elif result.is_active:
        messages.success(request, "Аккаунт разблокирован; изменение записано в журнал.")
    else:
        messages.success(request, "Аккаунт заблокирован; изменение записано в журнал.")
    return _user_action_redirect(user_id)


def _delete_user(request: HttpRequest, user_id: UUID) -> HttpResponseRedirect:
    actor = _staff_user(request)
    if actor is None:
        messages.error(request, _STEP_UP_ERRORS["not_staff"])
        return redirect("crm:users")
    allowed, reason = _authorize_step_up(request)
    if not allowed:
        messages.error(request, reason)
        if reason == _STEP_UP_REQUIRED:
            return _step_up_redirect(reverse("crm:user_detail", args=[user_id]))
        return _user_action_redirect(user_id)
    if request.POST.get("confirm_delete") != "yes":
        messages.error(request, "Подтвердите необратимое удаление аккаунта.")
        return _user_action_redirect(user_id)
    result = delete_customer(
        actor=actor,
        target_id=user_id,
        ip=request.META.get("REMOTE_ADDR"),
        reason=str(request.POST.get("reason") or "").strip()[:255],
    )
    if not result.ok:
        if result.reason == "self_target":
            messages.error(request, "Нельзя удалить собственную учётную запись.")
        else:
            messages.error(request, "Аккаунт не найден.")
        return redirect("crm:users")
    message = {
        "deleted": "Аккаунт анонимизирован; персональные данные удалены.",
        "scheduled": "Запрос на удаление создан: действует 7-дневное окно отмены.",
        "window_active": "Окно отмены ещё действует; персональные данные не удалены.",
        "already_deleted": "Аккаунт уже удалён.",
    }.get(result.reason, "Операция выполнена.")
    messages.success(request, message)
    return _user_action_redirect(user_id)


@role_required(USERS_MANAGE)
@require_http_methods(["GET", "POST"])
def user_detail(request: HttpRequest, user_id: UUID) -> TemplateResponse | HttpResponseRedirect:
    """Account profile, results and leaderboard rows (§2.16.2).

    POST is accepted as a convenience dispatcher for the action buttons; the
    dedicated ``.../block/`` and ``.../delete/`` endpoints remain the canonical
    mutation routes for non-JS forms.
    """
    if request.method == "POST":
        action = str(request.POST.get("action") or "")
        if action in {"block", "unblock", "toggle"}:
            return _toggle_block(request, user_id)
        if action == "delete":
            return _delete_user(request, user_id)
        messages.error(request, "Неизвестное действие.")
        return _user_action_redirect(user_id)

    target = _customer_or_404(user_id)
    profile_obj = UserProfile.objects.filter(user=target).first()
    email = EmailAddress.objects.filter(user=target).first()
    return TemplateResponse(
        request,
        "crm/users/detail.html",
        {
            "title": f"Пользователь {target.login} · CRM",
            "target": target,
            "profile": profile_obj,
            "email": email,
            "results": recent_results(target),
            "leaderboard_entries": current_leaderboard_entries(target),
        },
    )


@role_required(USERS_MANAGE)
@require_POST
def user_toggle_block(request: HttpRequest, user_id: UUID) -> HttpResponseRedirect:
    return _toggle_block(request, user_id)


@role_required(USERS_MANAGE)
@require_POST
def user_delete(request: HttpRequest, user_id: UUID) -> HttpResponseRedirect:
    return _delete_user(request, user_id)


@role_required(USERS_MANAGE)
@require_GET
def user_export(request: HttpRequest, user_id: UUID) -> JsonResponse | HttpResponseRedirect:
    """Download personal data; TZ §2.16.1 requires step-up before export."""
    target = _customer_or_404(user_id)
    if not is_step_up_valid(request.session):
        return _step_up_redirect(reverse("crm:user_export", args=[user_id]))
    response = JsonResponse(
        export_account_data(target),
        json_dumps_params={"ensure_ascii": False, "indent": 2},
    )
    response["Content-Disposition"] = 'attachment; filename="breaktime-account.json"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@role_required(CONTENT_MANAGE)
def content_overview(request: HttpRequest) -> TemplateResponse:
    """Content hub for editors/owners: genres, tags, translations and pages."""
    return TemplateResponse(
        request,
        "crm/content.html",
        {
            "title": "Контент · CRM",
            "genres": Genre.objects.all()[:100],
            "tags": Tag.objects.all()[:100],
            "translation_count": TranslationEntry.objects.count(),
            "page_count": ContentPage.objects.count(),
        },
    )


def _content_write_guard(request: HttpRequest) -> HttpResponseRedirect | None:
    """Every content write requires the capability plus password + TOTP."""
    allowed, reason = _authorize_step_up(request)
    if allowed:
        return None
    messages.error(request, reason)
    if reason == _STEP_UP_REQUIRED:
        return _step_up_redirect(request.get_full_path())
    return redirect("crm:content")


def _active_languages() -> list[Language]:
    return list(Language.objects.filter(is_active=True).order_by("sort_order", "code"))


def _translation_form_initial(entry: TranslationEntry | None) -> dict[str, object]:
    if entry is None:
        return {}
    return {
        "value": entry.value,
        "status": entry.status,
        "is_machine_translated": entry.is_machine_translated,
    }


@role_required(CONTENT_MANAGE)
@require_GET
def content_translations(request: HttpRequest) -> TemplateResponse:
    """Filterable list of localization entries."""
    language_code = str(request.GET.get("language") or "").strip()
    status = str(request.GET.get("status") or "").strip()
    query = str(request.GET.get("q") or "").strip()

    entries = TranslationEntry.objects.select_related("language").order_by(
        "language__sort_order", "namespace", "key"
    )
    if language_code:
        entries = entries.filter(language__code=language_code)
    if status in {choice for choice, _label in TranslationEntry.STATUS_CHOICES}:
        entries = entries.filter(status=status)
    if query:
        entries = entries.filter(
            Q(namespace__icontains=query) | Q(key__icontains=query) | Q(value__icontains=query)
        )
    return TemplateResponse(
        request,
        "crm/content_translations.html",
        {
            "title": "Переводы · CRM",
            "entries": entries[:200],
            "languages": _active_languages(),
            "statuses": TranslationEntry.STATUS_CHOICES,
            "filters": {
                "language": language_code,
                "status": status,
                "q": query,
            },
        },
    )


@role_required(CONTENT_MANAGE)
@require_http_methods(["GET", "POST"])
def content_translation_new(request: HttpRequest) -> TemplateResponse | HttpResponseRedirect:
    """Create a localization entry; publishing still needs step-up."""
    form = TranslationEntryCreateForm(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        refused = _content_write_guard(request)
        if refused is not None:
            return refused
        if form.is_valid():
            result = create_translation(
                namespace=str(form.cleaned_data["namespace"]),
                key=str(form.cleaned_data["key"]),
                language=form.cleaned_data["language"],
                value=str(form.cleaned_data["value"]),
                status=str(form.cleaned_data["status"]),
                is_machine_translated=bool(form.cleaned_data.get("is_machine_translated", False)),
                actor=_staff_user(request),
            )
            if result.ok and result.entry is not None:
                if result.entry.status == TranslationEntry.STATUS_PUBLISHED:
                    record_audit(
                        actor=_staff_user(request),
                        action=AdminAuditLog.ACTION_TRANSLATION_PUBLISHED,
                        object_type="translation_entry",
                        object_id=result.entry.id,
                        after={"status": result.entry.status},
                        ip=request.META.get("REMOTE_ADDR"),
                    )
                messages.success(request, "Строка перевода сохранена.")
                return redirect("crm:content_translation", entry_id=result.entry.id)
            messages.error(request, result.message)
    return TemplateResponse(
        request,
        "crm/content_translation_edit.html",
        {
            "title": "Новая строка перевода · CRM",
            "form": form,
            "entry": None,
            "is_new": True,
        },
    )


@role_required(CONTENT_MANAGE)
@require_http_methods(["GET", "POST"])
def content_translation(
    request: HttpRequest, entry_id: UUID
) -> TemplateResponse | HttpResponseRedirect:
    """Edit/publish one localization entry; invalid values never replace copy."""
    entry = get_object_or_404(
        TranslationEntry.objects.select_related("language"),
        pk=entry_id,
    )
    form = TranslationEntryEditForm(
        request.POST if request.method == "POST" else None,
        initial=_translation_form_initial(entry),
    )
    if request.method == "POST":
        refused = _content_write_guard(request)
        if refused is not None:
            return refused
        if form.is_valid():
            previous_status = entry.status
            result = update_translation(
                entry,
                value=str(form.cleaned_data["value"]),
                status=str(form.cleaned_data["status"]),
                is_machine_translated=bool(form.cleaned_data.get("is_machine_translated", False)),
                actor=_staff_user(request),
            )
            if result.ok and result.entry is not None:
                if result.entry.status == TranslationEntry.STATUS_PUBLISHED:
                    record_audit(
                        actor=_staff_user(request),
                        action=AdminAuditLog.ACTION_TRANSLATION_PUBLISHED,
                        object_type="translation_entry",
                        object_id=result.entry.id,
                        before={"status": previous_status},
                        after={"status": result.entry.status},
                        ip=request.META.get("REMOTE_ADDR"),
                    )
                messages.success(request, "Строка перевода сохранена.")
                return redirect("crm:content_translation", entry_id=entry.id)
            messages.error(request, result.message)
    return TemplateResponse(
        request,
        "crm/content_translation_edit.html",
        {
            "title": "Строка перевода · CRM",
            "form": form,
            "entry": entry,
            "is_new": False,
        },
    )


@role_required(CONTENT_MANAGE)
@require_GET
def content_pages(request: HttpRequest) -> TemplateResponse:
    """List language-neutral content pages and their translations."""
    pages = ContentPage.objects.prefetch_related("translations__language").order_by("slug")
    return TemplateResponse(
        request,
        "crm/content_pages.html",
        {"title": "Страницы · CRM", "pages": pages},
    )


@role_required(CONTENT_MANAGE)
@require_http_methods(["GET", "POST"])
def content_page_new(request: HttpRequest) -> TemplateResponse | HttpResponseRedirect:
    """Create an empty content page and continue to its translations."""
    form = ContentPageForm(request.POST if request.method == "POST" else None)
    error = ""
    if request.method == "POST":
        refused = _content_write_guard(request)
        if refused is not None:
            return refused
        if form.is_valid():
            try:
                page = create_page(slug=str(form.cleaned_data["slug"]))
            except PageValidationError as exc:
                error = exc.message
            else:
                messages.success(request, "Страница создана. Добавьте перевод.")
                return redirect("crm:content_page", page_id=page.id)
        else:
            error = "Проверьте адрес страницы."
    return TemplateResponse(
        request,
        "crm/content_page_edit.html",
        {
            "title": "Новая страница · CRM",
            "form": form,
            "page": None,
            "translation": None,
            "translations": [],
            "languages": _active_languages(),
            "selected_language": "",
            "error": error,
            "is_new": True,
        },
    )


@role_required(CONTENT_MANAGE)
@require_http_methods(["GET", "POST"])
def content_page(request: HttpRequest, page_id: UUID) -> TemplateResponse | HttpResponseRedirect:
    """Edit translations and publish/unpublish a content page."""
    page = get_object_or_404(ContentPage, pk=page_id)
    languages = _active_languages()
    selected_code = str(request.POST.get("language") or request.GET.get("language") or "")
    translation = None
    if selected_code:
        translation = (
            page.translations.select_related("language")
            .filter(language__code=selected_code)
            .first()
        )
    elif page.translations.exists():
        translation = page.translations.select_related("language").first()

    form = ContentPageTranslationForm(
        request.POST if request.method == "POST" else None,
        initial={
            "language": translation.language_id if translation else None,
            "title": translation.title if translation else "",
            "body": translation.body if translation else "",
            "seo_title": translation.seo_title if translation else "",
            "seo_description": translation.seo_description if translation else "",
        },
    )
    error = ""
    if request.method == "POST":
        refused = _content_write_guard(request)
        if refused is not None:
            return refused
        action = str(request.POST.get("action") or "save_translation")
        if action in {"publish", "unpublish"}:
            try:
                if action == "publish":
                    publish_page(page)
                    record_audit(
                        actor=_staff_user(request),
                        action=AdminAuditLog.ACTION_PAGE_PUBLISHED,
                        object_type="content_page",
                        object_id=page.id,
                        after={"is_published": True},
                        ip=request.META.get("REMOTE_ADDR"),
                    )
                    messages.success(request, "Страница опубликована.")
                else:
                    unpublish_page(page)
                    messages.success(request, "Публикация страницы снята.")
            except PageValidationError as exc:
                error = exc.message
                messages.error(request, error)
            return redirect("crm:content_page", page_id=page.id)

        if form.is_valid():
            language = form.cleaned_data["language"]
            result = save_page_translation(
                page,
                language=language,
                title=str(form.cleaned_data["title"]),
                body=str(form.cleaned_data.get("body") or ""),
                seo_title=str(form.cleaned_data.get("seo_title") or ""),
                seo_description=str(form.cleaned_data.get("seo_description") or ""),
            )
            if result.ok and result.translation is not None:
                messages.success(request, "Перевод страницы сохранён.")
                return redirect(
                    f"{reverse('crm:content_page', args=[page.id])}"
                    f"?language={result.translation.language.code}"
                )
            error = result.message
            messages.error(request, error)
        else:
            error = "Проверьте поля перевода."
            messages.error(request, error)

    selected_code = (
        translation.language.code
        if translation is not None
        else (languages[0].code if languages else "")
    )
    return TemplateResponse(
        request,
        "crm/content_page_edit.html",
        {
            "title": f"{page.slug} · CRM",
            "form": form,
            "page": page,
            "translation": translation,
            "translations": list(page.translations.select_related("language")),
            "languages": languages,
            "selected_language": selected_code,
            "error": error,
            "is_new": False,
        },
    )


# --- Жанры и теги (§2.16.2) ---------------------------------------------


def _parse_uuid(raw: object) -> UUID | None:
    try:
        return UUID(str(raw))
    except ValueError:
        return None


def _requested_language(request: HttpRequest) -> Language | None:
    """Resolve a language from a posted PK or a GET ``?language=<code>``."""
    raw = str(request.POST.get("language") or request.GET.get("language") or "").strip()
    if not raw:
        return None
    pk = _parse_uuid(raw)
    if pk is not None:
        return Language.objects.filter(pk=pk).first()
    return Language.objects.filter(code=raw, is_active=True).first()


def _translation_payload(
    cleaned: dict[str, Any] | None,
) -> TranslationPayload | None:
    """Build a translation payload; blank pairs mean "do not touch"."""
    if not cleaned:
        return None
    language = cleaned.get("language")
    name = str(cleaned.get("name") or "").strip()
    slug = str(cleaned.get("slug") or "").strip()
    if not isinstance(language, Language) or not name or not slug:
        return None
    return TranslationPayload(
        language=language,
        name=name,
        slug=slug,
        description=str(cleaned.get("description") or ""),
        seo_title=str(cleaned.get("seo_title") or ""),
        seo_description=str(cleaned.get("seo_description") or ""),
    )


@role_required(CONTENT_MANAGE)
@require_GET
def genres_list(request: HttpRequest) -> TemplateResponse:
    """Genres ordered by their CRM-defined ``sort_order``."""
    genres = Genre.objects.prefetch_related("translations__language").order_by("sort_order", "code")
    return TemplateResponse(
        request,
        "crm/genres/list.html",
        {"title": "Жанры · CRM", "genres": genres},
    )


@role_required(CONTENT_MANAGE)
@require_http_methods(["GET", "POST"])
def genre_new(request: HttpRequest) -> TemplateResponse | HttpResponseRedirect:
    languages = _active_languages()
    default_language = languages[0] if languages else None
    form = GenreForm(
        request.POST if request.method == "POST" else None,
        request.FILES if request.method == "POST" else None,
    )
    translation_form = GenreTranslationForm(
        request.POST if request.method == "POST" else None,
        show_language=True,
        initial={"language": default_language.id if default_language else None},
    )
    if request.method == "POST" and form.is_valid() and translation_form.is_valid():
        result = create_genre(
            code=str(form.cleaned_data["code"]),
            sort_order=int(form.cleaned_data.get("sort_order") or 0),
            image=form.cleaned_data.get("image"),
            translation=_translation_payload(translation_form.cleaned_data),
            actor=_staff_user(request),
            ip=request.META.get("REMOTE_ADDR"),
        )
        if result.ok and isinstance(result.instance, Genre):
            messages.success(request, "Жанр создан.")
            return redirect("crm:genre_edit", genre_id=result.instance.id)
        messages.error(request, result.message)
    return TemplateResponse(
        request,
        "crm/genres/form.html",
        {
            "title": "Новый жанр · CRM",
            "genre": None,
            "form": form,
            "translation_form": translation_form,
            "languages": languages,
            "selected_code": default_language.code if default_language else "",
            "translations": [],
            "is_new": True,
        },
    )


@role_required(CONTENT_MANAGE)
@require_http_methods(["GET", "POST"])
def genre_edit(request: HttpRequest, genre_id: UUID) -> TemplateResponse | HttpResponseRedirect:
    genre = get_object_or_404(Genre, pk=genre_id)
    languages = _active_languages()
    requested = _requested_language(request)
    translation = None
    if requested is not None:
        translation = (
            genre.translations.select_related("language").filter(language=requested).first()
        )
    if translation is None and requested is None:
        translation = (
            genre.translations.select_related("language")
            .order_by("language__sort_order", "language__code")
            .first()
        )
        if translation is not None:
            requested = translation.language
    if requested is None and languages:
        requested = languages[0]

    form = GenreForm(
        request.POST if request.method == "POST" else None,
        request.FILES if request.method == "POST" else None,
        initial=None
        if request.method == "POST"
        else {
            "code": genre.code,
            "sort_order": genre.sort_order,
        },
    )
    translation_form = GenreTranslationForm(
        request.POST if request.method == "POST" else None,
        initial=None
        if request.method == "POST"
        else {
            "language": requested.id if requested else None,
            "name": translation.name if translation else "",
            "slug": translation.slug if translation else "",
            "description": translation.description if translation else "",
            "seo_title": translation.seo_title if translation else "",
            "seo_description": translation.seo_description if translation else "",
        },
    )
    if request.method == "POST" and form.is_valid() and translation_form.is_valid():
        result = update_genre(
            genre,
            code=str(form.cleaned_data["code"]),
            sort_order=int(form.cleaned_data.get("sort_order") or 0),
            image=form.cleaned_data.get("image"),
            clear_image=bool(form.cleaned_data.get("clear_image")),
            translation=_translation_payload(translation_form.cleaned_data),
            actor=_staff_user(request),
            ip=request.META.get("REMOTE_ADDR"),
        )
        if result.ok:
            messages.success(request, "Жанр сохранён.")
            return redirect("crm:genre_edit", genre_id=genre.id)
        messages.error(request, result.message)

    return TemplateResponse(
        request,
        "crm/genres/form.html",
        {
            "title": f"{genre.code} · CRM",
            "genre": genre,
            "form": form,
            "translation_form": translation_form,
            "languages": languages,
            "selected_code": requested.code if requested else "",
            "translations": list(
                genre.translations.select_related("language").order_by(
                    "language__sort_order", "language__code"
                )
            ),
            "is_new": False,
        },
    )


@role_required(CONTENT_MANAGE)
@require_POST
def genre_delete(request: HttpRequest, genre_id: UUID) -> HttpResponseRedirect:
    genre = get_object_or_404(Genre, pk=genre_id)
    result = delete_genre(
        genre,
        actor=_staff_user(request),
        ip=request.META.get("REMOTE_ADDR"),
    )
    if result.ok:
        messages.success(request, "Жанр удалён.")
        return redirect("crm:genres")
    messages.error(request, result.message)
    return redirect("crm:genre_edit", genre_id=genre.id)


@role_required(CONTENT_MANAGE)
@require_GET
def tags_list(request: HttpRequest) -> TemplateResponse:
    """Tags with an optional «requires translation» queue filter."""
    queue = str(request.GET.get("queue") or "").strip().lower()
    needs_flag = str(
        request.GET.get("needs_translation") or request.GET.get("translation_queue") or ""
    ).lower()
    show_queue = queue in {"requires-translation", "requires_translation", "1"} or needs_flag in {
        "1",
        "true",
        "yes",
    }
    tags = Tag.objects.prefetch_related("translations__language").order_by("code")
    if show_queue:
        tags = tags.filter(needs_translation=True)
    return TemplateResponse(
        request,
        "crm/tags/list.html",
        {
            "title": "Теги · CRM",
            "tags": tags,
            "show_queue": show_queue,
            "queue_count": Tag.objects.filter(needs_translation=True).count(),
        },
    )


@role_required(CONTENT_MANAGE)
@require_http_methods(["GET", "POST"])
def tag_new(request: HttpRequest) -> TemplateResponse | HttpResponseRedirect:
    languages = _active_languages()
    default_language = languages[0] if languages else None
    form = TagForm(request.POST if request.method == "POST" else None)
    translation_form = TagTranslationForm(
        request.POST if request.method == "POST" else None,
        show_language=True,
        initial={"language": default_language.id if default_language else None},
    )
    if request.method == "POST" and form.is_valid() and translation_form.is_valid():
        result = create_tag(
            code=str(form.cleaned_data["code"]),
            needs_translation=bool(form.cleaned_data.get("needs_translation")),
            translation=_translation_payload(translation_form.cleaned_data),
            actor=_staff_user(request),
            ip=request.META.get("REMOTE_ADDR"),
        )
        if result.ok and isinstance(result.instance, Tag):
            messages.success(request, "Тег создан.")
            return redirect("crm:tag_edit", tag_id=result.instance.id)
        messages.error(request, result.message)
    return TemplateResponse(
        request,
        "crm/tags/form.html",
        {
            "title": "Новый тег · CRM",
            "tag": None,
            "form": form,
            "translation_form": translation_form,
            "languages": languages,
            "selected_code": default_language.code if default_language else "",
            "translations": [],
            "is_new": True,
        },
    )


@role_required(CONTENT_MANAGE)
@require_http_methods(["GET", "POST"])
def tag_edit(request: HttpRequest, tag_id: UUID) -> TemplateResponse | HttpResponseRedirect:
    tag = get_object_or_404(Tag, pk=tag_id)
    languages = _active_languages()
    requested = _requested_language(request)
    translation = None
    if requested is not None:
        translation = tag.translations.select_related("language").filter(language=requested).first()
    if translation is None and requested is None:
        translation = (
            tag.translations.select_related("language")
            .order_by("language__sort_order", "language__code")
            .first()
        )
        if translation is not None:
            requested = translation.language
    if requested is None and languages:
        requested = languages[0]

    form = TagForm(
        request.POST if request.method == "POST" else None,
        initial=None
        if request.method == "POST"
        else {
            "code": tag.code,
            "needs_translation": tag.needs_translation,
        },
    )
    translation_form = TagTranslationForm(
        request.POST if request.method == "POST" else None,
        initial=None
        if request.method == "POST"
        else {
            "language": requested.id if requested else None,
            "name": translation.name if translation else "",
            "slug": translation.slug if translation else "",
        },
    )
    if request.method == "POST" and form.is_valid() and translation_form.is_valid():
        result = update_tag(
            tag,
            code=str(form.cleaned_data["code"]),
            needs_translation=bool(form.cleaned_data.get("needs_translation")),
            translation=_translation_payload(translation_form.cleaned_data),
            actor=_staff_user(request),
            ip=request.META.get("REMOTE_ADDR"),
        )
        if result.ok:
            messages.success(request, "Тег сохранён.")
            return redirect("crm:tag_edit", tag_id=tag.id)
        messages.error(request, result.message)

    return TemplateResponse(
        request,
        "crm/tags/form.html",
        {
            "title": f"{tag.code} · CRM",
            "tag": tag,
            "form": form,
            "translation_form": translation_form,
            "languages": languages,
            "selected_code": requested.code if requested else "",
            "translations": list(
                tag.translations.select_related("language").order_by(
                    "language__sort_order", "language__code"
                )
            ),
            "is_new": False,
        },
    )


@role_required(CONTENT_MANAGE)
@require_POST
def tag_delete(request: HttpRequest, tag_id: UUID) -> HttpResponseRedirect:
    tag = get_object_or_404(Tag, pk=tag_id)
    result = delete_tag(
        tag,
        actor=_staff_user(request),
        ip=request.META.get("REMOTE_ADDR"),
    )
    if result.ok:
        messages.success(request, "Тег удалён.")
        return redirect("crm:tags")
    messages.error(request, result.message)
    return redirect("crm:tag_edit", tag_id=tag.id)


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


MODERATION_PAGE_SIZE = 50


@role_required(MODERATION_MANAGE)
def moderation_queue(request: HttpRequest) -> TemplateResponse:
    """Rating and complaint queues with filters, aggregates and pagination (§2.16.2)."""
    rating_filters = parse_rating_filters(request.GET)
    rating_queryset = filter_rating_votes(rating_filters)
    # The aggregate always covers every filtered row, never just one page.
    rating_summary = summarize_rating_votes(rating_queryset)
    # A bare ``page`` advances both queues (deep links keep working); the
    # table-specific parameters let the two paginators move independently.
    rating_page = Paginator(rating_queryset, MODERATION_PAGE_SIZE).get_page(
        request.GET.get("ratings_page", request.GET.get("page"))
    )
    complaint_page = Paginator(
        Complaint.objects.select_related("game", "rating", "reporter", "assigned_to").order_by(
            "-created_at", "-id"
        ),
        MODERATION_PAGE_SIZE,
    ).get_page(request.GET.get("complaints_page", request.GET.get("page")))
    # Rating links keep the active filters; both page parameters are dropped so
    # each queue advances independently.
    rating_params = request.GET.copy()
    rating_params.pop("ratings_page", None)
    rating_params.pop("complaints_page", None)
    rating_params.pop("page", None)
    # Keep the other queue's current page when one paginator moves.
    complaint_params = rating_params.copy()
    if request.GET.get("complaints_page"):
        rating_params["complaints_page"] = request.GET["complaints_page"]
    if request.GET.get("ratings_page"):
        complaint_params["ratings_page"] = request.GET["ratings_page"]
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
            "votes": rating_page.object_list,
            "rating_page_obj": rating_page,
            "rating_pagination_query": rating_params.urlencode(),
            "rating_filters": rating_filters,
            "rating_summary": rating_summary,
            "rating_games": rating_game_options(),
            "rating_statuses": RATING_STATUS_CHOICES,
            "rating_values": RATING_VALUE_CHOICES,
            "complaints": complaint_page.object_list,
            "complaints_page_obj": complaint_page,
            "complaint_pagination_query": complaint_params.urlencode(),
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
    "analytics_dashboard",
    "analytics_export",
    "audit_log",
    "complaint_assign",
    "complaint_reject",
    "complaint_resolve",
    "content_overview",
    "content_page",
    "content_page_new",
    "content_pages",
    "content_translation",
    "content_translation_new",
    "content_translations",
    "dashboard",
    "game_detail",
    "game_publish",
    "game_rollback",
    "games_list",
    "genre_delete",
    "genre_edit",
    "genre_new",
    "genres_list",
    "login_view",
    "logout_view",
    "moderation_queue",
    "rating_hide",
    "rating_restore",
    "seo_diagnostics",
    "staff_management",
    "step_up",
    "tag_delete",
    "tag_edit",
    "tag_new",
    "tags_list",
    "version_package_download",
    "version_report_download",
    "version_runtime_download",
    "wizard_analysis",
    "wizard_card",
    "wizard_check",
    "wizard_publish",
    "wizard_report",
    "wizard_upload",
]
