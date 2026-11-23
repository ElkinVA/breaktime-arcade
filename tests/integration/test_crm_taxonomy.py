"""CRM genre/tag CRUD, translation queue and related-game guards (§2.16.2)."""

from __future__ import annotations

import base64

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StaffRole, User
from apps.catalog.models import (
    Game,
    GameGenre,
    GameTag,
    Genre,
    GenreTranslation,
    Tag,
    TagTranslation,
)
from apps.crm.models import AdminAuditLog

PASSWORD = "correct horse battery staple"
# 1×1 transparent GIF.
GIF_BYTES = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")


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


def _language_id(code: str) -> str:
    from apps.i18n.models import Language

    return str(Language.objects.get(code=code).id)


def _game(technical_id: str, genre: Genre) -> Game:
    return Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=f"slug-{technical_id}",
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
    )


def _genre_payload(
    *, code: str, sort_order: int = 0, lang: str = "en", **translation: str
) -> dict[str, str]:
    payload = {
        "code": code,
        "sort_order": str(sort_order),
        "language": _language_id(lang),
    }
    payload.update(translation)
    return payload


def _tag_payload(
    *, code: str, needs_translation: bool = False, lang: str = "en", **translation: str
) -> dict[str, str]:
    payload = {"code": code}
    if needs_translation:
        payload["needs_translation"] = "on"
    payload["language"] = _language_id(lang)
    payload.update(translation)
    return payload


@pytest.mark.django_db
def test_genre_crud_translations_image_and_audit(tmp_path) -> None:
    editor = _staff("taxonomy_genre_editor", StaffRole.EDITOR)
    client = _client(editor)
    upload = SimpleUploadedFile("genre.gif", GIF_BYTES, content_type="image/gif")

    with override_settings(MEDIA_ROOT=str(tmp_path)):
        created = client.post(
            reverse("crm:genre_new"),
            _genre_payload(
                code="ARCADE",
                sort_order=7,
                name="Аркада",
                slug="arcade-ru",
                description="Классические аркады",
                seo_title="Аркадные игры",
                seo_description="Играйте в аркады",
            )
            | {"image": upload},
        )
    assert created.status_code == 302
    genre = Genre.objects.get(code="arcade")
    assert genre.sort_order == 7
    assert genre.image.name.startswith("genres/")
    translation = genre.translations.get(language__code="en")
    assert translation.name == "Аркада"
    assert translation.slug == "arcade-ru"
    assert translation.description == "Классические аркады"
    assert translation.seo_title == "Аркадные игры"
    assert translation.seo_description == "Играйте в аркады"
    assert AdminAuditLog.objects.filter(
        action=AdminAuditLog.ACTION_GENRE_CREATED,
        object_type="genre",
        object_id=genre.id,
        actor_id=editor.id,
    ).exists()
    assert client.get(reverse("crm:genre_edit", args=[genre.id])).status_code == 200

    saved = client.post(
        reverse("crm:genre_edit", args=[genre.id]),
        _genre_payload(
            code="arcade",
            sort_order=2,
            lang="ru",
            name="Аркада",
            slug="arkada",
            clear_image="on",
        ),
    )
    assert saved.status_code == 302
    genre.refresh_from_db()
    assert genre.sort_order == 2
    assert not genre.image
    ru = genre.translations.get(language__code="ru")
    assert ru.name == "Аркада"
    assert ru.slug == "arkada"
    assert AdminAuditLog.objects.filter(
        action=AdminAuditLog.ACTION_GENRE_UPDATED, object_id=genre.id
    ).exists()

    deleted = client.post(reverse("crm:genre_delete", args=[genre.id]))
    assert deleted.status_code == 302
    assert not Genre.objects.filter(pk=genre.id).exists()
    assert AdminAuditLog.objects.filter(
        action=AdminAuditLog.ACTION_GENRE_DELETED, object_id=genre.id
    ).exists()


@pytest.mark.django_db
def test_genre_delete_is_blocked_while_games_reference_it() -> None:
    editor = _staff("taxonomy_genre_guard", StaffRole.EDITOR)
    client = _client(editor)
    genre = Genre.objects.create(code="linked", sort_order=0)
    game = _game("linked_game", genre)
    GameGenre.objects.create(game=game, genre=genre)

    response = client.post(reverse("crm:genre_delete", args=[genre.id]), follow=True)
    assert response.status_code == 200
    assert Genre.objects.filter(pk=genre.id).exists()
    assert "используется играми" in response.content.decode()
    assert not AdminAuditLog.objects.filter(action=AdminAuditLog.ACTION_GENRE_DELETED).exists()

    # A primary genre alone is also a hard reference.
    primary_only = Genre.objects.create(code="primary_only", sort_order=0)
    _game("primary_game", primary_only)
    response = client.post(reverse("crm:genre_delete", args=[primary_only.id]), follow=True)
    assert response.status_code == 200
    assert Genre.objects.filter(pk=primary_only.id).exists()


