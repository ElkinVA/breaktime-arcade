from __future__ import annotations

import logging
from typing import Any, cast

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.accounts.forms import (
    DeleteAccountForm,
    DisableTwoFactorForm,
    LoginForm,
    PasswordResetRequestForm,
    ProfileForm,
    RecoveryCodeForm,
    RegistrationForm,
    SetPasswordForm,
    TwoFactorCodeForm,
)
from apps.accounts.models import (
    AccountToken,
    EmailAddress,
    LoginEvent,
    User,
    UserLegalAcceptance,
    UserProfile,
)
from apps.accounts.services.audit import record_login_event
from apps.accounts.services.email import (
    find_verified_email,
    password_reset_token_user,
    send_2fa_change_notice,
    send_email_change_notice,
    send_password_reset_email,
    send_verification_email,
    verify_email_token,
)
from apps.accounts.services.profile import (
    cancel_deletion,
    ensure_profile,
    update_nickname,
    update_settings,
)
from apps.accounts.services.rate_limit import (
    clear_login_failures,
    login_allowed,
    password_reset_allowed,
    record_login_failure,
    record_password_reset,
    record_registration,
    record_two_factor_failure,
    registration_allowed,
    two_factor_allowed,
)
from apps.accounts.services.tokens import consume_token, invalidate_tokens
from apps.accounts.services.two_factor import (
    disable_totp,
    enable_totp,
    generate_owner_recovery_code,
    generate_recovery_codes,
    generate_secret,
    provisioning_uri,
    verify_owner_recovery_code,
    verify_recovery_code,
    verify_totp,
)

logger = logging.getLogger(__name__)


def _ip(request: HttpRequest) -> str | None:
    return request.META.get("REMOTE_ADDR")


def _user(request: HttpRequest) -> User:
    return cast(User, request.user)


def _safe_next(request: HttpRequest, default: str) -> str:
    candidate = request.POST.get("next") or request.GET.get("next") or ""
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return default


def _pre_2fa_user(request: HttpRequest) -> User | None:
    user_id = request.session.get("2fa_user_id")
    if not user_id:
        return None
    user = User.objects.filter(pk=user_id, is_active=True, is_staff=True).first()
    if user is None:
        _clear_pre_2fa(request)
    return user


def _clear_pre_2fa(request: HttpRequest) -> None:
    for key in ("2fa_user_id", "2fa_backend", "2fa_next", "2fa_setup_secret"):
        request.session.pop(key, None)


def _finish_2fa_login(request: HttpRequest, user: User) -> str:
    backend = request.session.get("2fa_backend", "django.contrib.auth.backends.ModelBackend")
    next_url = str(request.session.get("2fa_next") or reverse("account:profile"))
    _clear_pre_2fa(request)
    auth_login(request, user, backend=backend)
    request.session["ba_2fa_verified"] = True
    return next_url


