"""CRM customer account management (§2.16.2): search, profile, actions."""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import timedelta

import pytest
from django.db import connections
from django.http import HttpResponse
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import (
    EmailAddress,
    RecoveryCode,
    StaffRole,
    User,
    UserProfile,
)
from apps.accounts.services import profile as profile_service
from apps.accounts.services.profile import anonymize_user
from apps.catalog.models import Game, GameVersion, Genre
from apps.crm.models import AdminAuditLog
from apps.crm.services import users as crm_users
from apps.gameplay.models import (
    GameResult,
    GameSession,
    GameStorage,
    LeaderboardEntry,
    UserGamePlaytime,
)
from apps.gameplay.services import results as results_service
from apps.gameplay.services import sessions as sessions_service
from apps.gameplay.services import storage as storage_service
from apps.gameplay.services.results import submit_result
from apps.gameplay.services.sessions import (
    SessionError,
    activate_session,
    create_session,
    heartbeat,
)
from apps.gameplay.services.storage import put_storage

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


def _step_up(client: Client) -> None:
    session = client.session
    session["crm_step_up_at"] = timezone.now().isoformat()
    session.save()


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
    assert client.post(reverse("crm:user_unblock", args=[target.id])).status_code == 403
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
def test_block_and_unblock_are_explicit_audited_and_authenticate() -> None:
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
def test_repeated_block_does_not_unblock_and_is_not_audited_twice() -> None:
    owner = _staff("owner", StaffRole.OWNER)
    target = _customer("target", "Target")
    client = _client(owner)

    assert client.post(reverse("crm:user_block", args=[target.id])).status_code == 302
    again = client.post(reverse("crm:user_block", args=[target.id]))
    assert again.status_code == 302
    target.refresh_from_db()
    assert target.is_active is False
    assert (
        AdminAuditLog.objects.filter(
            action=AdminAuditLog.ACTION_USER_BLOCKED, object_id=target.id
        ).count()
        == 1
    )

    assert client.post(reverse("crm:user_unblock", args=[target.id])).status_code == 302
    second_unblock = client.post(reverse("crm:user_unblock", args=[target.id]))
    assert second_unblock.status_code == 302
    target.refresh_from_db()
    assert target.is_active is True
    assert (
        AdminAuditLog.objects.filter(
            action=AdminAuditLog.ACTION_USER_UNBLOCKED, object_id=target.id
        ).count()
        == 1
    )

    first = crm_users.block_user(actor=owner, target_id=target.id)
    second = crm_users.block_user(actor=owner, target_id=target.id)
    assert first.ok and first.changed is True and first.audit is not None
    assert second.ok and second.changed is False and second.audit is None


def _session(
    game: Game,
    user: User,
    state: str,
    *,
    seed: str,
    **fields: object,
) -> GameSession:
    now = timezone.now()
    defaults: dict[str, object] = {
        "max_session_seconds": 1800,
        "activated_at": now - timedelta(seconds=60) if state != GameSession.STATE_CREATED else None,
        "last_heartbeat_at": now if state != GameSession.STATE_CREATED else None,
    }
    defaults.update(fields)
    return GameSession.objects.create(
        game=game,
        game_version=game.current_version,
        subject_type=GameSession.SUBJECT_USER,
        subject_id=user.id,
        mode=GameSession.MODE_USER,
        state=state,
        seed=seed,
        **defaults,
    )


@pytest.mark.django_db
def test_block_revokes_open_sessions_but_not_closed_ones() -> None:
    owner = _staff("owner", StaffRole.OWNER)
    target = _customer("target", "Target")
    other = _customer("other", "Other")
    game = _game("revoke_state_game")
    expires_at = timezone.now() + timedelta(seconds=60)
    created = _session(
        game,
        target,
        GameSession.STATE_CREATED,
        seed="created",
        ticket_hash="c" * 64,
        ticket_expires_at=expires_at,
        binding_nonce_hash="d" * 64,
    )
    active = _session(
        game,
        target,
        GameSession.STATE_ACTIVE,
        seed="active",
        binding_nonce_hash="d" * 64,
        credited_ms=30_000,
    )
    finished = _session(game, target, GameSession.STATE_FINISHED, seed="finished")
    expired = _session(game, target, GameSession.STATE_EXPIRED, seed="expired")
    other_active = _session(game, other, GameSession.STATE_ACTIVE, seed="other")

    response = _client(owner).post(reverse("crm:user_block", args=[target.id]))
    assert response.status_code == 302

    for session in (created, active):
        session.refresh_from_db()
        assert session.state == GameSession.STATE_ABORTED
        assert session.ticket_hash is None
        assert session.ticket_expires_at is None
        assert session.binding_nonce_hash == ""
    for session, expected in (
        (finished, GameSession.STATE_FINISHED),
        (expired, GameSession.STATE_EXPIRED),
        (other_active, GameSession.STATE_ACTIVE),
    ):
        session.refresh_from_db()
        assert session.state == expected
    assert GameResult.objects.count() == 0