@pytest.mark.django_db
def test_tag_crud_translation_queue_and_audit() -> None:
    editor = _staff("taxonomy_tag_editor", StaffRole.EDITOR)
    client = _client(editor)

    created = client.post(
        reverse("crm:tag_new"),
        _tag_payload(code="speedrun", needs_translation=True),
    )
    assert created.status_code == 302
    tag = Tag.objects.get(code="speedrun")
    assert tag.needs_translation is True
    assert AdminAuditLog.objects.filter(
        action=AdminAuditLog.ACTION_TAG_CREATED,
        object_type="tag",
        object_id=tag.id,
        actor_id=editor.id,
    ).exists()
    assert client.get(reverse("crm:tag_edit", args=[tag.id])).status_code == 200

    translated_tag = Tag.objects.create(code="translated", needs_translation=False)

    queue = client.get(reverse("crm:tags"), {"queue": "requires-translation"})
    assert queue.status_code == 200
    body = queue.content.decode()
    assert "speedrun" in body
    assert "translated" not in body

    saved = client.post(
        reverse("crm:tag_edit", args=[tag.id]),
        _tag_payload(
            code="speedrun",
            needs_translation=True,
            name="Спидран",
            slug="spidran",
        ),
    )
    assert saved.status_code == 302
    tag.refresh_from_db()
    assert tag.needs_translation is False
    assert tag.translations.get(language__code="en").name == "Спидран"
    assert AdminAuditLog.objects.filter(
        action=AdminAuditLog.ACTION_TAG_UPDATED, object_id=tag.id
    ).exists()

    queue_after = client.get(reverse("crm:tags"), {"queue": "requires-translation"})
    assert "speedrun" not in queue_after.content.decode()

    deleted = client.post(reverse("crm:tag_delete", args=[translated_tag.id]))
    assert deleted.status_code == 302
    assert not Tag.objects.filter(pk=translated_tag.id).exists()
    assert AdminAuditLog.objects.filter(
        action=AdminAuditLog.ACTION_TAG_DELETED, object_id=translated_tag.id
    ).exists()


@pytest.mark.django_db
def test_tag_delete_is_blocked_while_games_reference_it() -> None:
    editor = _staff("taxonomy_tag_guard", StaffRole.EDITOR)
    client = _client(editor)
    genre = Genre.objects.create(code="tag_guard_genre", sort_order=0)
    game = _game("tag_guard_game", genre)
    tag = Tag.objects.create(code="used_tag", needs_translation=False)
    GameTag.objects.create(game=game, tag=tag)

    response = client.post(reverse("crm:tag_delete", args=[tag.id]), follow=True)
    assert response.status_code == 200
    assert Tag.objects.filter(pk=tag.id).exists()
    assert "используется играми" in response.content.decode()
    assert not AdminAuditLog.objects.filter(action=AdminAuditLog.ACTION_TAG_DELETED).exists()


@pytest.mark.django_db
def test_genre_list_reflects_sort_order() -> None:
    editor = _staff("taxonomy_sort_editor", StaffRole.EDITOR)
    client = _client(editor)
    Genre.objects.create(code="sort_second", sort_order=20)
    Genre.objects.create(code="sort_first", sort_order=10)
    Genre.objects.create(code="sort_middle", sort_order=15)

    response = client.get(reverse("crm:genres"))

    assert response.status_code == 200
    body = response.content.decode()
    assert body.index("sort_first") < body.index("sort_middle") < body.index("sort_second")


@pytest.mark.django_db
def test_taxonomy_routes_require_content_manage() -> None:
    observer = _staff("taxonomy_observer", StaffRole.OBSERVER)
    observer_client = _client(observer)
    assert observer_client.get(reverse("crm:genres")).status_code == 403
    assert observer_client.get(reverse("crm:tags")).status_code == 403

    moderator = _staff("taxonomy_moderator", StaffRole.MODERATOR)
    moderator_client = _client(moderator)
    assert moderator_client.get(reverse("crm:genres")).status_code == 403
    assert moderator_client.get(reverse("crm:tags")).status_code == 403

    anonymous = Client()
    response = anonymous.get(reverse("crm:genres"))
    assert response.status_code == 302
    assert response.url == reverse("crm:login")

    editor = _staff("taxonomy_editor", StaffRole.EDITOR)
    editor_client = _client(editor)
    assert editor_client.get(reverse("crm:genres")).status_code == 200
    assert editor_client.get(reverse("crm:genre_new")).status_code == 200
    assert editor_client.get(reverse("crm:tags")).status_code == 200
    assert editor_client.get(reverse("crm:tag_new")).status_code == 200


@pytest.mark.django_db
def test_tag_translation_is_upserted_per_language() -> None:
    editor = _staff("taxonomy_tag_translations", StaffRole.EDITOR)
    client = _client(editor)
    tag = Tag.objects.create(code="localized", needs_translation=True)

    first = client.post(
        reverse("crm:tag_edit", args=[tag.id]),
        _tag_payload(
            code="localized",
            needs_translation=True,
            lang="ru",
            name="Русский",
            slug="russkiy",
        ),
    )
    assert first.status_code == 302
    second = client.post(
        reverse("crm:tag_edit", args=[tag.id]),
        _tag_payload(
            code="localized",
            needs_translation=True,
            lang="ru",
            name="Русский!",
            slug="russkiy-2",
        ),
    )
    assert second.status_code == 302

    assert TagTranslation.objects.filter(tag=tag).count() == 1
    translation = tag.translations.get(language__code="ru")
    assert translation.name == "Русский!"
    assert translation.slug == "russkiy-2"
    assert GenreTranslation.objects.count() == 0
