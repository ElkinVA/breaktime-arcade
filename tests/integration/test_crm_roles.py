"""CRM roles, least privilege, step-up, lockouts and audit trail (§2.16)."""

from __future__ import annotations

import pyotp
import pytest
from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StaffRole, User
from apps.catalog.models import Game, GameVersion, Genre
from apps.crm.models import AdminAuditLog
from apps.crm.services.staff import change_staff_role, set_staff_active

PASSWORD = "correct horse battery staple"


def _staff(
    login: str,
    role: str,
    *,
    is_active: bool = True,
    secret: str = "",
) -> User:
    user = User.objects.create_user(
        login=login,
        password=PASSWORD,
        is_staff=True,
        is_active=is_active,
        crm_role=role,
    )
    User.objects.filter(pk=user.pk).update(
        totp_confirmed_at=timezone.now(),
        totp_secret=secret,
    )
    user.refresh_from_db()
    return user


def _client(user: User, *, verified_2fa: bool = True) -> Client:
    client = Client()
    client.force_login(user)
    if verified_2fa:
        session = client.session
        session["ba_2fa_verified"] = True
        session.save()
    return client


def _elevate(client: Client) -> None:
    session = client.session
    session["crm_step_up_at"] = timezone.now().isoformat()
    session.save()


def _game(technical_id: str = "role_game", *, versions: int = 1) -> Game:
    genre, _ = Genre.objects.get_or_create(code="arcade")
    game = Game.objects.create(
        technical_id=technical_id,
        host_label=technical_id.replace("_", "-") + ".games.test",
        slug=f"slug-{technical_id}",
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
    )
    created = []
    for index in range(versions):
        version = GameVersion.objects.create(
            game=game,
            semver=f"{index + 1}.0.0",
            package_hash=str(index + 1) * 64,
            runtime_hash=str(index + 5) * 64,
            sdk_version="1.1.0",
            size_bytes=1000,
            manifest={},
            supported_languages=["en"],
            validation_report={"ok": True, "summary": {"blocker": 0}},
            e2e_report={"passed": True},
        )
        created.append(version)
    if created:
        game.current_version = created[-1]
        game.save(update_fields=["current_version"])
    return game


def _expected_denied(role: str) -> set[str]:
    return {
        StaffRole.OWNER: set(),
        StaffRole.EDITOR: {"crm:staff", "crm:moderation", "crm:audit", "crm:dashboard"},
        StaffRole.MODERATOR: {
            "crm:staff",
            "crm:dashboard",
            "crm:games",
            "crm:content",
            "crm:audit",
        },
        StaffRole.OBSERVER: {"crm:staff", "crm:games", "crm:content", "crm:moderation"},
    }[role]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role",
    [StaffRole.OWNER, StaffRole.EDITOR, StaffRole.MODERATOR, StaffRole.OBSERVER],
)
def test_each_role_only_reaches_its_sections(role: str) -> None:
    staff = _staff(f"role_{role}", role)
    client = _client(staff)
    denied = _expected_denied(role)

    sections = (
        "crm:dashboard",
        "crm:games",
        "crm:content",
        "crm:moderation",
        "crm:audit",
        "crm:staff",
    )
    for name in sections:
        response = client.get(reverse(name))
        if name in denied:
            assert response.status_code == 403, name
        else:
            assert response.status_code == 200, (role, name)