@pytest.mark.django_db
def test_block_invalidates_ticket_heartbeat_and_result_and_unblock_is_noop() -> None:
    owner = _staff("owner", StaffRole.OWNER)
    target = _customer("target", "Target")
    game = _game("revoke_sdk_game")
    ticket = "launch-ticket-before-block"
    created = _session(
        game,
        target,
        GameSession.STATE_CREATED,
        seed="created",
        ticket_hash=hashlib.sha256(ticket.encode()).hexdigest(),
        ticket_expires_at=timezone.now() + timedelta(seconds=60),
    )
    active = _session(
        game,
        target,
        GameSession.STATE_ACTIVE,
        seed="active",
        binding_nonce_hash=hashlib.sha256(b"nonce").hexdigest(),
        credited_ms=30_000,
    )
    request = RequestFactory().post("/")
    request.user = target
    nonce = "n" * 32

    def expect_revoked() -> None:
        with pytest.raises(SessionError) as activation:
            activate_session(request, created.pk, ticket=ticket, binding_nonce=nonce)
        assert activation.value.code == "E_SESSION_EXPIRED"
        with pytest.raises(SessionError) as beat:
            heartbeat(request, active.pk)
        assert beat.value.code == "E_SESSION_EXPIRED"
        with pytest.raises(SessionError) as submission:
            submit_result(
                request,
                active.pk,
                idempotency_key="revoked-key",
                value=10,
                duration_ms=30_000,
            )
        assert submission.value.code == "E_SESSION_EXPIRED"

    client = _client(owner)
    assert client.post(reverse("crm:user_block", args=[target.id])).status_code == 302
    expect_revoked()
    assert not GameResult.objects.filter(session=active).exists()

    assert client.post(reverse("crm:user_unblock", args=[target.id])).status_code == 302
    expect_revoked()
    for session in (created, active):
        session.refresh_from_db()
        assert session.state == GameSession.STATE_ABORTED
        assert session.ticket_hash is None
        assert session.ticket_expires_at is None
    # Unblocking must not recreate sessions or reissue launch tickets.
    assert GameSession.objects.count() == 2
    assert not GameResult.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_submit_result_racing_block_cannot_persist(monkeypatch) -> None:
    owner = _staff("owner", StaffRole.OWNER)
    target = _customer("target", "Target")
    game = _game("revoke_race_game")
    session = _session(
        game,
        target,
        GameSession.STATE_ACTIVE,
        seed="race",
        credited_ms=30_000,
    )
    request = RequestFactory().post("/")
    request.user = target

    reached_audit = threading.Event()
    release_block = threading.Event()
    submit_started = threading.Event()
    outcomes: list[str] = []
    outcomes_lock = threading.Lock()
    real_record_audit = crm_users.record_audit

    def blocking_audit(**kwargs: object) -> AdminAuditLog:
        reached_audit.set()
        assert release_block.wait(timeout=10)
        return real_record_audit(**kwargs)

    monkeypatch.setattr(crm_users, "record_audit", blocking_audit)

    def block_worker() -> None:
        try:
            result = crm_users.block_user(actor=owner, target_id=target.id)
            assert result.ok
        finally:
            connections.close_all()

    def submit_worker() -> None:
        try:
            submit_started.set()
            submit_result(
                request,
                session.pk,
                idempotency_key="race-key",
                value=10,
                duration_ms=30_000,
            )
        except SessionError as exc:
            with outcomes_lock:
                outcomes.append(exc.code)
        except Exception as exc:  # noqa: BLE001 - surface unexpected race failures
            with outcomes_lock:
                outcomes.append(type(exc).__name__)
        else:
            with outcomes_lock:
                outcomes.append("ok")
        finally:
            connections.close_all()

    block_thread = threading.Thread(target=block_worker)
    block_thread.start()
    assert reached_audit.wait(timeout=10), "block never reached its audit step"

    submit_thread = threading.Thread(target=submit_worker)
    submit_thread.start()
    assert submit_started.wait(timeout=10), "submit never started"
    release_block.set()

    block_thread.join(timeout=30)
    submit_thread.join(timeout=30)
    assert not block_thread.is_alive()
    assert not submit_thread.is_alive()

    assert outcomes == ["E_SESSION_EXPIRED"]
    assert not GameResult.objects.filter(session=session).exists()
    session.refresh_from_db()
    assert session.state == GameSession.STATE_ABORTED
    target.refresh_from_db()
    assert target.is_active is False


