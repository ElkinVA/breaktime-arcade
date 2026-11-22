"""CRM forms: ZIP upload and step-up confirmation (§2.14.5, §2.16.1)."""

from __future__ import annotations

from typing import Any, cast

from django import forms
from django.core.files.uploadedfile import UploadedFile


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