@pytest.mark.django_db
def test_roleless_staff_non_staff_and_unverified_2fa_are_blocked() -> None:
    roleless = User.objects.create_user(login="roleless", password=PASSWORD, is_staff=True)
    User.objects.filter(pk=roleless.pk).update(totp_confirmed_at=timezone.now())
    roleless.refresh_from_db()
    roleless_client = _client(roleless)
    assert roleless_client.get(reverse("crm:games")).status_code == 403

    plain = User.objects.create_user(login="plain_user", password=PASSWORD)
    plain_client = _client(plain)
    response = plain_client.get(reverse("crm:games"))
    assert response.status_code == 302
    assert response.url == reverse("crm:login")

    owner = _staff("unverified_owner", StaffRole.OWNER)
    unverified = _client(owner, verified_2fa=False)
    response = unverified.get(reverse("crm:games"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("accounts:login"))


@pytest.mark.django_db
def test_editor_cannot_publish_and_moderator_cannot_import() -> None:
    game = _game(versions=1)
    version = game.current_version
    assert version is not None

    editor = _staff("editor_denied", StaffRole.EDITOR)
    editor_client = _client(editor)
    _elevate(editor_client)
    assert editor_client.get(reverse("crm:wizard_upload")).status_code == 200
    response = editor_client.post(
        reverse("crm:game_publish", args=[game.id]),
        {"version_id": str(version.id)},
    )
    assert response.status_code == 403
    assert AdminAuditLog.objects.count() == 0

    moderator = _staff("moderator_denied", StaffRole.MODERATOR)
    moderator_client = _client(moderator)
    assert moderator_client.get(reverse("crm:wizard_upload")).status_code == 403
    assert moderator_client.get(reverse("crm:games")).status_code == 403

    observer = _staff("observer_denied", StaffRole.OBSERVER)
    observer_client = _client(observer)
    assert observer_client.get(reverse("crm:content")).status_code == 403
    assert observer_client.get(reverse("crm:moderation")).status_code == 403


def _post_staff_change(client: Client, *, action: str, target: User, **extra: str):
    payload = {"action": action, "user_id": str(target.id), **extra}
    return client.post(reverse("crm:staff"), payload)


@pytest.mark.django_db
def test_staff_changes_require_step_up_and_are_audited() -> None:
    owner = _staff("owner_actor", StaffRole.OWNER)
    target = _staff("target_editor", StaffRole.EDITOR)
    client = _client(owner)

    listing = client.get(reverse("crm:staff"))
    assert listing.status_code == 200
    listing_content = listing.content.decode()
    assert owner.login in listing_content
    assert target.login in listing_content

    no_step_up = _post_staff_change(client, action="role", target=target, role=StaffRole.MODERATOR)
    assert no_step_up.status_code == 302
    assert no_step_up.url.startswith(reverse("crm:step_up"))
    target.refresh_from_db()
    assert target.crm_role == StaffRole.EDITOR
    assert AdminAuditLog.objects.count() == 0

    wrong = _post_staff_change(
        client,
        action="role",
        target=target,
        role=StaffRole.MODERATOR,
        password="wrong",
        totp_code="000000",
    )
    assert wrong.status_code == 302
    assert wrong.url == reverse("crm:staff")
    target.refresh_from_db()
    assert target.crm_role == StaffRole.EDITOR
    assert AdminAuditLog.objects.count() == 0

    _elevate(client)
    assigned = _post_staff_change(client, action="role", target=target, role=StaffRole.MODERATOR)
    assert assigned.status_code == 302
    target.refresh_from_db()
    assert target.crm_role == StaffRole.MODERATOR
    role_audit = AdminAuditLog.objects.get(action=AdminAuditLog.ACTION_STAFF_ROLE_CHANGED)
    assert role_audit.actor_id == owner.id
    assert role_audit.object_type == "user"
    assert role_audit.object_id == target.id
    assert role_audit.created_at is not None
    assert role_audit.before_data == {"crm_role": StaffRole.EDITOR, "is_active": True}
    assert role_audit.after_data == {"crm_role": StaffRole.MODERATOR, "is_active": True}

    deactivated = _post_staff_change(client, action="active", target=target, active="0")
    assert deactivated.status_code == 302
    target.refresh_from_db()
    assert target.is_active is False
    assert AdminAuditLog.objects.filter(
        action=AdminAuditLog.ACTION_STAFF_DEACTIVATED, object_id=target.id
    ).exists()

    activated = _post_staff_change(client, action="active", target=target, active="1")
    assert activated.status_code == 302
    target.refresh_from_db()
    assert target.is_active is True
    assert AdminAuditLog.objects.filter(
        action=AdminAuditLog.ACTION_STAFF_ACTIVATED, object_id=target.id
    ).exists()


@pytest.mark.django_db
def test_step_up_with_password_and_totp_allows_role_assignment() -> None:
    secret = pyotp.random_base32()
    owner = _staff("owner_totp", StaffRole.OWNER, secret=secret)
    target = _staff("target_totp", StaffRole.EDITOR)
    client = _client(owner)

    response = _post_staff_change(
        client,
        action="role",
        target=target,
        role=StaffRole.OBSERVER,
        password=PASSWORD,
        totp_code=pyotp.TOTP(secret).now(),
    )

    assert response.status_code == 302
    target.refresh_from_db()
    assert target.crm_role == StaffRole.OBSERVER
    assert AdminAuditLog.objects.filter(
        action=AdminAuditLog.ACTION_STAFF_ROLE_CHANGED, object_id=target.id
    ).exists()


@pytest.mark.django_db
def test_self_lockout_is_prevented() -> None:
    owner = _staff("self_owner", StaffRole.OWNER)
    client = _client(owner)
    _elevate(client)

    demote = _post_staff_change(client, action="role", target=owner, role=StaffRole.EDITOR)
    assert demote.status_code == 302
    owner.refresh_from_db()
    assert owner.crm_role == StaffRole.OWNER

    deactivate = _post_staff_change(client, action="active", target=owner, active="0")
    assert deactivate.status_code == 302
    owner.refresh_from_db()
    assert owner.is_active is True
    assert AdminAuditLog.objects.count() == 0


@pytest.mark.django_db
def test_last_owner_lockout_is_prevented_at_service_level() -> None:
    last_owner = _staff("last_owner", StaffRole.OWNER)
    # An actor can only be another role-holder; use an inactive owner so the
    # target is the single *active* owner. Capability checks still pass.
    actor = _staff("inactive_owner", StaffRole.OWNER, is_active=False)

    demote = change_staff_role(
        actor=actor,
        target_id=last_owner.id,
        role=StaffRole.EDITOR,
    )
    assert demote.ok is False
    assert demote.reason == "last_owner"
    last_owner.refresh_from_db()
    assert last_owner.crm_role == StaffRole.OWNER

    deactivate = set_staff_active(
        actor=actor,
        target_id=last_owner.id,
        is_active=False,
    )
    assert deactivate.ok is False
    assert deactivate.reason == "last_owner"
    last_owner.refresh_from_db()
    assert last_owner.is_active is True
    assert AdminAuditLog.objects.count() == 0


@pytest.mark.django_db
def test_publish_and_rollback_are_audited_and_log_is_immutable() -> None:
    owner = _staff("publish_owner", StaffRole.OWNER)
    game = _game("audited_game", versions=2)
    old_version, new_version = list(game.versions.order_by("semver"))
    from apps.pipeline.services.publishing import publish_version

    assert publish_version(game, old_version, actor=owner).ok
    client = _client(owner)
    _elevate(client)

    response = client.post(
        reverse("crm:game_publish", args=[game.id]),
        {"version_id": str(new_version.id)},
    )
    assert response.status_code == 302
    game.refresh_from_db()
    assert game.current_version_id == new_version.id
    published = AdminAuditLog.objects.filter(
        action=AdminAuditLog.ACTION_GAME_PUBLISHED,
        after_data__current_version_id=str(new_version.id),
    ).get()
    assert published.actor_id == owner.id
    assert published.object_type == "game"
    assert published.object_id == game.id
    assert published.created_at is not None
    assert published.after_data["current_version_id"] == str(new_version.id)

    response = client.post(
        reverse("crm:game_rollback", args=[game.id]),
        {"version_id": str(old_version.id)},
    )
    assert response.status_code == 302
    game.refresh_from_db()
    assert game.current_version_id == old_version.id
    rolled_back = AdminAuditLog.objects.get(action=AdminAuditLog.ACTION_GAME_ROLLED_BACK)
    assert rolled_back.actor_id == owner.id
    assert rolled_back.object_id == game.id

    with pytest.raises(ValidationError):
        published.save()
    with pytest.raises(ValidationError):
        published.delete()
    with pytest.raises(DatabaseError), transaction.atomic():
        AdminAuditLog.objects.filter(pk=published.pk).update(reason="tampered")
    published.refresh_from_db()
    assert published.reason == ""

    # ON DELETE SET NULL for the actor must remain possible on an append-only log.
    with transaction.atomic():
        AdminAuditLog.objects.filter(pk=published.pk).update(actor=None)
    published.refresh_from_db()
    assert published.actor_id is None


@pytest.mark.django_db
def test_superuser_manager_defaults_to_owner() -> None:
    superuser = User.objects.create_superuser(login="root_owner", password=PASSWORD)
    assert superuser.is_staff is True
    assert superuser.crm_role == StaffRole.OWNER
