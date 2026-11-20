from __future__ import annotations

from typing import Any, cast

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator

from apps.accounts.models import EmailAddress, User, UserProfile
from apps.accounts.models.user import login_validator
from apps.accounts.services.hibp import HIBPUnavailable, password_is_pwned
from apps.accounts.services.nickname import nickname_available, normalize_nickname
from apps.accounts.services.profile import can_change_nickname
from apps.accounts.services.registration import register_user
from apps.i18n.models import Language


class RegistrationForm(forms.Form):
    language_code = "en"
    login = forms.CharField(max_length=30, label="Логин")
    nickname = forms.CharField(max_length=20, label="Никнейм")
    password1 = forms.CharField(widget=forms.PasswordInput, label="Пароль")
    password2 = forms.CharField(widget=forms.PasswordInput, label="Повторите пароль")
    email = forms.EmailField(required=False, label="Email (необязательно)")
    age_confirmed = forms.BooleanField(label="Мне 16 лет или больше")
    terms_accepted = forms.BooleanField(label="Я принимаю условия")
    privacy_accepted = forms.BooleanField(label="Я принимаю политику конфиденциальности")
    marketing_consent = forms.BooleanField(required=False, label="Хочу получать новости")

    def clean_login(self) -> str:
        value = str(self.cleaned_data["login"]).strip().lower()
        if len(value) < 3 or len(value) > 30:
            raise ValidationError("Логин: 3–30 символов.")
        login_validator(value)
        if User.objects.filter(login__iexact=value).exists():
            raise ValidationError("Этот логин уже занят.")
        return value

    def clean_nickname(self) -> str:
        value = normalize_nickname(self.cleaned_data["nickname"])
        if not nickname_available(value):
            raise ValidationError("Этот никнейм уже занят.")
        return value

    def clean_email(self) -> str:
        value = (self.cleaned_data.get("email") or "").strip().lower()
        if not value:
            return ""
        EmailValidator()(value)
        if EmailAddress.objects.filter(email__iexact=value).exists():
            raise ValidationError("Этот email уже используется.")
        return value

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        password = cleaned.get("password1")
        password2 = cleaned.get("password2")
        login = cleaned.get("login", "")
        nickname = cleaned.get("nickname", "")
        email = cleaned.get("email", "")
        if password and password2 and password != password2:
            self.add_error("password2", "Пароли не совпадают.")
        if isinstance(password, str):
            candidate = User(login=str(login))
            try:
                validate_password(password, user=candidate)
            except ValidationError as exc:
                self.add_error("password1", exc)
            if password and password.lower() in {
                str(login).lower(),
                str(nickname).lower(),
                str(email).lower(),
            }:
                self.add_error(
                    "password1",
                    "Пароль не должен совпадать с логином, никнеймом или email.",
                )
            try:
                if password_is_pwned(password):
                    self.add_error("password1", "Этот пароль найден в утечках; выберите другой.")
            except HIBPUnavailable:
                self.add_error("password1", "Проверка пароля временно недоступна.")
        return cleaned

    def save(self, *, ip: str | None = None) -> User:
        return register_user(
            login=str(self.cleaned_data["login"]),
            password=str(self.cleaned_data["password1"]),
            nickname=str(self.cleaned_data["nickname"]),
            email=str(self.cleaned_data.get("email") or ""),
            language_code=self.language_code,
            age_confirmed=bool(self.cleaned_data["age_confirmed"]),
            terms_accepted=bool(self.cleaned_data["terms_accepted"]),
            privacy_accepted=bool(self.cleaned_data["privacy_accepted"]),
            marketing_consent=bool(self.cleaned_data.get("marketing_consent")),
            ip=ip,
        )


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Логин")
    password = forms.CharField(widget=forms.PasswordInput, label="Пароль")

    error_messages = {
        "invalid_login": "Неверный логин или пароль.",
        "inactive": "Аккаунт заблокирован.",
    }


