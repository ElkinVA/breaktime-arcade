"""CRM administration of game genres and tags (§2.16.2, §2.22).

Genres and tags are language-neutral records with one translation per active
language. Every mutation is audited with :func:`apps.crm.services.audit.record_audit`
inside the same transaction. Deletion is refused while any game still points at
the record, both through ``GameGenre``/``GameTag`` and through the game's
primary genre foreign key.

The translation queue for tags is a read-only concern of the CRM list view:
``needs_translation`` is cleared as soon as the tag has at least one saved
translation (the public catalog falls back to the neutral code for missing
languages).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.accounts.models import User
from apps.catalog.models import (
    Genre,
    GenreTranslation,
    Tag,
    TagTranslation,
)
from apps.crm.models import AdminAuditLog
from apps.crm.services.audit import record_audit
from apps.i18n.models import Language

GENRE_IN_USE = "Жанр используется играми и не может быть удалён."
TAG_IN_USE = "Тег используется играми и не может быть удалён."
DUPLICATE_CODE = "Запись с таким кодом уже существует."
DUPLICATE_SLUG = "Такой slug уже используется для этого языка."
EMPTY_CODE = "Укажите код."


def _delete_image_after_commit(name: str) -> None:
    """Remove a replaced genre image only after the DB transaction commits."""
    if not name:
        return
    transaction.on_commit(lambda: default_storage.delete(name))


INVALID_TRANSLATION = "Укажите название и slug перевода."


@dataclass(frozen=True, slots=True)
class TranslationPayload:
    """Validated translation values for one language."""

    language: Language
    name: str
    slug: str
    description: str = ""
    seo_title: str = ""
    seo_description: str = ""


@dataclass(frozen=True, slots=True)
class TaxonomyResult:
    """Outcome of a genre/tag mutation."""

    ok: bool
    message: str = ""
    instance: Genre | Tag | None = None


def _normalize_translation(payload: TranslationPayload | None) -> TranslationPayload | None:
    if payload is None:
        return None
    name = payload.name.strip()
    slug = payload.slug.strip().lower()
    if not name or not slug:
        return None
    return replace(
        payload,
        name=name,
        slug=slug,
        description=payload.description.strip(),
        seo_title=payload.seo_title.strip(),
        seo_description=payload.seo_description.strip(),
    )


def _genre_snapshot(genre: Genre) -> dict[str, Any]:
    return {
        "code": str(genre.code),
        "sort_order": genre.sort_order,
        "image": genre.image.name if genre.image else "",
        "translations": [
            {
                "language": str(translation.language.code),
                "name": translation.name,
                "slug": str(translation.slug),
                "description": translation.description,
                "seo_title": translation.seo_title,
                "seo_description": translation.seo_description,
            }
            for translation in genre.translations.select_related("language").order_by(
                "language__sort_order", "language__code"
            )
        ],
    }


def _tag_snapshot(tag: Tag) -> dict[str, Any]:
    return {
        "code": str(tag.code),
        "needs_translation": tag.needs_translation,
        "translations": [
            {
                "language": str(translation.language.code),
                "name": translation.name,
                "slug": str(translation.slug),
            }
            for translation in tag.translations.select_related("language").order_by(
                "language__sort_order", "language__code"
            )
        ],
    }


def _code_taken(model: type[Genre] | type[Tag], code: str, exclude_id: UUID | None) -> bool:
    queryset = model.objects.filter(code=code)
    if exclude_id is not None:
        queryset = queryset.exclude(pk=exclude_id)
    return queryset.exists()


def _slug_taken(
    model: type[GenreTranslation] | type[TagTranslation],
    language: Language,
    slug: str,
    exclude_id: UUID | None,
) -> bool:
    queryset = model.objects.filter(language=language, slug=slug)
    if exclude_id is not None:
        queryset = queryset.exclude(pk=exclude_id)
    return queryset.exists()


def _upsert_genre_translation(genre: Genre, payload: TranslationPayload) -> GenreTranslation:
    translation, _created = GenreTranslation.objects.update_or_create(
        genre=genre,
        language=payload.language,
        defaults={
            "name": payload.name,
            "slug": payload.slug,
            "description": payload.description,
            "seo_title": payload.seo_title,
            "seo_description": payload.seo_description,
        },
    )
    return translation


def _upsert_tag_translation(tag: Tag, payload: TranslationPayload) -> TagTranslation:
    translation, _created = TagTranslation.objects.update_or_create(
        tag=tag,
        language=payload.language,
        defaults={"name": payload.name, "slug": payload.slug},
    )
    return translation


def _clear_tag_translation_flag(tag: Tag) -> None:
    """A tag is no longer in the translation queue once a translation exists."""
    if tag.needs_translation and tag.translations.exists():
        tag.needs_translation = False
        tag.save(update_fields=["needs_translation", "updated_at"])


def create_genre(
    *,
    code: str,
    sort_order: int,
    image: UploadedFile[Any] | None = None,
    translation: TranslationPayload | None = None,
    actor: User | None,
    ip: str | None = None,
) -> TaxonomyResult:
    """Create a genre and, optionally, one translation."""
    clean_code = code.strip()
    if not clean_code:
        return TaxonomyResult(False, EMPTY_CODE)
    payload = _normalize_translation(translation)
    if translation is not None and payload is None:
        return TaxonomyResult(False, INVALID_TRANSLATION)
    if _code_taken(Genre, clean_code, None):
        return TaxonomyResult(False, DUPLICATE_CODE)
    if payload is not None and _slug_taken(GenreTranslation, payload.language, payload.slug, None):
        return TaxonomyResult(False, DUPLICATE_SLUG)

    try:
        with transaction.atomic():
            genre = Genre(code=clean_code, sort_order=sort_order)
            if image is not None:
                genre.image = image
            genre.save()
            if payload is not None:
                _upsert_genre_translation(genre, payload)
            record_audit(
                actor=actor,
                action=AdminAuditLog.ACTION_GENRE_CREATED,
                object_type="genre",
                object_id=genre.id,
                before=None,
                after=_genre_snapshot(genre),
                ip=ip,
            )
    except IntegrityError:
        return TaxonomyResult(False, DUPLICATE_CODE)
    return TaxonomyResult(True, instance=genre)


def update_genre(
    genre: Genre,
    *,
    code: str,
    sort_order: int,
    image: UploadedFile[Any] | None = None,
    clear_image: bool = False,
    translation: TranslationPayload | None = None,
    actor: User | None,
    ip: str | None = None,
) -> TaxonomyResult:
    """Update genre fields and, optionally, one translation."""
    clean_code = code.strip()
    if not clean_code:
        return TaxonomyResult(False, EMPTY_CODE)
    payload = _normalize_translation(translation)
    if translation is not None and payload is None:
        return TaxonomyResult(False, INVALID_TRANSLATION)
    if _code_taken(Genre, clean_code, genre.id):
        return TaxonomyResult(False, DUPLICATE_CODE)

    existing: GenreTranslation | None = None
    if payload is not None:
        existing = genre.translations.filter(language=payload.language).first()
        exclude_id = existing.id if existing is not None else None
        if _slug_taken(GenreTranslation, payload.language, payload.slug, exclude_id):
            return TaxonomyResult(False, DUPLICATE_SLUG)

    before = _genre_snapshot(genre)
    previous_image = genre.image.name if genre.image else ""
    try:
        with transaction.atomic():
            genre.code = clean_code
            genre.sort_order = sort_order
            if image is not None:
                genre.image = image
            elif clear_image:
                genre.image = ""
            genre.save()
            if previous_image and (image is not None or clear_image):
                _delete_image_after_commit(previous_image)
            if payload is not None:
                _upsert_genre_translation(genre, payload)
            record_audit(
                actor=actor,
                action=AdminAuditLog.ACTION_GENRE_UPDATED,
                object_type="genre",
                object_id=genre.id,
                before=before,
                after=_genre_snapshot(genre),
                ip=ip,
            )
    except IntegrityError:
        return TaxonomyResult(False, DUPLICATE_CODE)
    return TaxonomyResult(True, instance=genre)


def delete_genre(
    genre: Genre,
    *,
    actor: User | None,
    ip: str | None = None,
) -> TaxonomyResult:
    """Delete an unreferenced genre; refuse while games still use it."""
    try:
        with transaction.atomic():
            locked = Genre.objects.select_for_update().get(pk=genre.pk)
            if locked.game_links.exists() or locked.primary_games.exists():
                return TaxonomyResult(False, GENRE_IN_USE, instance=genre)
            snapshot = _genre_snapshot(locked)
            image_name = (locked.image.name or "") if locked.image else ""
            record_audit(
                actor=actor,
                action=AdminAuditLog.ACTION_GENRE_DELETED,
                object_type="genre",
                object_id=locked.id,
                before=snapshot,
                after=None,
                ip=ip,
            )
            locked.delete()
            _delete_image_after_commit(image_name)
    except Genre.DoesNotExist:
        return TaxonomyResult(False, GENRE_IN_USE)
    except ProtectedError:
        return TaxonomyResult(False, GENRE_IN_USE, instance=genre)
    return TaxonomyResult(True)


def create_tag(
    *,
    code: str,
    needs_translation: bool,
    translation: TranslationPayload | None = None,
    actor: User | None,
    ip: str | None = None,
) -> TaxonomyResult:
    """Create a tag and, optionally, one translation."""
    clean_code = code.strip()
    if not clean_code:
        return TaxonomyResult(False, EMPTY_CODE)
    payload = _normalize_translation(translation)
    if translation is not None and payload is None:
        return TaxonomyResult(False, INVALID_TRANSLATION)
    if _code_taken(Tag, clean_code, None):
        return TaxonomyResult(False, DUPLICATE_CODE)
    if payload is not None and _slug_taken(TagTranslation, payload.language, payload.slug, None):
        return TaxonomyResult(False, DUPLICATE_SLUG)

    try:
        with transaction.atomic():
            tag = Tag(code=clean_code, needs_translation=needs_translation)
            tag.save()
            if payload is not None:
                _upsert_tag_translation(tag, payload)
                _clear_tag_translation_flag(tag)
            record_audit(
                actor=actor,
                action=AdminAuditLog.ACTION_TAG_CREATED,
                object_type="tag",
                object_id=tag.id,
                before=None,
                after=_tag_snapshot(tag),
                ip=ip,
            )
    except IntegrityError:
        return TaxonomyResult(False, DUPLICATE_CODE)
    return TaxonomyResult(True, instance=tag)


def update_tag(
    tag: Tag,
    *,
    code: str,
    needs_translation: bool,
    translation: TranslationPayload | None = None,
    actor: User | None,
    ip: str | None = None,
) -> TaxonomyResult:
    """Update tag fields and, optionally, one translation."""
    clean_code = code.strip()
    if not clean_code:
        return TaxonomyResult(False, EMPTY_CODE)
    payload = _normalize_translation(translation)
    if translation is not None and payload is None:
        return TaxonomyResult(False, INVALID_TRANSLATION)
    if _code_taken(Tag, clean_code, tag.id):
        return TaxonomyResult(False, DUPLICATE_CODE)

    existing: TagTranslation | None = None
    if payload is not None:
        existing = tag.translations.filter(language=payload.language).first()
        exclude_id = existing.id if existing is not None else None
        if _slug_taken(TagTranslation, payload.language, payload.slug, exclude_id):
            return TaxonomyResult(False, DUPLICATE_SLUG)

    before = _tag_snapshot(tag)
    try:
        with transaction.atomic():
            tag.code = clean_code
            tag.needs_translation = needs_translation
            tag.save()
            if payload is not None:
                _upsert_tag_translation(tag, payload)
                _clear_tag_translation_flag(tag)
            record_audit(
                actor=actor,
                action=AdminAuditLog.ACTION_TAG_UPDATED,
                object_type="tag",
                object_id=tag.id,
                before=before,
                after=_tag_snapshot(tag),
                ip=ip,
            )
    except IntegrityError:
        return TaxonomyResult(False, DUPLICATE_CODE)
    return TaxonomyResult(True, instance=tag)


def delete_tag(
    tag: Tag,
    *,
    actor: User | None,
    ip: str | None = None,
) -> TaxonomyResult:
    """Delete an unreferenced tag; refuse while games still use it."""
    try:
        with transaction.atomic():
            locked = Tag.objects.select_for_update().get(pk=tag.pk)
            if locked.game_links.exists():
                return TaxonomyResult(False, TAG_IN_USE, instance=tag)
            snapshot = _tag_snapshot(locked)
            record_audit(
                actor=actor,
                action=AdminAuditLog.ACTION_TAG_DELETED,
                object_type="tag",
                object_id=locked.id,
                before=snapshot,
                after=None,
                ip=ip,
            )
            locked.delete()
    except Tag.DoesNotExist:
        return TaxonomyResult(False, TAG_IN_USE)
    return TaxonomyResult(True)


__all__ = [
    "DUPLICATE_CODE",
    "DUPLICATE_SLUG",
    "EMPTY_CODE",
    "GENRE_IN_USE",
    "INVALID_TRANSLATION",
    "TAG_IN_USE",
    "TaxonomyResult",
    "TranslationPayload",
    "create_genre",
    "create_tag",
    "delete_genre",
    "delete_tag",
    "update_genre",
    "update_tag",
]
