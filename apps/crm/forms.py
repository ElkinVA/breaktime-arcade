"""CRM forms: ZIP upload and step-up confirmation (§2.14.5, §2.16.1)."""

from __future__ import annotations

from typing import Any, cast

from django import forms
from django.core.files.uploadedfile import UploadedFile
from django.core.validators import RegexValidator
from django.db.models import QuerySet

from apps.i18n.models import Language, TranslationEntry

SLUG_VALIDATOR = RegexValidator(
    r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    "Slug: только строчные латинские буквы, цифры и дефис.",
)


class ZipUploadForm(forms.Form):
    """Accept a single ZIP; archive safety is decided by the pipeline."""

    package = forms.FileField(
        label="ZIP-пакет",
        widget=forms.ClearableFileInput(
            attrs={
                "accept": ".zip,application/zip",
                "class": "block w-full text-sm",
                "data-testid": "crm-wizard-upload-input",
            }
        ),
    )

    def clean_package(self) -> UploadedFile[Any]:
        upload = cast("UploadedFile[Any]", self.cleaned_data["package"])
        name = str(upload.name or "")
        if not name.lower().endswith(".zip"):
            raise forms.ValidationError("Требуется файл в формате ZIP.")
        if not upload.size:
            raise forms.ValidationError("Файл пуст.")
        return upload


class StepUpForm(forms.Form):
    """Password + TOTP confirmation for a sensitive CRM operation."""

    password = forms.CharField(
        label="Пароль",
        strip=False,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={
                "autocomplete": "current-password",
                "class": "w-full bg-bg border border-text/20 rounded px-3 py-2",
                "data-testid": "crm-step-up-password",
            },
        ),
    )
    totp_code = forms.CharField(
        label="Код TOTP",
        max_length=12,
        widget=forms.TextInput(
            attrs={
                "inputmode": "numeric",
                "autocomplete": "one-time-code",
                "class": "w-full bg-bg border border-text/20 rounded px-3 py-2",
                "data-testid": "crm-step-up-totp",
            }
        ),
    )
    next = forms.CharField(required=False, widget=forms.HiddenInput())

    def clean_totp_code(self) -> str:
        value = str(self.cleaned_data["totp_code"]).strip().replace(" ", "")
        if not value.isdigit() or len(value) != 6:
            raise forms.ValidationError("Введите шестизначный код TOTP.")
        return value


class _ActiveLanguageField(forms.ModelChoiceField):  # type: ignore[type-arg]
    def __init__(self) -> None:
        super().__init__(queryset=Language.objects.none(), label="Язык")

    def clean(self, value: Any) -> Language:
        language = cast("Language", super().clean(value))
        if not language.is_active:
            raise forms.ValidationError("Язык отключён.")
        return language


_INPUT_CLASS = "w-full bg-bg border border-text/20 rounded px-3 py-2"


