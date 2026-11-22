"""CRM editing, publishing and caching for basic content pages (§2.16.2).

A page is language-neutral (stable slug, single publish flag) with one
translation per language. Bodies are sanitised before storage; a rejected
update never touches the published copy. Every successful write explicitly
invalidates the page cache on commit so the next read rebuilds it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, cast

from django.core.cache import cache
from django.db import transaction

from apps.content.models import ContentPage, ContentPageTranslation
from apps.content.services.sanitize import sanitize_html
from apps.i18n.models import Language

PAGE_CACHE_KEY = "content:page:{slug}"
PAGE_CACHE_TTL = 3600
MAX_BODY_LENGTH = 100_000
_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,126}[a-z0-9])?$")


class PageValidationError(ValueError):
    """A safe validation failure for the CRM content page form."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class PageSaveResult:
    ok: bool
    translation: ContentPageTranslation | None = None
    code: str = ""
    message: str = ""


def page_cache_key(slug: str) -> str:
    return PAGE_CACHE_KEY.format(slug=str(slug).lower())


def validate_slug(raw: str) -> str:
    slug = raw.strip().lower()
    if not _SLUG_RE.fullmatch(slug):
        raise PageValidationError(
            "invalid_slug",
            "Адрес страницы: строчные латинские буквы, цифры и дефис.",
        )
    return slug


def create_page(*, slug: str) -> ContentPage:
    clean = validate_slug(slug)
    if ContentPage.objects.filter(slug=clean).exists():
        raise PageValidationError("duplicate_slug", "Страница с таким адресом уже существует.")
    return ContentPage.objects.create(slug=clean)


def _validate_plain(value: str, *, field: str, max_length: int, required: bool) -> str:
    clean = value.strip()
    if required and not clean:
        raise PageValidationError(f"{field}_required", "Заполните обязательное поле.")
    if len(clean) > max_length:
        raise PageValidationError(f"{field}_too_long", f"Поле длиннее {max_length} символов.")
    if "\x00" in clean:
        raise PageValidationError(f"{field}_control", "Недопустимые управляющие символы.")
    return clean


def save_page_translation(
    page: ContentPage,
    *,
    language: Language,
    title: str,
    body: str,
    seo_title: str = "",
    seo_description: str = "",
) -> PageSaveResult:
    """Sanitise and validate a translation; no write happens on failure."""
    try:
        clean_title = _validate_plain(title, field="title", max_length=200, required=True)
        clean_seo_title = _validate_plain(
            seo_title, field="seo_title", max_length=60, required=False
        )
        clean_seo_description = _validate_plain(
            seo_description,
            field="seo_description",
            max_length=160,
            required=False,
        )
        clean_body = sanitize_html(body)
        if len(clean_body) > MAX_BODY_LENGTH:
            raise PageValidationError("body_too_long", "Тело страницы слишком длинное.")
        if page.is_published and not clean_body.strip():
            raise PageValidationError(
                "body_required",
                "Опубликованная страница не может иметь пустое тело.",
            )
    except PageValidationError as exc:
        return PageSaveResult(ok=False, code=exc.code, message=exc.message)

    with transaction.atomic():
        translation, _ = ContentPageTranslation.objects.update_or_create(
            page=page,
            language=language,
            defaults={
                "title": clean_title,
                "body": clean_body,
                "seo_title": clean_seo_title,
                "seo_description": clean_seo_description,
            },
        )
    transaction.on_commit(lambda: invalidate_page(page))
    return PageSaveResult(ok=True, translation=translation)


def publish_page(page: ContentPage) -> None:
    """Publish a page that has at least one non-empty translation."""
    translations = list(page.translations.all())
    if not translations or not any(tr.title.strip() and tr.body.strip() for tr in translations):
        raise PageValidationError(
            "translation_required",
            "Добавьте хотя бы один заполненный перевод перед публикацией.",
        )
    page.is_published = True
    page.save(update_fields=["is_published", "updated_at"])
    transaction.on_commit(lambda: invalidate_page(page))


def unpublish_page(page: ContentPage) -> None:
    if page.is_published:
        page.is_published = False
        page.save(update_fields=["is_published", "updated_at"])
    transaction.on_commit(lambda: invalidate_page(page))


def invalidate_page(page: ContentPage) -> None:
    """Explicitly drop the cached public representation of ``page``."""
    cache.delete(page_cache_key(str(page.slug)))


def get_cached_page(slug: str) -> dict[str, Any] | None:
    """Return a cached published-page payload (``None`` when not published)."""
    key = page_cache_key(slug)
    cached = cache.get(key)
    if cached is not None:
        return cast("dict[str, Any]", cached)

    page = (
        ContentPage.objects.filter(slug=slug, is_published=True)
        .prefetch_related("translations__language")
        .first()
    )
    if page is None:
        return None
    payload: dict[str, Any] = {
        "id": str(page.id),
        "slug": str(page.slug),
        "translations": {
            str(tr.language.code): {
                "title": tr.title,
                "body": tr.body,
                "seo_title": tr.seo_title,
                "seo_description": tr.seo_description,
            }
            for tr in page.translations.all()
        },
    }
    cache.set(key, payload, PAGE_CACHE_TTL)
    return payload


__all__ = [
    "MAX_BODY_LENGTH",
    "PAGE_CACHE_KEY",
    "PageSaveResult",
    "PageValidationError",
    "create_page",
    "get_cached_page",
    "invalidate_page",
    "page_cache_key",
    "publish_page",
    "save_page_translation",
    "unpublish_page",
    "validate_slug",
]
