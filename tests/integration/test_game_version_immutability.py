from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Game, GameVersion, Genre


def _version(
    *,
    created_by: User | None = None,
    manual_review_by: User | None = None,
) -> GameVersion:
    genre = Genre.objects.create(code="version_immutability")
    game = Game.objects.create(
        technical_id="version_immutability",
        host_label="version-immutability.games.test",
        slug="version-immutability",
        primary_genre=genre,
        published_at=timezone.now(),
    )
    return GameVersion.objects.create(
        game=game,
        semver="1.0.0",
        package_hash="a" * 64,
        runtime_hash="b" * 64,
        sdk_version="1.1.0",
        size_bytes=1024,
        manifest={"name": "immutable"},
        supported_languages=["en"],
        created_by=created_by,
        manual_review_by=manual_review_by,
    )


@pytest.mark.django_db
def test_model_rejects_content_changes() -> None:
    version = _version()
    version.package_hash = "c" * 64

    with pytest.raises(ValidationError):
        version.save()

    version.refresh_from_db()
    assert version.package_hash == "a" * 64


@pytest.mark.django_db
def test_model_allows_audit_references_to_be_nulled_only() -> None:
    user = User.objects.create_user(login="audit-user", password="correct horse battery staple")
    version = _version(created_by=user, manual_review_by=user)

    version.created_by = None
    version.manual_review_by = None
    version.save(update_fields=["created_by", "manual_review_by"])

    version.refresh_from_db()
    assert version.created_by is None
    assert version.manual_review_by is None


@pytest.mark.django_db
def test_model_update_fields_checks_only_written_content() -> None:
    user = User.objects.create_user(login="audit-user", password="correct horse battery staple")
    version = _version(created_by=user, manual_review_by=user)

    version.package_hash = "c" * 64
    version.manual_review_by = None
    version.save(update_fields=["manual_review_by"])

    version.refresh_from_db()
    assert version.package_hash == "a" * 64
    assert version.manual_review_by is None


@pytest.mark.django_db
def test_model_rejects_non_null_audit_change() -> None:
    user = User.objects.create_user(login="audit-user", password="correct horse battery staple")
    version = _version()

    version.created_by = user
    with pytest.raises(ValidationError):
        version.save()


@pytest.mark.django_db
def test_database_trigger_blocks_content_update() -> None:
    version = _version()

    with pytest.raises(DatabaseError), transaction.atomic():
        GameVersion.objects.filter(pk=version.pk).update(package_hash="c" * 64)

    version.refresh_from_db()
    assert version.package_hash == "a" * 64


@pytest.mark.django_db
def test_database_trigger_blocks_audit_retarget() -> None:
    first = User.objects.create_user(login="audit-first", password="correct horse battery staple")
    second = User.objects.create_user(login="audit-second", password="correct horse battery staple")
    version = _version(created_by=first)

    with pytest.raises(DatabaseError), transaction.atomic():
        GameVersion.objects.filter(pk=version.pk).update(created_by=second)


@pytest.mark.django_db
def test_bulk_update_audit_null_is_allowed() -> None:
    user = User.objects.create_user(login="audit-user", password="correct horse battery staple")
    version = _version(created_by=user)
    version.created_by = None

    with transaction.atomic():
        GameVersion.objects.bulk_update([version], ["created_by"])

    version.refresh_from_db()
    assert version.created_by is None


@pytest.mark.django_db
def test_bulk_update_content_is_blocked_by_trigger() -> None:
    version = _version()
    version.package_hash = "c" * 64

    with pytest.raises(DatabaseError), transaction.atomic():
        GameVersion.objects.bulk_update([version], ["package_hash"])


@pytest.mark.django_db
def test_database_trigger_allows_audit_null() -> None:
    user = User.objects.create_user(login="audit-user", password="correct horse battery staple")
    version = _version(created_by=user, manual_review_by=user)

    with transaction.atomic():
        GameVersion.objects.filter(pk=version.pk).update(created_by=None, manual_review_by=None)

    version.refresh_from_db()
    assert version.created_by is None
    assert version.manual_review_by is None


@pytest.mark.django_db
def test_user_deletion_nulls_version_audit_references() -> None:
    user = User.objects.create_user(login="audit-user", password="correct horse battery staple")
    version = _version(created_by=user, manual_review_by=user)

    user.delete()

    version.refresh_from_db()
    assert version.created_by is None
    assert version.manual_review_by is None


@pytest.mark.django_db
def test_database_trigger_blocks_non_null_audit_change() -> None:
    user = User.objects.create_user(login="audit-user", password="correct horse battery staple")
    version = _version()

    with pytest.raises(DatabaseError), transaction.atomic():
        GameVersion.objects.filter(pk=version.pk).update(created_by=user)


@pytest.mark.django_db
def test_noop_save_is_allowed() -> None:
    version = _version()
    version.save()
    version.refresh_from_db()
    assert version.package_hash == "a" * 64


@pytest.mark.django_db
def test_nullable_content_transition_is_blocked() -> None:
    version = _version()
    assert version.critical_path_bytes_measured is None

    with pytest.raises(DatabaseError), transaction.atomic():
        GameVersion.objects.filter(pk=version.pk).update(critical_path_bytes_measured=1)


@pytest.mark.django_db
def test_jsonb_expression_update_is_blocked() -> None:
    version = _version()

    with (
        pytest.raises(DatabaseError),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "UPDATE catalog_game_version SET manifest = manifest || %s::jsonb WHERE id = %s",
            ['{"changed": true}', version.pk],
        )


@pytest.mark.django_db
def test_on_conflict_update_is_blocked() -> None:
    version = _version()
    version.package_hash = "c" * 64

    with pytest.raises(DatabaseError), transaction.atomic():
        GameVersion.objects.bulk_create(
            [version],
            update_conflicts=True,
            unique_fields=["id"],
            update_fields=["package_hash"],
        )


@pytest.mark.django_db
def test_trigger_covers_every_content_column() -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT prosrc, prosecdef FROM pg_proc WHERE proname = %s",
            ["ba_game_version_immutable"],
        )
        row = cursor.fetchone()

    assert row is not None
    source, security_definer = row
    assert security_definer is False
    for field in GameVersion.IMMUTABLE_FIELDS:
        assert f"NEW.{field}" in source
    for field in GameVersion.AUDIT_FIELDS:
        assert f"NEW.{field}_id" in source
