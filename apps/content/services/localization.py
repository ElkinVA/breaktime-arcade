"""Validation and publishing rules for CRM localization entries (§2.15).

Interface strings are always rendered as text. A value is accepted only when
it is non-empty, free of HTML markup, well-formed with respect to ``{name}``
placeholders and (for non-English languages) uses exactly the placeholders of
the published English source. Validation happens before any write, therefore
an invalid update can never silently replace the currently published copy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from django.db import transaction

from apps.accounts.models import User
from apps.i18n.models import Language, TranslationEntry
from apps.i18n.services.dictionary import invalidate_language

MAX_VALUE_LENGTH = 8000
_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_ANY_BRACED = re.compile(r"\{[^{}]*\}")

STATUSES = frozenset(
    {
        TranslationEntry.STATUS_DRAFT,
        TranslationEntry.STATUS_REVIEW,
        TranslationEntry.STATUS_APPROVED,
        TranslationEntry.STATUS_PUBLISHED,
    }
)


class TranslationValidationError(ValueError):
    """A safe, localisable validation failure for the CRM form."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class TranslationSaveResult:
    ok: bool
    entry: TranslationEntry | None = None
    code: str = ""
    message: str = ""


def placeholders(value: str) -> set[str]:
    """Return the set of ``{parameter}`` names used by ``value``."""
    return set(_PLACEHOLDER.findall(value))


def _validate_braces(value: str) -> None:
    for match in _ANY_BRACED.finditer(value):
        if _PLACEHOLDER.fullmatch(match.group(0)) is None:
            raise TranslationValidationError(
                "placeholder_invalid",
                "Некорректный плейсхолдер: используйте формат {name}.",
            )
    remainder = _ANY_BRACED.sub("", value)
    if "{" in remainder or "}" in remainder:
        raise TranslationValidationError(
            "placeholder_invalid",
            "Некорректный плейсхолдер: используйте формат {name}.",
        )


def validate_value(value: str, *, source_value: str | None = None) -> None:
    """Raise :class:`TranslationValidationError` when a value is unsafe."""
    if not value or not value.strip():
        raise TranslationValidationError("empty", "Перевод не может быть пустым.")
    if len(value) > MAX_VALUE_LENGTH:
        raise TranslationValidationError(
            "too_long",
            f"Перевод длиннее {MAX_VALUE_LENGTH} символов.",
        )
    if "\x00" in value:
        raise TranslationValidationError("control_chars", "Недопустимые управляющие символы.")
    if "<" in value:
        raise TranslationValidationError("html_forbidden", "HTML в строках интерфейса запрещён.")
    _validate_braces(value)
    if source_value is not None and placeholders(value) != placeholders(source_value):
        raise TranslationValidationError(
            "placeholder_mismatch",
            "Набор плейсхолдеров не совпадает с исходной строкой.",
        )


def _source_value(namespace: str, key: str, *, exclude_id: UUID | None = None) -> str | None:
    query = TranslationEntry.objects.filter(
        namespace=namespace,
        key=key,
        language__code="en",
        status=TranslationEntry.STATUS_PUBLISHED,
    )
    if exclude_id is not None:
        query = query.exclude(pk=exclude_id)
    return query.values_list("value", flat=True).first()


def _schedule_invalidation(language: Language) -> None:
    transaction.on_commit(lambda: invalidate_language(language))


def _check_status(status: str) -> None:
    if status not in STATUSES:
        raise TranslationValidationError("invalid_status", "Неизвестный статус перевода.")


def create_translation(
    *,
    namespace: str,
    key: str,
    language: Language,
    value: str,
    status: str,
    is_machine_translated: bool = False,
    actor: User | None = None,
) -> TranslationSaveResult:
    """Create one localization entry after running all safety checks."""
    namespace = namespace.strip()
    key = key.strip()
    if not namespace or not key:
        return TranslationSaveResult(
            ok=False,
            code="identity_required",
            message="Укажите namespace и ключ.",
        )
    _check_status(status)
    try:
        source = None if language.code == "en" else _source_value(namespace, key)
        validate_value(value, source_value=source)
    except TranslationValidationError as exc:
        return TranslationSaveResult(ok=False, code=exc.code, message=exc.message)

    if TranslationEntry.objects.filter(
        namespace=namespace,
        key=key,
        language=language,
    ).exists():
        return TranslationSaveResult(
            ok=False,
            code="duplicate",
            message="Такая строка для этого языка уже существует.",
        )

    with transaction.atomic():
        entry = TranslationEntry.objects.create(
            namespace=namespace,
            key=key,
            language=language,
            value=value,
            status=status,
            is_machine_translated=is_machine_translated,
            updated_by=actor,
        )
    _schedule_invalidation(language)
    return TranslationSaveResult(ok=True, entry=entry)


def update_translation(
    entry: TranslationEntry,
    *,
    value: str,
    status: str,
    is_machine_translated: bool,
    actor: User | None = None,
) -> TranslationSaveResult:
    """Validate first, then update; a rejected value leaves the row untouched."""
    _check_status(status)
    try:
        source = (
            None
            if entry.language.code == "en"
            else _source_value(entry.namespace, entry.key, exclude_id=entry.pk)
        )
        validate_value(value, source_value=source)
    except TranslationValidationError as exc:
        return TranslationSaveResult(ok=False, code=exc.code, message=exc.message)

    with transaction.atomic():
        entry.value = value
        entry.status = status
        entry.is_machine_translated = is_machine_translated
        entry.updated_by = actor
        entry.save(
            update_fields=[
                "value",
                "status",
                "is_machine_translated",
                "updated_by",
                "updated_at",
            ]
        )
    _schedule_invalidation(entry.language)
    return TranslationSaveResult(ok=True, entry=entry)


__all__ = [
    "MAX_VALUE_LENGTH",
    "STATUSES",
    "TranslationSaveResult",
    "TranslationValidationError",
    "create_translation",
    "placeholders",
    "update_translation",
    "validate_value",
]
