"""CRM customer account management (§2.16.2): search, profile, actions."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import (
    EmailAddress,
    RecoveryCode,
    StaffRole,
    User,
    UserProfile,
)
from apps.catalog.models import Game, GameVersion, Genre
from apps.crm.models import AdminAuditLog
from apps.gameplay.models import GameResult, GameSession, LeaderboardEntry

PASSWORD = "correct horse battery staple"


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


def _customer(
    login: str,
    nickname: str,
    *,
    email: str | None = None,
    verified: bool = False,
    is_active: bool = True,
) -> User:
    user = User.objects.create_user(login=login, password=PASSWORD, is_active=is_active)
    UserProfile.objects.create(user=user, nickname=nickname, nickname_skeleton=nickname.lower())
    if email is not None:
        EmailAddress.objects.create(
            user=user,
            email=email,
            verified_at=timezone.now() if verified else None,
        )
    return user


def _game(technical_id: str = "users_game") -> Game:
    genre, _ = Genre.objects.get_or_create(code="users_genre")
    game = Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=f"slug-{technical_id}",
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
        score_direction="higher_is_better",
        leaderboard_enabled=True,
    )
    version = GameVersion.objects.create(
        game=game,
        semver="1.0.0",
        package_hash="a" * 64,
        runtime_hash="b" * 64,
        sdk_version="1.1.0",
        size_bytes=1000,
        manifest={},
        supported_languages=["en"],
    )
    game.current_version = version
    game.save(update_fields=["current_version"])
    return game


def _result_and_entry(game: Game, user: User, value: int = 42) -> GameResult:
    now = timezone.now()
    session = GameSession.objects.create(
        game=game,
        game_version=game.current_version,
        subject_type=GameSession.SUBJECT_USER,
        subject_id=user.id,
        mode=GameSession.MODE_USER,
        state=GameSession.STATE_FINISHED,
        seed="seed",
        max_session_seconds=1800,
        activated_at=now - timedelta(seconds=30),
        last_heartbeat_at=now,
        finished_at=now,
    )
    result = GameResult.objects.create(
        session=session,
        game=game,
        game_version=game.current_version,
        subject_type=GameResult.SUBJECT_USER,
        user=user,
        epoch=game.leaderboard_epoch,
        value=value,
        unit=game.score_unit,
        duration_ms=30_000,
        idempotency_key=f"key-{user.pk}-{value}",
    )
    LeaderboardEntry.objects.create(
        game=game,
        epoch=game.leaderboard_epoch,
        user=user,
        best_result=result,
        value=value,
        achieved_at=result.created_at,
        trust_level=GameResult.TRUST_CLIENT_REPORTED,
    )
    return result


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role",
    [StaffRole.EDITOR, StaffRole.MODERATOR, StaffRole.OBSERVER],
)
def test_non_owner_staff_gets_403_everywhere(role: str) -> None:
    staff = _staff(f"denied_{role}", role)
    target = _customer("target", "Target")
    client = _client(staff)

    assert client.get(reverse("crm:users")).status_code == 403
    assert client.get(reverse("crm:user_detail", args=[target.id])).status_code == 403
    assert client.get(reverse("crm:user_export", args=[target.id])).status_code == 403
    assert client.post(reverse("crm:user_block", args=[target.id])).status_code == 403
    assert client.post(reverse("crm:user_delete", args=[target.id])).status_code == 403


@pytest.mark.django_db
def test_owner_can_open_list_and_detail() -> None:
    owner = _staff("owner", StaffRole.OWNER)
    target = _customer("target", "Target", email="target@example.com", verified=True)
    client = _client(owner)

    response = client.get(reverse("crm:users"))
    assert response.status_code == 200
    assert "target" in response.content.decode()

    detail = client.get(reverse("crm:user_detail", args=[target.id]))
    assert detail.status_code == 200
    body = detail.content.decode()
    assert "target" in body
    assert "Target" in body
    assert "target@example.com" in body


@pytest.mark.django_db
def test_search_matches_login_nickname_and_email_case_insensitively() -> None:
    owner = _staff("owner", StaffRole.OWNER)
    by_login = _customer("alice", "Wonder", email="alice@example.com")
    by_nickname = _customer("bob", "RabbitHole")
    by_email = _customer("carol", "Carol", email="Zebra@Example.com")
    client = _client(owner)

    def logins(query: str) -> set[str]:
        response = client.get(reverse("crm:users"), {"q": query})
        assert response.status_code == 200
        return {user.login for user in response.context["users"]}

    assert logins("ALICE") == {by_login.login}
    assert logins("rabbit") == {by_nickname.login}
    assert logins("zebra@example") == {by_email.login}
    # One character does not trigger the search; the full list is returned.
    assert logins("a") == {by_login.login, by_nickname.login, by_email.login}


@pytest.mark.django_db
def test_filters_by_email_verified_and_blocked_status() -> None:
    owner = _staff("owner", StaffRole.OWNER)
    verified = _customer("verified", "Verified", email="verified@example.com", verified=True)
    unverified = _customer("unverified", "Unverified", email="unverified@example.com")
    unconfirmed = _customer("unconfirmed", "Unconfirmed")
    blocked = _customer(
        "blocked",
        "Blocked",
        email="blocked@example.com",
        verified=True,
        is_active=False,
    )
    client = _client(owner)

    def logins(**params: str) -> set[str]:
        response = client.get(reverse("crm:users"), params)
        assert response.status_code == 200
        return {user.login for user in response.context["users"]}

    assert logins(email_verified="true") == {verified.login, blocked.login}
    assert logins(email_verified="false") == {
        unverified.login,
        unconfirmed.login,
    }
    assert logins(blocked="true") == {blocked.login}
    assert logins(blocked="false") == {verified.login, unverified.login, unconfirmed.login}


@pytest.mark.django_db
def test_detail_renders_results_and_leaderboard_without_secrets() -> None:
    owner = _staff("owner", StaffRole.OWNER)
    target = _customer("target", "Target", email="target@example.com", verified=True)
    User.objects.filter(pk=target.pk).update(totp_secret="TOPSECRETTOTP")
    target.refresh_from_db()
    target.set_password(PASSWORD)
    target.save(update_fields=["password"])
    RecoveryCode.objects.create(user=target, code_hash="f" * 64)
    game = _game("visible_game")
    _result_and_entry(game, target, value=77)

    response = _client(owner).get(reverse("crm:user_detail", args=[target.id]))
    assert response.status_code == 200
    body = response.content.decode()

    assert game.technical_id in body
    assert "77" in body
    assert response.context["results"].count() == 1
    assert response.context["leaderboard_entries"].count() == 1

    assert target.password not in body
    assert "TOPSECRETTOTP" not in body
    assert "f" * 64 not in body
    assert "pbkdf2_" not in body
    assert "argon2" not in body


@pytest.mark.django_db
def test_block_and_unblock_toggle_active_audit_and_authentication() -> None:
    owner = _staff("owner", StaffRole.OWNER)
    target = _customer("target", "Target")
    client = _client(owner)

    blocked = client.post(reverse("crm:user_block", args=[target.id]))
    assert blocked.status_code == 302
    target.refresh_from_db()
    assert target.is_active is False
    audit = AdminAuditLog.objects.get(action=AdminAuditLog.ACTION_USER_BLOCKED)
    assert audit.actor_id == owner.id
    assert audit.object_type == "user"
    assert audit.object_id == target.id

    assert Client().login(username=target.login, password=PASSWORD) is False

    unblocked = client.post(reverse("crm:user_unblock", args=[target.id]))
    assert unblocked.status_code == 302
    target.refresh_from_db()
    assert target.is_active is True
    assert AdminAuditLog.objects.filter(
        action=AdminAuditLog.ACTION_USER_UNBLOCKED, object_id=target.id
    ).exists()
    assert Client().login(username=target.login, password=PASSWORD) is True


@pytest.mark.django_db
def test_delete_requests_window_then_anonymizes_when_due_and_is_idempotent() -> None:
    owner = _staff("owner", StaffRole.OWNER)
    target = _customer("target", "Target", email="target@example.com")
    client = _client(owner)

    scheduled = client.post(reverse("crm:user_delete", args=[target.id]))
    assert scheduled.status_code == 302
    target.refresh_from_db()
    profile = UserProfile.objects.get(user=target)
    assert profile.deletion_requested_at is not None
    assert AdminAuditLog.objects.filter(
        action=AdminAuditLog.ACTION_USER_DELETION_REQUESTED, object_id=target.id
    ).exists()

    # Inside the cancellation window nothing is purged.
    again = client.post(reverse("crm:user_delete", args=[target.id]))
    assert again.status_code == 302
    assert UserProfile.objects.filter(user=target).exists()

    UserProfile.objects.filter(user=target).update(
        deletion_requested_at=timezone.now() - timedelta(days=8)
    )
    deleted = client.post(reverse("crm:user_delete", args=[target.id]))
    assert deleted.status_code == 302
    target.refresh_from_db()
    assert target.is_active is False
    assert target.login.startswith("deleted-")
    assert not UserProfile.objects.filter(user=target).exists()
    assert not EmailAddress.objects.filter(user=target).exists()
    assert AdminAuditLog.objects.filter(
        action=AdminAuditLog.ACTION_USER_DELETED, object_id=target.id
    ).exists()

    repeat = client.post(reverse("crm:user_delete", args=[target.id]))
    assert repeat.status_code == 302
    assert (
        AdminAuditLog.objects.filter(
            action=AdminAuditLog.ACTION_USER_DELETED, object_id=target.id
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_export_matches_cabinet_shape_and_is_an_attachment() -> None:
    owner = _staff("owner", StaffRole.OWNER)
    target = _customer("target", "Target", email="target@example.com", verified=True)

    cabinet = Client()
    assert cabinet.login(username=target.login, password=PASSWORD) is True
    account_export = cabinet.get(reverse("account:export"))
    assert account_export.status_code == 200

    crm_export = _client(owner).get(reverse("crm:user_export", args=[target.id]))
    assert crm_export.status_code == 200
    assert "attachment" in crm_export["Content-Disposition"]
    assert "breaktime-account.json" in crm_export["Content-Disposition"]

    assert json.loads(crm_export.content) == json.loads(account_export.content)