@pytest.mark.django_db(transaction=True)
def test_concurrent_submit_result_racing_anonymise_cannot_deadlock(monkeypatch) -> None:
    """R-051: submit_result and anonymize_user share the User -> Session order.

    Anonymisation is parked after it took the User row lock and before it
    locks the sessions. ``submit_result`` must wait on that same account lock
    instead of locking the session first (which would deadlock on the result
    insert's ``FOR KEY SHARE`` on the User row).
    """
    target = _customer("target", "Target")
    game = _game("result_anonymise_race_game")
    session = _session(game, target, GameSession.STATE_ACTIVE, seed="race", credited_ms=30_000)
    request = RequestFactory().post("/")
    request.user = target

    reached_user_lock = threading.Event()
    release_anonymise = threading.Event()
    reached_session = threading.Event()
    outcomes: list[str] = []
    outcomes_lock = threading.Lock()
    real_reserve_nickname = profile_service.reserve_nickname
    real_subject = results_service._subject

    def blocking_reserve_nickname(*args: object, **kwargs: object) -> object:
        reached_user_lock.set()
        assert release_anonymise.wait(timeout=10)
        return real_reserve_nickname(*args, **kwargs)

    def signalling_subject(request_, session_):  # type: ignore[no-untyped-def]
        # Called only once the session row is locked by submit_result.
        reached_session.set()
        return real_subject(request_, session_)

    monkeypatch.setattr(profile_service, "reserve_nickname", blocking_reserve_nickname)
    monkeypatch.setattr(results_service, "_subject", signalling_subject)

    def anonymise_worker() -> None:
        try:
            anonymize_user(target)
        finally:
            connections.close_all()

    def submit_worker() -> None:
        try:
            submit_result(
                request,
                session.pk,
                idempotency_key="race-key",
                value=10,
                duration_ms=30_000,
            )
        except SessionError as exc:
            with outcomes_lock:
                outcomes.append(exc.code)
        except Exception as exc:  # noqa: BLE001 - surface unexpected race failures
            with outcomes_lock:
                outcomes.append(type(exc).__name__)
        else:
            with outcomes_lock:
                outcomes.append("ok")
        finally:
            connections.close_all()

    anonymise_thread = threading.Thread(target=anonymise_worker)
    anonymise_thread.start()
    assert reached_user_lock.wait(timeout=10), "anonymise never locked the account"

    submit_thread = threading.Thread(target=submit_worker)
    submit_thread.start()
    # With User -> GameSession ordering submit parks on the account lock and
    # never reaches the session while anonymisation holds the User row.
    reached_session.wait(timeout=1.0)
    release_anonymise.set()

    anonymise_thread.join(timeout=30)
    submit_thread.join(timeout=30)
    assert not anonymise_thread.is_alive()
    assert not submit_thread.is_alive()

    assert outcomes == ["E_OWNERSHIP"]
    assert not GameResult.objects.filter(session=session).exists()
    assert not LeaderboardEntry.objects.filter(user=target).exists()
    session.refresh_from_db()
    assert session.subject_type == GameSession.SUBJECT_DELETED


