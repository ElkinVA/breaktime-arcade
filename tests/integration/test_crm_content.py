"""CRM localization/content editing, sanitisation and cache invalidation."""

from __future__ import annotations

import pytest
from django.core.cache import cache, caches
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StaffRole, User
from apps.content.models import ContentPage
from apps.content.services.pages import get_cached_page, page_cache_key
from apps.i18n.models import Language, TranslationEntry
from apps.i18n.services.dictionary import CACHE_KEY as DICTIONARY_KEY
from apps.i18n.services.dictionary import get_dictionary

PASSWORD = "correct horse battery staple"
LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "throttle": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


@pytest.fixture(autouse=True)
def locmem_cache():
    with override_settings(CACHES=LOCMEM_CACHES):
        caches["default"].clear()
        caches["throttle"].clear()
        yield
        caches["default"].clear()
        caches["throttle"].clear()


def _staff(login: str, role: str) -> User:
    user = User.objects.create_user(
        login=login,
        password=PASSWORD,
        is_staff=True,
        crm_role=role,
    )
    User.objects.filter(pk=user.pk).update(totp_confirmed_at=timezone.now())
    user.refresh_from_db()
    return user


def _client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    session = client.session
    session["ba_2fa_verified"] = True
    session.save()
    return client


def _elevate(client: Client) -> None:
    session = client.session
    session["crm_step_up_at"] = timezone.now().isoformat()
    session.save()


def _source(namespace: str, key: str, value: str) -> TranslationEntry:
    return TranslationEntry.objects.create(
        namespace=namespace,
        key=key,
        language=Language.objects.get(code="en"),
        value=value,
        status=TranslationEntry.STATUS_PUBLISHED,
    )


@pytest.mark.django_db
def test_translation_publish_requires_step_up_and_invalidates_cache(
    django_capture_on_commit_callbacks,
) -> None:
    ru = Language.objects.get(code="ru")
    _source("catalog", "greeting", "Hello {name}")
    # Warm the published dictionary cache before the edit.
    assert "greeting" not in get_dictionary(ru).get("catalog", {})
    assert cache.get(DICTIONARY_KEY.format(code="ru")) is not None

    editor = _staff("content_editor", StaffRole.EDITOR)
    client = _client(editor)

    blocked = client.post(
        reverse("crm:content_translation_new"),
        {
            "namespace": "catalog",
            "key": "greeting",
            "language": str(ru.id),
            "value": "Привет {name}",
            "status": TranslationEntry.STATUS_PUBLISHED,
        },
    )
    assert blocked.status_code == 302
    assert blocked.url.startswith(reverse("crm:step_up"))
    assert not TranslationEntry.objects.filter(
        language=ru, namespace="catalog", key="greeting"
    ).exists()

    _elevate(client)
    with django_capture_on_commit_callbacks(execute=True):
        created = client.post(
            reverse("crm:content_translation_new"),
            {
                "namespace": "catalog",
                "key": "greeting",
                "language": str(ru.id),
                "value": "Привет {name}",
                "status": TranslationEntry.STATUS_PUBLISHED,
            },
        )
    assert created.status_code == 302
    entry = TranslationEntry.objects.get(language=ru, namespace="catalog", key="greeting")
    assert entry.status == TranslationEntry.STATUS_PUBLISHED
    assert entry.updated_by_id == editor.id
    assert cache.get(DICTIONARY_KEY.format(code="ru")) is None
    assert get_dictionary(ru)["catalog"]["greeting"] == "Привет {name}"

    # A placeholder mismatch must never replace the published copy.
    invalid = client.post(
        reverse("crm:content_translation", args=[entry.id]),
        {
            "value": "Привет {other}",
            "status": TranslationEntry.STATUS_PUBLISHED,
        },
    )
    assert invalid.status_code == 200
    entry.refresh_from_db()
    assert entry.value == "Привет {name}"
    assert entry.status == TranslationEntry.STATUS_PUBLISHED

    # HTML in interface strings is rejected for the same reason.
    html_attempt = client.post(
        reverse("crm:content_translation", args=[entry.id]),
        {
            "value": "<script>alert(1)</script>",
            "status": TranslationEntry.STATUS_PUBLISHED,
        },
    )
    assert html_attempt.status_code == 200
    entry.refresh_from_db()
    assert entry.value == "Привет {name}"

    with django_capture_on_commit_callbacks(execute=True):
        updated = client.post(
            reverse("crm:content_translation", args=[entry.id]),
            {
                "value": "Здравствуй {name}",
                "status": TranslationEntry.STATUS_PUBLISHED,
            },
        )
    assert updated.status_code == 302
    assert cache.get(DICTIONARY_KEY.format(code="ru")) is None
    assert get_dictionary(ru)["catalog"]["greeting"] == "Здравствуй {name}"