class TranslationEntryCreateForm(forms.Form):
    """Create a localization entry; value safety is checked by the service."""

    namespace = forms.CharField(
        max_length=64,
        label="Namespace",
        widget=forms.TextInput(attrs={"class": _INPUT_CLASS}),
    )
    key = forms.CharField(
        max_length=128,
        label="Ключ",
        widget=forms.TextInput(attrs={"class": _INPUT_CLASS}),
    )
    language = _ActiveLanguageField()
    value = forms.CharField(
        label="Значение",
        strip=False,
        widget=forms.Textarea(attrs={"rows": 4, "class": _INPUT_CLASS}),
    )
    status = forms.ChoiceField(choices=TranslationEntry.STATUS_CHOICES, label="Статус")
    is_machine_translated = forms.BooleanField(
        required=False,
        label="Машинный черновой перевод",
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        language = self.fields["language"]
        assert isinstance(language, _ActiveLanguageField)
        language.queryset = Language.objects.filter(is_active=True).order_by("sort_order", "code")


class TranslationEntryEditForm(forms.Form):
    """Edit value/status of an existing entry (identity is immutable here)."""

    value = forms.CharField(
        label="Значение",
        strip=False,
        widget=forms.Textarea(attrs={"rows": 6, "class": _INPUT_CLASS}),
    )
    status = forms.ChoiceField(choices=TranslationEntry.STATUS_CHOICES, label="Статус")
    is_machine_translated = forms.BooleanField(
        required=False,
        label="Машинный черновой перевод",
    )


class ContentPageForm(forms.Form):
    """Create a language-neutral content page."""

    slug = forms.CharField(
        max_length=128,
        label="Адрес",
        widget=forms.TextInput(attrs={"class": _INPUT_CLASS}),
    )


class ContentPageTranslationForm(forms.Form):
    """Edit one language version of a content page."""

    language = _ActiveLanguageField()
    title = forms.CharField(
        max_length=200,
        label="Заголовок",
        widget=forms.TextInput(attrs={"class": _INPUT_CLASS}),
    )
    body = forms.CharField(
        label="Текст (allowlist HTML)",
        required=False,
        strip=False,
        widget=forms.Textarea(attrs={"rows": 12, "class": _INPUT_CLASS}),
    )
    seo_title = forms.CharField(
        max_length=60,
        required=False,
        label="SEO Title",
        widget=forms.TextInput(attrs={"class": _INPUT_CLASS}),
    )
    seo_description = forms.CharField(
        max_length=160,
        required=False,
        label="SEO Description",
        widget=forms.Textarea(attrs={"rows": 2, "class": _INPUT_CLASS}),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        language = self.fields["language"]
        assert isinstance(language, _ActiveLanguageField)
        language.queryset = Language.objects.filter(is_active=True).order_by("sort_order", "code")


def _active_language_queryset() -> QuerySet[Language]:
    return Language.objects.filter(is_active=True).order_by("sort_order", "code")


def _language_field(*, hidden: bool) -> forms.ModelChoiceField:  # type: ignore[type-arg]
    widget = forms.HiddenInput() if hidden else forms.Select(attrs={"class": _INPUT_CLASS})
    return forms.ModelChoiceField(
        queryset=_active_language_queryset(),
        label="Язык",
        widget=widget,
    )


class GenreForm(forms.Form):
    """Language-neutral genre fields (§2.16.2, §2.22)."""

    code = forms.CharField(
        max_length=32,
        label="Код",
        widget=forms.TextInput(attrs={"class": _INPUT_CLASS, "data-testid": "crm-genre-code"}),
    )
    sort_order = forms.IntegerField(
        min_value=0,
        max_value=32767,
        required=False,
        initial=0,
        label="Порядок",
        widget=forms.NumberInput(attrs={"class": _INPUT_CLASS}),
    )
    image = forms.ImageField(
        required=False,
        label="Изображение",
        widget=forms.ClearableFileInput(attrs={"class": "block w-full text-sm"}),
    )
    clear_image = forms.BooleanField(
        required=False,
        label="Удалить текущее изображение",
    )


class TagForm(forms.Form):
    """Language-neutral tag fields (§2.16.2, §2.22)."""

    code = forms.CharField(
        max_length=64,
        label="Код",
        widget=forms.TextInput(attrs={"class": _INPUT_CLASS, "data-testid": "crm-tag-code"}),
    )
    needs_translation = forms.BooleanField(
        required=False,
        label="Требует перевода",
        widget=forms.CheckboxInput(attrs={"data-testid": "crm-tag-needs-translation"}),
    )


def _validate_translation_pair(form: forms.Form, cleaned: dict[str, Any]) -> None:
    name = str(cleaned.get("name") or "").strip()
    slug = str(cleaned.get("slug") or "").strip()
    if not name and not slug:
        return
    if not name:
        form.add_error("name", "Укажите название перевода.")
    if not slug:
        form.add_error("slug", "Укажите slug перевода.")


class GenreTranslationForm(forms.Form):
    """One localized genre translation; all fields optional as a group."""

    language = _language_field(hidden=True)
    name = forms.CharField(
        max_length=64,
        required=False,
        label="Название",
        widget=forms.TextInput(attrs={"class": _INPUT_CLASS}),
    )
    slug = forms.CharField(
        max_length=64,
        required=False,
        label="Slug",
        validators=[SLUG_VALIDATOR],
        widget=forms.TextInput(attrs={"class": _INPUT_CLASS}),
    )
    description = forms.CharField(
        max_length=500,
        required=False,
        label="Описание",
        widget=forms.Textarea(attrs={"rows": 3, "class": _INPUT_CLASS}),
    )
    seo_title = forms.CharField(
        max_length=60,
        required=False,
        label="SEO Title",
        widget=forms.TextInput(attrs={"class": _INPUT_CLASS}),
    )
    seo_description = forms.CharField(
        max_length=160,
        required=False,
        label="SEO Description",
        widget=forms.Textarea(attrs={"rows": 2, "class": _INPUT_CLASS}),
    )

    def __init__(self, *args: Any, show_language: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if show_language:
            self.fields["language"] = _language_field(hidden=False)

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        _validate_translation_pair(self, cleaned)
        return cleaned


class TagTranslationForm(forms.Form):
    """One localized tag translation; all fields optional as a group."""

    language = _language_field(hidden=True)
    name = forms.CharField(
        max_length=64,
        required=False,
        label="Название",
        widget=forms.TextInput(attrs={"class": _INPUT_CLASS}),
    )
    slug = forms.CharField(
        max_length=64,
        required=False,
        label="Slug",
        validators=[SLUG_VALIDATOR],
        widget=forms.TextInput(attrs={"class": _INPUT_CLASS}),
    )

    def __init__(self, *args: Any, show_language: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if show_language:
            self.fields["language"] = _language_field(hidden=False)

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        _validate_translation_pair(self, cleaned)
        return cleaned


__all__ = [
    "ContentPageForm",
    "ContentPageTranslationForm",
    "GenreForm",
    "GenreTranslationForm",
    "StepUpForm",
    "TagForm",
    "TagTranslationForm",
    "TranslationEntryCreateForm",
    "TranslationEntryEditForm",
    "ZipUploadForm",
]