@pytest.mark.django_db(transaction=True)
def test_concurrent_submit_result_racing_block_revoke_cannot_deadlock(monkeypatch) -> None:
    """R-051: submit_result waits for the block's account lock, no inversion."""
    owner = _staff("owner", StaffRole.OWNER)
    target = _customer("target", "Target")
    game = _game("result_block_race_game")
    session = _session(game, target, GameSession.STATE_ACTIVE, seed="race", credited_ms=30_000)
    request = RequestFactory().post("/")
    request.user = target

    reached_user_lock = threading.Event()
    release_block = threading.Event()
    reached_session = threading.Event()
    outcomes: list[str] = []
    outcomes_lock = threading.Lock()
    real_revoke = crm_users._revoke_open_sessions
    real_subject = results_service._subject

    def blocking_revoke(user: User) -> int:
        reached_user_lock.set()
        assert release_block.wait(timeout=10)
        return real_revoke(user)

    def signalling_subject(request_, session_):  # type: ignore[no-untyped-def]
        reached_session.set()
        return real_subject(request_, session_)

    monkeypatch.setattr(crm_users, "_revoke_open_sessions", blocking_revoke)
    monkeypatch.setattr(results_service, "_subject", signalling_subject)

    def block_worker() -> None:
        try:
            result = crm_users.block_user(actor=owner, target_id=target.id)
            assert result.ok
        finally:
            connections.close_all()

    def submit_worker() -> None:
        try:
            submit_result(
                request,
                session.pk,
                idempotency_key="race-key",
                value=10,
                duration_ms=30_000,
            )
        except SessionError as exc:
            with outcomes_lock:
                outcomes.append(exc.code)
        except Exception as exc:  # noqa: BLE001 - surface unexpected race failures
            with outcomes_lock:
                outcomes.append(type(exc).__name__)
        else:
            with outcomes_lock:
                outcomes.append("ok")
        finally:
            connections.close_all()

    block_thread = threading.Thread(target=block_worker)
    block_thread.start()
    assert reached_user_lock.wait(timeout=10), "block never locked the account"

    submit_thread = threading.Thread(target=submit_worker)
    submit_thread.start()
    # The submit must be blocked on the User row, not holding the session one.
    reached_session.wait(timeout=1.0)
    release_block.set()

    block_thread.join(timeout=30)
    submit_thread.join(timeout=30)
    assert not block_thread.is_alive()
    assert not submit_thread.is_alive()

    assert outcomes == ["E_SESSION_EXPIRED"]
    assert not GameResult.objects.filter(session=session).exists()
    session.refresh_from_db()
    assert session.state == GameSession.STATE_ABORTED
    target.refresh_from_db()
    assert target.is_active is False