@pytest.mark.django_db
def test_translation_values_are_escaped_in_the_crm() -> None:
    ru = Language.objects.get(code="ru")
    TranslationEntry.objects.create(
        namespace="catalog",
        key="unsafe_value",
        language=ru,
        value="<b>bold</b>",
        status=TranslationEntry.STATUS_PUBLISHED,
    )
    editor = _staff("escaping_editor", StaffRole.EDITOR)
    client = _client(editor)

    response = client.get(reverse("crm:content_translations"))

    assert response.status_code == 200
    body = response.content.decode()
    assert "&lt;b&gt;bold&lt;/b&gt;" in body
    assert "<b>bold</b>" not in body


@pytest.mark.django_db
def test_content_page_sanitises_publishes_and_invalidates_cache(
    django_capture_on_commit_callbacks,
) -> None:
    en = Language.objects.get(code="en")
    editor = _staff("page_editor", StaffRole.EDITOR)
    client = _client(editor)

    blocked = client.post(reverse("crm:content_page_new"), {"slug": "about"})
    assert blocked.status_code == 302
    assert blocked.url.startswith(reverse("crm:step_up"))
    assert ContentPage.objects.count() == 0

    _elevate(client)
    with django_capture_on_commit_callbacks(execute=True):
        created = client.post(reverse("crm:content_page_new"), {"slug": "about"})
    assert created.status_code == 302
    page = ContentPage.objects.get(slug="about")

    unsafe_body = (
        '<p onclick="evil()">Hello</p>'
        "<script>alert(1)</script>"
        '<a href="javascript:alert(1)">link</a>'
        "<strong>ok</strong>"
    )
    with django_capture_on_commit_callbacks(execute=True):
        saved = client.post(
            reverse("crm:content_page", args=[page.id]),
            {
                "action": "save_translation",
                "language": str(en.id),
                "title": "About",
                "body": unsafe_body,
                "seo_title": "About",
                "seo_description": "About page",
            },
        )
    assert saved.status_code == 302
    translation = page.translations.get(language=en)
    assert translation.body == '<p>Hello</p><a rel="nofollow noopener">link</a><strong>ok</strong>'
    assert "<script" not in translation.body
    assert "onclick" not in translation.body
    assert "javascript:" not in translation.body

    with django_capture_on_commit_callbacks(execute=True):
        published = client.post(
            reverse("crm:content_page", args=[page.id]),
            {"action": "publish"},
        )
    assert published.status_code == 302
    page.refresh_from_db()
    assert page.is_published is True
    cached = get_cached_page("about")
    assert cached is not None
    assert cached["translations"]["en"]["title"] == "About"

    # Published copy survives an invalid (empty body) update.
    invalid = client.post(
        reverse("crm:content_page", args=[page.id]),
        {
            "action": "save_translation",
            "language": str(en.id),
            "title": "About",
            "body": "",
        },
    )
    assert invalid.status_code == 200
    translation.refresh_from_db()
    assert translation.body == '<p>Hello</p><a rel="nofollow noopener">link</a><strong>ok</strong>'

    # Explicit invalidation happens for any accepted translation write.
    assert cache.get(page_cache_key("about")) is not None
    with django_capture_on_commit_callbacks(execute=True):
        client.post(
            reverse("crm:content_page", args=[page.id]),
            {
                "action": "save_translation",
                "language": str(en.id),
                "title": "About",
                "body": "<p>Updated</p>",
            },
        )
    assert cache.get(page_cache_key("about")) is None

    preview = client.get(reverse("crm:content_page", args=[page.id]) + "?language=en")
    assert preview.status_code == 200
    preview_body = preview.content.decode()
    assert "&lt;p&gt;Updated&lt;/p&gt;" in preview_body
    assert "><p>Updated</p>" not in preview_body

    # Page-level publish audit entry is appended.
    from apps.crm.models import AdminAuditLog

    assert AdminAuditLog.objects.filter(
        action=AdminAuditLog.ACTION_PAGE_PUBLISHED,
        object_id=page.id,
        actor_id=editor.id,
    ).exists()


@pytest.mark.django_db
def test_content_and_analytics_role_boundaries() -> None:
    observer = _staff("content_observer", StaffRole.OBSERVER)
    observer_client = _client(observer)
    assert observer_client.get(reverse("crm:content")).status_code == 403
    assert observer_client.get(reverse("crm:content_translations")).status_code == 403
    assert observer_client.get(reverse("crm:content_pages")).status_code == 403
    assert observer_client.get(reverse("crm:analytics")).status_code == 200

    moderator = _staff("content_moderator", StaffRole.MODERATOR)
    moderator_client = _client(moderator)
    assert moderator_client.get(reverse("crm:analytics")).status_code == 403
    assert moderator_client.get(reverse("crm:analytics_export")).status_code == 403

    editor = _staff("content_editor_role", StaffRole.EDITOR)
    editor_client = _client(editor)
    assert editor_client.get(reverse("crm:content")).status_code == 200
    assert editor_client.get(reverse("crm:analytics")).status_code == 403

    anonymous = Client()
    response = anonymous.get(reverse("crm:content_translations"))
    assert response.status_code == 302
    assert response.url == reverse("crm:login")