class ProfileForm(forms.Form):
    nickname = forms.CharField(max_length=20, required=False, label="Никнейм")
    email = forms.EmailField(required=False, label="Email")
    current_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput,
        label="Текущий пароль (для смены email)",
    )
    language_code = forms.ChoiceField(required=False, label="Язык")
    theme = forms.ChoiceField(choices=[("dark", "Dark"), ("light", "Light")], required=False)
    marketing_consent = forms.BooleanField(required=False, label="Получать новости")

    def __init__(self, *args: Any, user: User, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.user = user
        self.current_email = ""
        language_field = cast(forms.ChoiceField, self.fields["language_code"])
        language_field.choices = [("", "—")] + [
            (code, code)
            for code in Language.objects.filter(is_active=True).values_list("code", flat=True)
        ]
        profile = UserProfile.objects.filter(user=user).first()
        if profile is not None:
            self.fields["nickname"].initial = profile.nickname
            self.fields["language_code"].initial = profile.language.code if profile.language else ""
            self.fields["theme"].initial = profile.theme
            self.fields["marketing_consent"].initial = profile.marketing_consent_at is not None
        email = EmailAddress.objects.filter(user=user).first()
        self.current_email = email.email if email else ""
        self.fields["email"].initial = self.current_email

    def clean_nickname(self) -> str:
        value = (self.cleaned_data.get("nickname") or "").strip()
        if not value:
            return ""
        normalized = normalize_nickname(value)
        if not nickname_available(normalized, exclude_user_id=self.user.pk):
            raise ValidationError("Этот никнейм уже занят.")
        return normalized

    def clean_email(self) -> str:
        value = (self.cleaned_data.get("email") or "").strip().lower()
        if not value:
            return ""
        EmailValidator()(value)
        if EmailAddress.objects.filter(email__iexact=value).exclude(user=self.user).exists():
            raise ValidationError("Этот email уже используется.")
        return value

    def clean_nickname_change_allowed(self) -> None:
        profile = UserProfile.objects.get(user=self.user)
        nickname = self.cleaned_data.get("nickname") or ""
        if (
            nickname
            and nickname.casefold() != profile.nickname.casefold()
            and not can_change_nickname(profile)
        ):
            raise ValidationError("Никнейм можно менять не чаще одного раза в 30 дней.")

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        self.clean_nickname_change_allowed()
        new_email = str(cleaned.get("email") or "")
        password = str(cleaned.get("current_password") or "")
        if new_email.casefold() != self.current_email.casefold() and (
            not password or not self.user.check_password(password)
        ):
            self.add_error("current_password", "Для смены email требуется текущий пароль.")
        return cleaned


class SetPasswordForm(forms.Form):
    password1 = forms.CharField(widget=forms.PasswordInput, label="Новый пароль")
    password2 = forms.CharField(widget=forms.PasswordInput, label="Повторите пароль")

    def __init__(self, *args: Any, user: User, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.user = user

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        password = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password and password2 and password != password2:
            self.add_error("password2", "Пароли не совпадают.")
        if isinstance(password, str):
            try:
                validate_password(password, user=self.user)
            except ValidationError as exc:
                self.add_error("password1", exc)
            try:
                if password_is_pwned(password):
                    self.add_error("password1", "Этот пароль найден в утечках.")
            except HIBPUnavailable:
                self.add_error("password1", "Проверка пароля временно недоступна.")
        return cleaned


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(label="Email")


class DeleteAccountForm(forms.Form):
    password = forms.CharField(widget=forms.PasswordInput, label="Пароль")
    confirmation = forms.CharField(label="Введите DELETE")


class TwoFactorCodeForm(forms.Form):
    code = forms.CharField(
        max_length=6,
        min_length=6,
        label="Код из приложения",
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code"}),
    )

    def clean_code(self) -> str:
        value = str(self.cleaned_data["code"]).strip().replace(" ", "")
        if not value.isdigit():
            raise ValidationError("Код должен состоять из шести цифр.")
        return value


class RecoveryCodeForm(forms.Form):
    code = forms.CharField(max_length=32, label="Резервный код")


class DisableTwoFactorForm(forms.Form):
    password = forms.CharField(widget=forms.PasswordInput, label="Текущий пароль")
    code = forms.CharField(
        max_length=6,
        min_length=6,
        label="Код из приложения",
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code"}),
    )