def _storage_row(game: Game, user: User) -> None:
    GameStorage.objects.create(
        game=game,
        subject_type=GameStorage.SUBJECT_USER,
        user=user,
        data={"before": True},
        revision=1,
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("existing", [False, True])
def test_concurrent_put_storage_racing_anonymise_does_not_restore_data(
    monkeypatch, existing: bool
) -> None:
    """R-056: put_storage waits for anonymise's account lock before writing."""
    target = _customer("target", "Target")
    game = _game("storage_anonymise_race_game")
    _session(game, target, GameSession.STATE_ACTIVE, seed="race", credited_ms=30_000)
    if existing:
        _storage_row(game, target)
    request = RequestFactory().post("/")
    request.user = target

    reached_user_lock = threading.Event()
    release_anonymise = threading.Event()
    reached_account_lock = threading.Event()
    outcomes: list[str] = []
    outcomes_lock = threading.Lock()
    real_reserve_nickname = profile_service.reserve_nickname
    real_lock_account = storage_service._lock_account

    def blocking_reserve_nickname(*args: object, **kwargs: object) -> object:
        reached_user_lock.set()
        assert release_anonymise.wait(timeout=10)
        return real_reserve_nickname(*args, **kwargs)

    def signalling_lock_account(subject_type: str, subject_id):  # type: ignore[no-untyped-def]
        reached_account_lock.set()
        return real_lock_account(subject_type, subject_id)

    monkeypatch.setattr(profile_service, "reserve_nickname", blocking_reserve_nickname)
    monkeypatch.setattr(storage_service, "_lock_account", signalling_lock_account)

    def anonymise_worker() -> None:
        try:
            anonymize_user(target)
        finally:
            connections.close_all()

    def storage_worker() -> None:
        try:
            put_storage(
                request,
                game.technical_id,
                data={"after": True},
                if_match='"1"' if existing else "*",
            )
        except SessionError as exc:
            with outcomes_lock:
                outcomes.append(exc.code)
        except Exception as exc:  # noqa: BLE001 - surface unexpected race failures
            with outcomes_lock:
                outcomes.append(type(exc).__name__)
        else:
            with outcomes_lock:
                outcomes.append("ok")
        finally:
            connections.close_all()

    anonymise_thread = threading.Thread(target=anonymise_worker)
    anonymise_thread.start()
    assert reached_user_lock.wait(timeout=10), "anonymise never locked the account"

    storage_thread = threading.Thread(target=storage_worker)
    storage_thread.start()
    # put_storage must park on the User row, never touching storage while the
    # cleanup pass still owns the account.
    assert reached_account_lock.wait(timeout=10), "put_storage never took the account lock"
    release_anonymise.set()

    anonymise_thread.join(timeout=30)
    storage_thread.join(timeout=30)
    assert not anonymise_thread.is_alive()
    assert not storage_thread.is_alive()

    assert outcomes == ["E_SESSION_INVALID"]
    assert not GameStorage.objects.filter(user=target).exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("existing", [False, True])
def test_concurrent_put_storage_racing_block_cannot_write(monkeypatch, existing: bool) -> None:
    """R-056: a blocked account cannot create or update storage concurrently."""
    owner = _staff("owner", StaffRole.OWNER)
    target = _customer("target", "Target")
    game = _game("storage_block_race_game")
    _session(game, target, GameSession.STATE_ACTIVE, seed="race", credited_ms=30_000)
    if existing:
        _storage_row(game, target)
    request = RequestFactory().post("/")
    request.user = target

    reached_block = threading.Event()
    release_block = threading.Event()
    reached_account_lock = threading.Event()
    outcomes: list[str] = []
    outcomes_lock = threading.Lock()
    real_revoke = crm_users._revoke_open_sessions
    real_lock_account = storage_service._lock_account

    def blocking_revoke(user: User) -> int:
        reached_block.set()
        assert release_block.wait(timeout=10)
        return real_revoke(user)

    def signalling_lock_account(subject_type: str, subject_id):  # type: ignore[no-untyped-def]
        reached_account_lock.set()
        return real_lock_account(subject_type, subject_id)

    monkeypatch.setattr(crm_users, "_revoke_open_sessions", blocking_revoke)
    monkeypatch.setattr(storage_service, "_lock_account", signalling_lock_account)

    def block_worker() -> None:
        try:
            result = crm_users.block_user(actor=owner, target_id=target.id)
            assert result.ok
        finally:
            connections.close_all()

    def storage_worker() -> None:
        try:
            put_storage(
                request,
                game.technical_id,
                data={"after": True},
                if_match='"1"' if existing else "*",
            )
        except SessionError as exc:
            with outcomes_lock:
                outcomes.append(exc.code)
        except Exception as exc:  # noqa: BLE001 - surface unexpected race failures
            with outcomes_lock:
                outcomes.append(type(exc).__name__)
        else:
            with outcomes_lock:
                outcomes.append("ok")
        finally:
            connections.close_all()

    block_thread = threading.Thread(target=block_worker)
    block_thread.start()
    assert reached_block.wait(timeout=10), "block never reached its session revoke step"

    storage_thread = threading.Thread(target=storage_worker)
    storage_thread.start()
    assert reached_account_lock.wait(timeout=10), "put_storage never took the account lock"
    release_block.set()

    block_thread.join(timeout=30)
    storage_thread.join(timeout=30)
    assert not block_thread.is_alive()
    assert not storage_thread.is_alive()

    assert outcomes == ["E_SESSION_INVALID"]
    target.refresh_from_db()
    assert target.is_active is False
    rows = GameStorage.objects.filter(user=target)
    if existing:
        # Blocking keeps storage, but the racing write must not bump it.
        row = rows.get()
        assert row.revision == 1
        assert row.data == {"before": True}
    else:
        assert not rows.exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_heartbeat_racing_anonymise_cannot_deadlock(monkeypatch) -> None:
    """R-051: heartbeat locks the account before the session it credits."""
    target = _customer("target", "Target")
    game = _game("heartbeat_anonymise_race_game")
    session = _session(
        game,
        target,
        GameSession.STATE_ACTIVE,
        seed="race",
        credited_ms=0,
        last_heartbeat_at=timezone.now() - timedelta(seconds=30),
    )
    request = RequestFactory().post("/")
    request.user = target

    reached_user_lock = threading.Event()
    release_anonymise = threading.Event()
    reached_account_lock = threading.Event()
    outcomes: list[str] = []
    outcomes_lock = threading.Lock()
    real_reserve_nickname = profile_service.reserve_nickname
    real_lock_account = sessions_service._lock_account

    def blocking_reserve_nickname(*args: object, **kwargs: object) -> object:
        reached_user_lock.set()
        assert release_anonymise.wait(timeout=10)
        return real_reserve_nickname(*args, **kwargs)

    def signalling_lock_account(subject_type: str, subject_id):  # type: ignore[no-untyped-def]
        reached_account_lock.set()
        return real_lock_account(subject_type, subject_id)

    monkeypatch.setattr(profile_service, "reserve_nickname", blocking_reserve_nickname)
    monkeypatch.setattr(sessions_service, "_lock_account", signalling_lock_account)

    def anonymise_worker() -> None:
        try:
            anonymize_user(target)
        finally:
            connections.close_all()

    def heartbeat_worker() -> None:
        try:
            heartbeat(request, session.pk)
        except SessionError as exc:
            with outcomes_lock:
                outcomes.append(exc.code)
        except Exception as exc:  # noqa: BLE001 - surface unexpected race failures
            with outcomes_lock:
                outcomes.append(type(exc).__name__)
        else:
            with outcomes_lock:
                outcomes.append("ok")
        finally:
            connections.close_all()

    anonymise_thread = threading.Thread(target=anonymise_worker)
    anonymise_thread.start()
    assert reached_user_lock.wait(timeout=10), "anonymise never locked the account"

    heartbeat_thread = threading.Thread(target=heartbeat_worker)
    heartbeat_thread.start()
    # The heartbeat takes the account lock before the session row; it never
    # reaches the playtime insert while anonymisation holds the User row.
    reached_account_lock.wait(timeout=1.0)
    release_anonymise.set()

    anonymise_thread.join(timeout=30)
    heartbeat_thread.join(timeout=30)
    assert not anonymise_thread.is_alive()
    assert not heartbeat_thread.is_alive()

    assert outcomes == ["E_OWNERSHIP"]
    assert not UserGamePlaytime.objects.filter(user=target).exists()
    session.refresh_from_db()
    assert session.subject_type == GameSession.SUBJECT_DELETED


def _open_session_count(user: User) -> int:
    return GameSession.objects.filter(
        subject_type=GameSession.SUBJECT_USER,
        subject_id=user.id,
        state__in=(GameSession.STATE_CREATED, GameSession.STATE_ACTIVE),
    ).count()


@pytest.mark.django_db(transaction=True)
def test_concurrent_create_session_racing_block_creates_no_open_session(monkeypatch) -> None:
    """R-049 / ARCADE-SESSION-RACE-001: a blocked account cannot gain a session."""
    owner = _staff("owner", StaffRole.OWNER)
    target = _customer("target", "Target")
    game = _game("session_block_race_game")
    request = RequestFactory().post("/")
    request.user = target
    response = HttpResponse()

    reached_audit = threading.Event()
    release_block = threading.Event()
    create_started = threading.Event()
    outcomes: list[str] = []
    outcomes_lock = threading.Lock()
    real_record_audit = crm_users.record_audit

    def blocking_audit(**kwargs: object) -> AdminAuditLog:
        reached_audit.set()
        assert release_block.wait(timeout=10)
        return real_record_audit(**kwargs)

    monkeypatch.setattr(crm_users, "record_audit", blocking_audit)

    def block_worker() -> None:
        try:
            result = crm_users.block_user(actor=owner, target_id=target.id)
            assert result.ok
        finally:
            connections.close_all()

    def create_worker() -> None:
        try:
            create_started.set()
            create_session(request, response, game_id=game.technical_id)
        except SessionError as exc:
            with outcomes_lock:
                outcomes.append(exc.code)
        except Exception as exc:  # noqa: BLE001 - surface unexpected race failures
            with outcomes_lock:
                outcomes.append(type(exc).__name__)
        else:
            with outcomes_lock:
                outcomes.append("ok")
        finally:
            connections.close_all()

    block_thread = threading.Thread(target=block_worker)
    block_thread.start()
    assert reached_audit.wait(timeout=10), "block never reached its audit step"
    create_thread = threading.Thread(target=create_worker)
    create_thread.start()
    assert create_started.wait(timeout=10), "create_session never started"
    # Let the block commit while create_session is in flight.
    release_block.set()

    block_thread.join(timeout=30)
    create_thread.join(timeout=30)
    assert not block_thread.is_alive()
    assert not create_thread.is_alive()

    assert outcomes == ["E_SESSION_INVALID"]
    assert _open_session_count(target) == 0
    target.refresh_from_db()
    assert target.is_active is False


@pytest.mark.django_db(transaction=True)
def test_concurrent_create_session_racing_anonymise_creates_no_open_session(monkeypatch) -> None:
    """R-049 / ARCADE-SESSION-RACE-001: an anonymised account cannot gain a session."""
    target = _customer("target", "Target")
    game = _game("session_delete_race_game")
    request = RequestFactory().post("/")
    request.user = target
    response = HttpResponse()

    reached_anonymise = threading.Event()
    release_anonymise = threading.Event()
    create_started = threading.Event()
    outcomes: list[str] = []
    outcomes_lock = threading.Lock()
    real_anonymize_results = results_service.anonymize_user_results

    def blocking_anonymize_results(user: User) -> None:
        reached_anonymise.set()
        assert release_anonymise.wait(timeout=10)
        real_anonymize_results(user)

    monkeypatch.setattr(results_service, "anonymize_user_results", blocking_anonymize_results)

    def anonymise_worker() -> None:
        try:
            anonymize_user(target)
        finally:
            connections.close_all()

    def create_worker() -> None:
        try:
            create_started.set()
            create_session(request, response, game_id=game.technical_id)
        except SessionError as exc:
            with outcomes_lock:
                outcomes.append(exc.code)
        except Exception as exc:  # noqa: BLE001 - surface unexpected race failures
            with outcomes_lock:
                outcomes.append(type(exc).__name__)
        else:
            with outcomes_lock:
                outcomes.append("ok")
        finally:
            connections.close_all()

    anonymise_thread = threading.Thread(target=anonymise_worker)
    anonymise_thread.start()
    assert reached_anonymise.wait(timeout=10), "anonymise never reached the result pass"
    create_thread = threading.Thread(target=create_worker)
    create_thread.start()
    assert create_started.wait(timeout=10), "create_session never started"
    # Let anonymisation commit while create_session is in flight.
    release_anonymise.set()

    anonymise_thread.join(timeout=30)
    create_thread.join(timeout=30)
    assert not anonymise_thread.is_alive()
    assert not create_thread.is_alive()

    assert outcomes == ["E_SESSION_INVALID"]
    assert _open_session_count(target) == 0
    target.refresh_from_db()
    assert target.is_active is False


@pytest.mark.django_db
def test_delete_requests_window_then_anonymizes_when_due_and_is_idempotent() -> None:
    owner = _staff("owner", StaffRole.OWNER)
    target = _customer("target", "Target", email="target@example.com")
    client = _client(owner)

    not_elevated = client.post(reverse("crm:user_delete", args=[target.id]))
    assert not_elevated.status_code == 302
    assert UserProfile.objects.get(user=target).deletion_requested_at is None

    _step_up(client)
    no_confirm = client.post(reverse("crm:user_delete", args=[target.id]))
    assert no_confirm.status_code == 302
    assert UserProfile.objects.get(user=target).deletion_requested_at is None

    scheduled = client.post(reverse("crm:user_delete", args=[target.id]), {"confirm_delete": "yes"})
    assert scheduled.status_code == 302
    target.refresh_from_db()
    profile = UserProfile.objects.get(user=target)
    assert profile.deletion_requested_at is not None
    assert AdminAuditLog.objects.filter(
        action=AdminAuditLog.ACTION_USER_DELETION_REQUESTED, object_id=target.id
    ).exists()

    # Inside the cancellation window nothing is purged.
    again = client.post(reverse("crm:user_delete", args=[target.id]), {"confirm_delete": "yes"})
    assert again.status_code == 302
    assert UserProfile.objects.filter(user=target).exists()

    UserProfile.objects.filter(user=target).update(
        deletion_requested_at=timezone.now() - timedelta(days=8)
    )
    deleted = client.post(reverse("crm:user_delete", args=[target.id]), {"confirm_delete": "yes"})
    assert deleted.status_code == 302
    target.refresh_from_db()
    assert target.is_active is False
    assert target.login.startswith("deleted-")
    assert not UserProfile.objects.filter(user=target).exists()
    assert not EmailAddress.objects.filter(user=target).exists()
    assert AdminAuditLog.objects.filter(
        action=AdminAuditLog.ACTION_USER_DELETED, object_id=target.id
    ).exists()

    repeat = client.post(reverse("crm:user_delete", args=[target.id]), {"confirm_delete": "yes"})
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

    client = _client(owner)
    blocked = client.get(reverse("crm:user_export", args=[target.id]))
    assert blocked.status_code == 302
    assert reverse("crm:step_up") in blocked["Location"]

    _step_up(client)
    crm_export = client.get(reverse("crm:user_export", args=[target.id]))
    assert crm_export.status_code == 200
    assert "attachment" in crm_export["Content-Disposition"]
    assert "breaktime-account.json" in crm_export["Content-Disposition"]
    assert crm_export["X-Content-Type-Options"] == "nosniff"

    assert json.loads(crm_export.content) == json.loads(account_export.content)


@pytest.mark.django_db
def test_staff_and_owner_targets_are_not_addressable_as_customers() -> None:
    owner = _staff("owner", StaffRole.OWNER)
    other_owner = _staff("other_owner", StaffRole.OWNER)
    UserProfile.objects.create(
        user=other_owner, nickname="OtherOwner", nickname_skeleton="otherowner"
    )
    client = _client(owner)
    _step_up(client)

    assert client.get(reverse("crm:user_detail", args=[other_owner.id])).status_code == 404
    assert client.get(reverse("crm:user_export", args=[other_owner.id])).status_code == 404
    assert client.post(reverse("crm:user_block", args=[other_owner.id])).status_code == 302
    other_owner.refresh_from_db()
    assert other_owner.is_active is True
    assert (
        client.post(
            reverse("crm:user_delete", args=[other_owner.id]),
            {"confirm_delete": "yes"},
        ).status_code
        == 302
    )
    assert UserProfile.objects.filter(user=other_owner).exists()
    assert not AdminAuditLog.objects.filter(object_id=other_owner.id).exists()


@pytest.mark.django_db
def test_block_on_anonymized_tombstone_does_not_reactivate() -> None:
    owner = _staff("owner", StaffRole.OWNER)
    target = _customer("target", "Target")
    client = _client(owner)

    UserProfile.objects.filter(user=target).delete()
    User.objects.filter(pk=target.pk).update(is_active=False)
    target.refresh_from_db()
    response = client.post(reverse("crm:user_unblock", args=[target.id]))
    assert response.status_code == 302
    target.refresh_from_db()
    assert target.is_active is False


@pytest.mark.django_db
def test_detail_shows_only_current_leaderboard_epoch() -> None:
    owner = _staff("owner", StaffRole.OWNER)
    target = _customer("target", "Target")
    game = _game("epoch_game")
    now = timezone.now()
    old_session = GameSession.objects.create(
        game=game,
        game_version=game.current_version,
        subject_type=GameSession.SUBJECT_USER,
        subject_id=target.id,
        mode=GameSession.MODE_USER,
        state=GameSession.STATE_FINISHED,
        seed="old-epoch-seed",
        max_session_seconds=1800,
        activated_at=now - timedelta(seconds=30),
        last_heartbeat_at=now,
        finished_at=now,
    )
    old_result = GameResult.objects.create(
        session=old_session,
        game=game,
        game_version=game.current_version,
        subject_type=GameResult.SUBJECT_USER,
        user=target,
        epoch=game.leaderboard_epoch - 1,
        value=5,
        unit=game.score_unit,
        duration_ms=30_000,
        idempotency_key="old-epoch-key",
    )
    LeaderboardEntry.objects.create(
        game=game,
        epoch=old_result.epoch,
        user=target,
        best_result=old_result,
        value=5,
        achieved_at=old_result.created_at,
        trust_level=GameResult.TRUST_CLIENT_REPORTED,
    )
    _result_and_entry(game, target, value=10)

    client = _client(owner)
    response = client.get(reverse("crm:user_detail", args=[target.id]))
    assert response.status_code == 200
    epochs = {entry.epoch for entry in response.context["leaderboard_entries"]}
    assert epochs == {game.leaderboard_epoch}


@pytest.mark.django_db
def test_mutations_reject_missing_csrf_token() -> None:
    owner = _staff("owner", StaffRole.OWNER)
    target = _customer("target", "Target")
    client = Client(enforce_csrf_checks=True)
    client.force_login(owner)
    session = client.session
    session["ba_2fa_verified"] = True
    session.save()
    _step_up(client)

    response = client.post(reverse("crm:user_block", args=[target.id]))
    assert response.status_code == 403
    response = client.post(reverse("crm:user_unblock", args=[target.id]))
    assert response.status_code == 403
    response = client.post(reverse("crm:user_delete", args=[target.id]), {"confirm_delete": "yes"})
    assert response.status_code == 403