def register(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("account:profile")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST":
        if not registration_allowed(_ip(request)):
            messages.error(request, "Слишком много попыток регистрации. Попробуйте позже.")
        elif form.is_valid():
            form.language_code = getattr(request, "LANGUAGE_CODE", "en")
            try:
                user = form.save(ip=_ip(request))
            except (ValidationError, IntegrityError) as exc:
                error = str(exc) if isinstance(exc, ValidationError) else "Аккаунт уже существует."
                form.add_error(None, error)
            else:
                record_registration(_ip(request))
                if EmailAddress.objects.filter(user=user).exists():
                    try:
                        send_verification_email(user, request)
                    except Exception:
                        logger.warning("account.email.verification_send_failed", exc_info=True)
                        messages.warning(
                            request,
                            "Аккаунт создан, но письмо подтверждения не отправлено.",
                        )
                auth_login(request, user)
                messages.success(request, "Аккаунт создан.")
                return redirect("account:profile")
    return render(
        request,
        "accounts/register.html",
        {
            "form": form,
            "terms_url": settings.LEGAL_TERMS_URL,
            "privacy_url": settings.LEGAL_PRIVACY_URL,
        },
    )


def login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("account:profile")
    form = LoginForm(request, data=request.POST or None)
    if request.method == "POST":
        username = request.POST.get("username", "")
        if not login_allowed(username, _ip(request)):
            messages.error(request, "Слишком много попыток входа. Попробуйте позже.")
        elif form.is_valid():
            user = form.get_user()
            if user.is_staff:
                request.session.cycle_key()
                request.session["2fa_user_id"] = str(user.pk)
                request.session["2fa_backend"] = getattr(
                    user, "backend", "django.contrib.auth.backends.ModelBackend"
                )
                request.session["2fa_next"] = _safe_next(request, reverse("account:profile"))
                clear_login_failures(username, _ip(request))
                record_login_event(
                    event=LoginEvent.EVENT_PASSWORD_OK,
                    user=user,
                    ip=_ip(request),
                )
                if user.totp_confirmed_at is None:
                    return redirect("accounts:two_factor_setup")
                return redirect("accounts:two_factor_verify")
            auth_login(request, user)
            clear_login_failures(username, _ip(request))
            record_login_event(
                event=LoginEvent.EVENT_LOGIN_SUCCESS,
                user=user,
                ip=_ip(request),
            )
            return redirect(_safe_next(request, reverse("account:profile")))
        else:
            record_login_failure(username, _ip(request))
            record_login_event(
                event=LoginEvent.EVENT_LOGIN_FAILED,
                subject=username,
                ip=_ip(request),
            )
    return render(request, "accounts/login.html", {"form": form})


@require_POST
def logout_view(request: HttpRequest) -> HttpResponse:
    auth_logout(request)
    return redirect("catalog:home")


def two_factor_verify(request: HttpRequest) -> HttpResponse:
    user = _pre_2fa_user(request)
    if user is None:
        return redirect("accounts:login")
    if user.totp_confirmed_at is None:
        return redirect("accounts:two_factor_setup")
    form = TwoFactorCodeForm(request.POST or None)
    if request.method == "POST":
        if not two_factor_allowed(str(user.pk), _ip(request)):
            form.add_error(None, "Слишком много попыток. Попробуйте позже.")
        elif form.is_valid():
            if verify_totp(user, str(form.cleaned_data["code"])):
                record_login_event(
                    event=LoginEvent.EVENT_2FA_SUCCESS,
                    user=user,
                    ip=_ip(request),
                )
                return redirect(_finish_2fa_login(request, user))
            record_two_factor_failure(str(user.pk), _ip(request))
            record_login_event(
                event=LoginEvent.EVENT_2FA_FAILED,
                user=user,
                ip=_ip(request),
            )
            form.add_error(None, "Неверный код.")
    return render(request, "accounts/two_factor_verify.html", {"form": form})


def two_factor_recovery(request: HttpRequest) -> HttpResponse:
    user = _pre_2fa_user(request)
    if user is None:
        return redirect("accounts:login")
    form = RecoveryCodeForm(request.POST or None)
    if request.method == "POST":
        if not two_factor_allowed(str(user.pk), _ip(request)):
            form.add_error(None, "Слишком много попыток. Попробуйте позже.")
        elif form.is_valid():
            if verify_recovery_code(user, str(form.cleaned_data["code"])):
                logger.warning("account.2fa.recovery_used", extra={"user_id": str(user.pk)})
                record_login_event(
                    event=LoginEvent.EVENT_RECOVERY_USED,
                    user=user,
                    ip=_ip(request),
                )
                messages.warning(request, "Использован резервный код. Сгенерируйте новый набор.")
                return redirect(_finish_2fa_login(request, user))
            record_two_factor_failure(str(user.pk), _ip(request))
            record_login_event(
                event=LoginEvent.EVENT_2FA_FAILED,
                user=user,
                ip=_ip(request),
            )
            form.add_error(None, "Неверный резервный код.")
    return render(request, "accounts/two_factor_recovery.html", {"form": form})


def two_factor_owner_recovery(request: HttpRequest) -> HttpResponse:
    user = _pre_2fa_user(request)
    if user is None:
        return redirect("accounts:login")
    if not user.is_superuser:
        return redirect("accounts:two_factor_verify")
    form = RecoveryCodeForm(request.POST or None)
    if request.method == "POST":
        if not two_factor_allowed(str(user.pk), _ip(request)):
            form.add_error(None, "Слишком много попыток. Попробуйте позже.")
        elif form.is_valid():
            if verify_owner_recovery_code(user, str(form.cleaned_data["code"])):
                record_login_event(
                    event=LoginEvent.EVENT_OWNER_RECOVERY_USED,
                    user=user,
                    ip=_ip(request),
                )
                logger.warning("account.2fa.owner_recovery_used", extra={"user_id": str(user.pk)})
                disable_totp(user)
                messages.warning(
                    request,
                    "Использован офлайн-код владельца. Настройте 2FA заново.",
                )
                return redirect("accounts:two_factor_setup")
            record_two_factor_failure(str(user.pk), _ip(request))
            form.add_error(None, "Неверный код владельца.")
    return render(request, "accounts/two_factor_owner_recovery.html", {"form": form})


def two_factor_setup(request: HttpRequest) -> HttpResponse:
    user = _pre_2fa_user(request)
    authenticated_staff = request.user.is_authenticated and _user(request).is_staff
    if user is None:
        if not authenticated_staff:
            return redirect("accounts:login")
        user = _user(request)
    if user.totp_confirmed_at is not None:
        if request.user.is_authenticated:
            return redirect("account:profile")
        return redirect("accounts:two_factor_verify")

    secret = request.session.get("2fa_setup_secret")
    if not secret:
        secret = generate_secret()
        request.session["2fa_setup_secret"] = secret
    form = TwoFactorCodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            recovery_codes = enable_totp(user, secret, str(form.cleaned_data["code"]))
        except ValueError:
            form.add_error(None, "Неверный код.")
        else:
            request.session.pop("2fa_setup_secret", None)
            owner_code = generate_owner_recovery_code(user) if user.is_superuser else None
            logger.info("account.2fa.enabled", extra={"user_id": str(user.pk)})
            record_login_event(
                event=LoginEvent.EVENT_2FA_ENABLED,
                user=user,
                ip=_ip(request),
            )
            try:
                send_2fa_change_notice(user, enabled=True)
            except Exception:
                logger.warning("account.2fa.notice_failed", exc_info=True)
            if request.user.is_authenticated:
                request.session["ba_2fa_verified"] = True
                return render(
                    request,
                    "accounts/two_factor_setup.html",
                    {
                        "recovery_codes": recovery_codes,
                        "owner_recovery_code": owner_code,
                        "secret": secret,
                        "form": None,
                    },
                )
            next_url = _finish_2fa_login(request, user)
            return render(
                request,
                "accounts/two_factor_setup.html",
                {
                    "recovery_codes": recovery_codes,
                    "owner_recovery_code": owner_code,
                    "secret": secret,
                    "form": None,
                    "next_url": next_url,
                },
            )
    return render(
        request,
        "accounts/two_factor_setup.html",
        {
            "form": form,
            "secret": secret,
            "provisioning_uri": provisioning_uri(user, secret),
        },
    )


@login_required(login_url="accounts:login")
def two_factor_regenerate(request: HttpRequest) -> HttpResponse:
    user = _user(request)
    if not user.is_staff:
        raise PermissionDenied
    form = DisableTwoFactorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if not user.check_password(str(form.cleaned_data["password"])):
            form.add_error("password", "Неверный пароль.")
        elif not verify_totp(user, str(form.cleaned_data["code"])):
            form.add_error("code", "Неверный код.")
        else:
            codes = generate_recovery_codes(user)
            owner_code = generate_owner_recovery_code(user) if user.is_superuser else None
            return render(
                request,
                "accounts/two_factor_recovery_codes.html",
                {"recovery_codes": codes, "owner_recovery_code": owner_code},
            )
    return render(request, "accounts/two_factor_regenerate.html", {"form": form})


@login_required(login_url="accounts:login")
def two_factor_disable(request: HttpRequest) -> HttpResponse:
    user = _user(request)
    if not user.is_staff:
        raise PermissionDenied
    form = DisableTwoFactorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if not user.check_password(str(form.cleaned_data["password"])):
            form.add_error("password", "Неверный пароль.")
        elif not verify_totp(user, str(form.cleaned_data["code"])):
            form.add_error("code", "Неверный код.")
        else:
            _invalidate_other_sessions(request, user)
            disable_totp(user)
            logger.info("account.2fa.disabled", extra={"user_id": str(user.pk)})
            record_login_event(
                event=LoginEvent.EVENT_2FA_DISABLED,
                user=user,
                ip=_ip(request),
            )
            try:
                send_2fa_change_notice(user, enabled=False)
            except Exception:
                logger.warning("account.2fa.notice_failed", exc_info=True)
            auth_logout(request)
            messages.success(request, "2FA отключена. Войдите снова для настройки.")
            return redirect("accounts:login")
    return render(request, "accounts/two_factor_disable.html", {"form": form})


def verify_email(request: HttpRequest, token: str) -> HttpResponse:
    with transaction.atomic():
        email = verify_email_token(token)
    if email is None:
        messages.error(request, "Ссылка недействительна или истекла.")
    else:
        messages.success(request, "Email подтверждён.")
    return redirect("account:profile" if request.user.is_authenticated else "accounts:login")


@login_required(login_url="accounts:login")
@require_POST
def resend_verification(request: HttpRequest) -> HttpResponse:
    try:
        send_verification_email(_user(request), request)
    except Exception:
        messages.error(request, "Не удалось отправить письмо. Попробуйте позже.")
    else:
        messages.info(request, "Если email указан и не подтверждён, письмо отправлено.")
    return redirect("account:profile")


def password_reset_request(request: HttpRequest) -> HttpResponse:
    form = PasswordResetRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = str(form.cleaned_data["email"])
        if password_reset_allowed(email, _ip(request)):
            record_password_reset(email, _ip(request))
            target = find_verified_email(email)
            if target is not None:
                try:
                    send_password_reset_email(target, request)
                except Exception:
                    logger.warning("account.email.password_reset_send_failed", exc_info=True)
        messages.success(
            request,
            "Если для этого email есть подтверждённый аккаунт, письмо отправлено.",
        )
        return redirect("accounts:login")
    return render(request, "accounts/password_reset.html", {"form": form})


def password_reset_confirm(request: HttpRequest, token: str) -> HttpResponse:
    token_user = password_reset_token_user(token)
    if token_user is None:
        messages.error(request, "Ссылка недействительна или истекла.")
        return redirect("accounts:password_reset")
    form = SetPasswordForm(request.POST or None, user=token_user)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            token_obj = consume_token(token, AccountToken.PURPOSE_PASSWORD_RESET)
            if token_obj is None:
                messages.error(request, "Ссылка недействительна или истекла.")
                return redirect("accounts:password_reset")
            user = token_obj.user
            user.set_password(str(form.cleaned_data["password1"]))
            user.save(update_fields=["password"])
            invalidate_tokens(user, AccountToken.PURPOSE_PASSWORD_RESET)
            _invalidate_other_sessions(request, user)
        messages.success(request, "Пароль изменён. Войдите с новым паролем.")
        return redirect("accounts:login")
    return render(request, "accounts/password_reset_confirm.html", {"form": form, "token": token})


@login_required(login_url="accounts:login")
def profile(request: HttpRequest) -> HttpResponse:
    user = _user(request)
    profile_obj = ensure_profile(user)
    email = EmailAddress.objects.filter(user=user).first()
    legal = list(UserLegalAcceptance.objects.filter(user=user).order_by("-accepted_at"))
    return render(
        request,
        "accounts/profile.html",
        {"profile": profile_obj, "email_address": email, "legal_acceptances": legal},
    )


@login_required(login_url="accounts:login")
def profile_edit(request: HttpRequest) -> HttpResponse:
    user = _user(request)
    profile_obj = ensure_profile(user)
    form = ProfileForm(request.POST or None, user=user)
    if request.method == "POST" and form.is_valid():
        try:
            nickname = str(form.cleaned_data.get("nickname") or "")
            if nickname and nickname.casefold() != profile_obj.nickname.casefold():
                update_nickname(user, nickname)
            _update_email(request, user, str(form.cleaned_data.get("email") or ""))
            update_settings(
                user,
                language_code=str(form.cleaned_data.get("language_code") or ""),
                theme=str(form.cleaned_data.get("theme") or "dark"),
                marketing_consent=bool(form.cleaned_data.get("marketing_consent")),
            )
        except (ValidationError, IntegrityError) as exc:
            error = (
                str(exc) if isinstance(exc, ValidationError) else "Не удалось сохранить профиль."
            )
            form.add_error(None, error)
        else:
            messages.success(request, "Профиль обновлён.")
            return redirect("account:profile")
    return render(request, "accounts/profile_edit.html", {"form": form, "profile": profile_obj})


@login_required(login_url="accounts:login")
def password_change(request: HttpRequest) -> HttpResponse:
    form = PasswordChangeForm(_user(request), request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        invalidate_tokens(user, AccountToken.PURPOSE_PASSWORD_RESET)
        _invalidate_other_sessions(request, user)
        messages.success(request, "Пароль изменён; другие сессии завершены.")
        return redirect("account:profile")
    return render(request, "accounts/password_change.html", {"form": form})


@login_required(login_url="accounts:login")
def export_account(request: HttpRequest) -> JsonResponse:
    user = _user(request)
    profile_obj = UserProfile.objects.filter(user=user).first()
    email = EmailAddress.objects.filter(user=user).first()
    legal = list(
        UserLegalAcceptance.objects.filter(user=user).values(
            "terms_version", "privacy_version", "accepted_at"
        )
    )
    data: dict[str, Any] = {
        "login": user.login,
        "created_at": user.created_at.isoformat(),
        "profile": None
        if profile_obj is None
        else {
            "nickname": profile_obj.nickname,
            "theme": profile_obj.theme,
            "language": profile_obj.language.code
            if profile_obj.language_id and profile_obj.language
            else None,
            "age_confirmed_at": profile_obj.age_confirmed_at.isoformat()
            if profile_obj.age_confirmed_at
            else None,
            "marketing_consent_at": profile_obj.marketing_consent_at.isoformat()
            if profile_obj.marketing_consent_at
            else None,
            "deletion_requested_at": profile_obj.deletion_requested_at.isoformat()
            if profile_obj.deletion_requested_at
            else None,
        },
        "email": None
        if email is None
        else {
            "email": email.email,
            "verified_at": email.verified_at.isoformat() if email.verified_at else None,
        },
        "legal_acceptances": legal,
    }
    response = JsonResponse(data, json_dumps_params={"ensure_ascii": False, "indent": 2})
    response["Content-Disposition"] = 'attachment; filename="breaktime-account.json"'
    return response


@login_required(login_url="accounts:login")
def delete_account(request: HttpRequest) -> HttpResponse:
    user = _user(request)
    form = DeleteAccountForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if not user.check_password(str(form.cleaned_data["password"])):
            form.add_error("password", "Неверный пароль.")
        elif str(form.cleaned_data["confirmation"]).strip().upper() != "DELETE":
            form.add_error("confirmation", "Введите DELETE для подтверждения.")
        else:
            profile_obj = UserProfile.objects.get(user=user)
            profile_obj.deletion_requested_at = timezone.now()
            profile_obj.save(update_fields=["deletion_requested_at", "updated_at"])
            messages.success(
                request,
                "Удаление запрошено. Аккаунт будет анонимизирован через 7 дней; "
                "отмена доступна в профиле.",
            )
            return redirect("account:profile")
    return render(request, "accounts/delete_account.html", {"form": form})


@login_required(login_url="accounts:login")
@require_POST
def delete_cancel(request: HttpRequest) -> HttpResponse:
    try:
        cancel_deletion(_user(request))
    except Exception as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Запрос на удаление отменён.")
    return redirect("account:profile")


def _update_email(request: HttpRequest, user: User, value: str) -> None:
    current = EmailAddress.objects.filter(user=user).first()
    if not value:
        if current is not None:
            current.delete()
            invalidate_tokens(user, AccountToken.PURPOSE_EMAIL_VERIFY)
        return
    if current is not None and current.email.casefold() == value.casefold():
        return
    if current is not None:
        try:
            send_email_change_notice(current, request)
        except Exception:
            logger.warning("account.email.change_notice_failed", exc_info=True)
    with transaction.atomic():
        if current is None:
            EmailAddress.objects.create(user=user, email=value)
        else:
            current.email = value
            current.verified_at = None
            current.bounce_at = None
            current.save(update_fields=["email", "verified_at", "bounce_at", "updated_at"])
    try:
        send_verification_email(user, request)
    except Exception:
        logger.warning("account.email.change_verification_send_failed", exc_info=True)
        messages.warning(request, "Email изменён, но письмо подтверждения не отправлено.")


def _invalidate_other_sessions(request: HttpRequest, user: User) -> None:
    current_key = request.session.session_key
    for session in Session.objects.filter(expire_date__gt=timezone.now()):
        if session.session_key == current_key:
            continue
        data = session.get_decoded()
        if str(data.get("_auth_user_id")) == str(user.pk):
            session.delete()
