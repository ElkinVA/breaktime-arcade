from __future__ import annotations

import json
import re
import threading
import time
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.db import connections
from django.test import Client, RequestFactory, override_settings
from django.utils import timezone

from apps.accounts.models import AnonymousIdentity, User
from apps.accounts.services.anonymous import COOKIE_NAME
from apps.catalog.models import Game, GameVersion, Genre
from apps.gameplay.models import GameSession
from apps.gameplay.services.sessions import SessionError, activate_session, heartbeat

LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}
API = "/api/v1/sessions"
NONCE = "n" * 32


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


def _client(user: User | None = None) -> tuple[Client, str]:
    cache.clear()
    client = Client(enforce_csrf_checks=True)
    page = client.get("/en/auth/login/")
    assert page.status_code == 200
    match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.content.decode())
    assert match is not None
    if user is not None:
        client.force_login(user)
    return client, match.group(1)


def _game(*, technical_id: str = "session_game", published: bool = True) -> Game:
    genre = Genre.objects.create(code=f"genre_{technical_id}")
    game = Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=f"slug-{technical_id}",
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED if published else Game.STATUS_DRAFT,
        published_at=timezone.now() if published else None,
        max_session_seconds=1800,
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


def _create(client: Client, csrf: str, game: Game, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {"game_id": game.technical_id}
    payload.update(extra)
    response = client.post(
        API,
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 201, response.content
    return response.json()


def _activate(
    client: Client,
    csrf: str,
    session_id: str,
    ticket: str,
    *,
    nonce: str = NONCE,
) -> object:
    return client.post(
        f"{API}/{session_id}/activate",
        data=json.dumps({"ticket": ticket, "binding_nonce": nonce}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )


def _service_request(token: str):
    request = RequestFactory().post("/")
    request.user = AnonymousUser()
    request.COOKIES[COOKIE_NAME] = token
    return request


def _run_parallel(workers: list) -> list[str]:
    outcomes: list[str] = []
    lock = threading.Lock()

    def wrap(worker) -> None:
        try:
            worker()
        except SessionError as exc:
            with lock:
                outcomes.append(exc.code)
        else:
            with lock:
                outcomes.append("ok")
        finally:
            connections.close_all()

    threads = [threading.Thread(target=wrap, args=(worker,)) for worker in workers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not any(thread.is_alive() for thread in threads)
    return outcomes


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_guest_create_requires_csrf_and_returns_exact_ticket_response() -> None:
    game = _game()
    client, csrf = _client()

    without_csrf = client.post(
        API,
        data=json.dumps({"game_id": game.technical_id}),
        content_type="application/json",
    )
    assert without_csrf.status_code == 403

    result = _create(client, csrf, game)
    assert set(result) == {"session_id", "ticket", "expires_at"}
    session = GameSession.objects.get(pk=result["session_id"])
    assert session.state == GameSession.STATE_CREATED
    assert session.subject_type == GameSession.SUBJECT_ANON
    assert session.mode == GameSession.MODE_GUEST
    assert session.ticket_hash != result["ticket"]
    assert COOKIE_NAME in client.cookies


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_guest_activate_builds_context_and_rejects_ticket_reuse() -> None:
    game = _game(technical_id="activate_game")
    client, csrf = _client()
    result = _create(client, csrf, game)

    activated = _activate(client, csrf, str(result["session_id"]), str(result["ticket"]))
    assert activated.status_code == 200, activated.content
    context = activated.json()["context"]
    assert context["sessionId"] == result["session_id"]
    assert context["gameId"] == game.technical_id
    assert context["gameVersion"] == "1.0.0"
    assert context["mode"] == "guest"
    assert context["trustLevel"] == "client_reported"
    assert context["limits"]["maxSessionSeconds"] == 1800
    assert context["language"] == "en"
    assert context["fallbackLanguage"] == game.default_language
    assert context["strings"] == {}
    assert context["score"]["type"] == game.score_type
    assert context["score"]["maxDeltaMs"] == 45_000
    assert context["limits"]["heartbeatIntervalSeconds"] == 30
    session = GameSession.objects.get(pk=result["session_id"])
    assert context["seed"] == session.seed
    assert session.state == GameSession.STATE_ACTIVE
    assert session.ticket_hash is None

    reused = _activate(client, csrf, str(result["session_id"]), str(result["ticket"]))
    assert reused.status_code == 400
    assert reused.json()["code"] == "E_TICKET_INVALID"


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_activation_rejects_wrong_ticket_and_expired_window() -> None:
    game = _game(technical_id="expired_game")
    client, csrf = _client()
    result = _create(client, csrf, game)
    session = GameSession.objects.get(pk=result["session_id"])

    wrong = _activate(client, csrf, str(session.id), "x" * 40)
    assert wrong.status_code == 400
    assert wrong.json()["code"] == "E_TICKET_INVALID"

    GameSession.objects.filter(pk=session.pk).update(
        created_at=timezone.now() - timedelta(seconds=301)
    )
    expired_window = _activate(client, csrf, str(session.id), str(result["ticket"]))
    assert expired_window.status_code == 410
    assert expired_window.json()["code"] == "E_SESSION_EXPIRED"
    session.refresh_from_db()
    assert session.state == GameSession.STATE_EXPIRED


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_expired_ticket_is_session_expired() -> None:
    game = _game(technical_id="ticket_game")
    client, csrf = _client()
    result = _create(client, csrf, game)
    GameSession.objects.filter(pk=result["session_id"]).update(
        ticket_expires_at=timezone.now() - timedelta(seconds=1)
    )
    response = _activate(client, csrf, str(result["session_id"]), str(result["ticket"]))
    assert response.status_code == 410
    assert response.json()["code"] == "E_SESSION_EXPIRED"


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_other_subject_cannot_activate() -> None:
    game = _game(technical_id="owner_game")
    owner, csrf = _client()
    result = _create(owner, csrf, game)
    stranger, stranger_csrf = _client()
    response = _activate(stranger, stranger_csrf, str(result["session_id"]), str(result["ticket"]))
    assert response.status_code == 403
    assert response.json()["code"] == "E_OWNERSHIP"


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_active_session_limit_is_three() -> None:
    game = _game(technical_id="limit_game")
    client, csrf = _client()
    for _ in range(3):
        result = _create(client, csrf, game)
        activated = _activate(client, csrf, str(result["session_id"]), str(result["ticket"]))
        assert activated.status_code == 200
    fourth = client.post(
        API,
        data=json.dumps({"game_id": game.technical_id}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert fourth.status_code == 429
    assert fourth.json()["code"] == "E_RATE_LIMIT"


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_user_session_uses_user_mode() -> None:
    game = _game(technical_id="user_game")
    user = User.objects.create_user(login="alice", password="correct horse battery staple")
    client, csrf = _client(user)
    result = _create(client, csrf, game)
    session = GameSession.objects.get(pk=result["session_id"])
    assert session.subject_type == GameSession.SUBJECT_USER
    assert session.subject_id == user.id
    assert session.mode == GameSession.MODE_USER


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_draft_game_is_not_available() -> None:
    game = _game(technical_id="draft_session_game", published=False)
    client, csrf = _client()
    response = client.post(
        API,
        data=json.dumps({"game_id": game.technical_id}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 404
    assert response.json()["code"] == "E_SESSION_INVALID"


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_heartbeat_clamps_delta_and_caps_credited_time() -> None:
    game = _game(technical_id="heartbeat_game")
    client, csrf = _client()
    result = _create(client, csrf, game)
    session_id = result["session_id"]
    activated = _activate(client, csrf, str(session_id), str(result["ticket"]))
    assert activated.status_code == 200
    session = GameSession.objects.get(pk=session_id)

    base = timezone.now() - timedelta(seconds=100)
    GameSession.objects.filter(pk=session.pk).update(
        activated_at=base,
        last_heartbeat_at=base,
        credited_ms=0,
        max_session_seconds=1800,
    )
    request = RequestFactory().post("/")
    request.user = AnonymousUser()
    request.COOKIES[COOKIE_NAME] = client.cookies[COOKIE_NAME].value

    heartbeat(request, session.pk, now=base + timedelta(seconds=10))
    session.refresh_from_db()
    assert session.credited_ms == 10_000

    heartbeat(request, session.pk, now=base + timedelta(seconds=100))
    session.refresh_from_db()
    assert session.credited_ms == 55_000

    GameSession.objects.filter(pk=session.pk).update(
        credited_ms=1_790_000,
        last_heartbeat_at=base + timedelta(seconds=110),
    )
    heartbeat(request, session.pk, now=base + timedelta(seconds=120))
    session.refresh_from_db()
    assert session.credited_ms == 1_800_000


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_heartbeat_expires_idle_and_max_duration() -> None:
    game = _game(technical_id="idle_game")
    client, csrf = _client()
    result = _create(client, csrf, game)
    _activate(client, csrf, str(result["session_id"]), str(result["ticket"]))
    session = GameSession.objects.get(pk=result["session_id"])
    request = RequestFactory().post("/")
    request.user = AnonymousUser()
    request.COOKIES[COOKIE_NAME] = client.cookies[COOKIE_NAME].value
    now = timezone.now()

    GameSession.objects.filter(pk=session.pk).update(
        activated_at=now - timedelta(seconds=1801),
        last_heartbeat_at=now - timedelta(seconds=1801),
        max_session_seconds=7200,
    )
    with pytest.raises(SessionError) as idle:
        heartbeat(request, session.pk, now=now)
    assert idle.value.code == "E_SESSION_EXPIRED"

    GameSession.objects.filter(pk=session.pk).update(
        state=GameSession.STATE_ACTIVE,
        activated_at=now - timedelta(seconds=1801),
        last_heartbeat_at=now - timedelta(seconds=10),
        max_session_seconds=1800,
    )
    with pytest.raises(SessionError) as max_duration:
        heartbeat(request, session.pk, now=now)
    assert max_duration.value.code == "E_SESSION_EXPIRED"


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_activation_cannot_take_more_than_three_active_sessions() -> None:
    game = _game(technical_id="activation_limit_game")
    client, csrf = _client()
    for _ in range(2):
        done = _create(client, csrf, game)
        assert (
            _activate(client, csrf, str(done["session_id"]), str(done["ticket"])).status_code == 200
        )
    first = _create(client, csrf, game)
    second = _create(client, csrf, game)
    assert (
        _activate(client, csrf, str(first["session_id"]), str(first["ticket"])).status_code == 200
    )
    denied = _activate(client, csrf, str(second["session_id"]), str(second["ticket"]))
    assert denied.status_code == 429
    assert denied.json()["code"] == "E_RATE_LIMIT"
    assert GameSession.objects.filter(game=game, state=GameSession.STATE_ACTIVE).count() == 3


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_invalid_body_returns_structured_error() -> None:
    client, csrf = _client()
    response = client.post(
        API,
        data=json.dumps({}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 400
    assert response.json() == {"code": "E_INVALID_REQUEST", "message": "Invalid request"}


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_published_game_without_current_version_is_unavailable() -> None:
    game = _game(technical_id="no_version_game")
    game.current_version = None
    game.save(update_fields=["current_version"])
    client, csrf = _client()
    response = client.post(
        API,
        data=json.dumps({"game_id": game.technical_id}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 404
    assert response.json()["code"] == "E_SESSION_INVALID"


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_session_duration_is_clamped_to_global_maximum() -> None:
    game = _game(technical_id="clamp_game")
    game.max_session_seconds = 9999
    game.save(update_fields=["max_session_seconds"])
    client, csrf = _client()
    result = _create(client, csrf, game)
    session = GameSession.objects.get(pk=result["session_id"])
    assert session.max_session_seconds == 7200


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_garbage_guest_cookie_is_treated_as_no_identity() -> None:
    game = _game(technical_id="garbage_cookie_game")
    client, csrf = _client()
    client.cookies[COOKIE_NAME] = "not-a-signed-token"
    rejected = _activate(client, csrf, str(uuid4()), "t" * 32)
    assert rejected.status_code == 403
    assert rejected.json()["code"] == "E_OWNERSHIP"
    result = _create(client, csrf, game)
    assert GameSession.objects.filter(pk=result["session_id"]).exists()
    assert COOKIE_NAME in client.cookies


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_valid_guest_identity_throttles_by_subject() -> None:
    game = _game(technical_id="subject_bucket_game")
    client, csrf = _client()
    _create(client, csrf, game)
    identity = AnonymousIdentity.objects.latest("created_at")
    key = f"throttle_sessions_anon:{identity.id}"
    try:
        cache.set(key, [time.time()] * 30, timeout=3600)
        response = client.post(
            API,
            data=json.dumps({"game_id": game.technical_id}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
    finally:
        cache.delete(key)
    assert response.status_code == 429


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_garbage_guest_cookie_falls_back_to_ip_throttle() -> None:
    game = _game(technical_id="ip_bucket_game")
    client, csrf = _client()
    key = "throttle_sessions_ip:127.0.0.1"
    client.cookies[COOKIE_NAME] = "garbage-token"
    try:
        cache.set(key, [time.time()] * 30, timeout=3600)
        response = client.post(
            API,
            data=json.dumps({"game_id": game.technical_id}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
    finally:
        cache.delete(key)
    assert response.status_code == 429


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_heartbeat_before_activation_is_rejected() -> None:
    game = _game(technical_id="pre_activation_game")
    client, csrf = _client()
    result = _create(client, csrf, game)
    token = client.cookies[COOKIE_NAME].value
    with pytest.raises(SessionError) as exc:
        heartbeat(_service_request(token), UUID(str(result["session_id"])))
    assert exc.value.code == "E_SESSION_INVALID"
    assert exc.value.status == 400


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_heartbeat_after_finish_is_gone() -> None:
    game = _game(technical_id="finished_heartbeat_game")
    client, csrf = _client()
    result = _create(client, csrf, game)
    _activate(client, csrf, str(result["session_id"]), str(result["ticket"]))
    GameSession.objects.filter(pk=result["session_id"]).update(state=GameSession.STATE_FINISHED)
    token = client.cookies[COOKIE_NAME].value
    with pytest.raises(SessionError) as exc:
        heartbeat(_service_request(token), UUID(str(result["session_id"])))
    assert exc.value.code == "E_SESSION_FINISHED"
    assert exc.value.status == 410


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_activation_is_allowed_at_ticket_and_window_boundary() -> None:
    game = _game(technical_id="boundary_game")
    client, csrf = _client()
    result = _create(client, csrf, game)
    now = timezone.now()
    GameSession.objects.filter(pk=result["session_id"]).update(
        created_at=now - timedelta(seconds=300),
        ticket_expires_at=now,
    )
    token = client.cookies[COOKIE_NAME].value
    context = activate_session(
        _service_request(token),
        UUID(str(result["session_id"])),
        ticket=str(result["ticket"]),
        binding_nonce=NONCE,
        now=now,
    )
    assert context["sessionId"] == result["session_id"]


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_idle_and_max_duration_boundaries_are_inclusive() -> None:
    game = _game(technical_id="idle_boundary_game")
    client, csrf = _client()
    result = _create(client, csrf, game)
    _activate(client, csrf, str(result["session_id"]), str(result["ticket"]))
    now = timezone.now()
    GameSession.objects.filter(pk=result["session_id"]).update(
        activated_at=now - timedelta(seconds=100),
        last_heartbeat_at=now - timedelta(seconds=1800),
    )
    token = client.cookies[COOKIE_NAME].value
    heartbeat(_service_request(token), UUID(str(result["session_id"])), now=now)
    session = GameSession.objects.get(pk=result["session_id"])
    assert session.state == GameSession.STATE_ACTIVE
    assert session.credited_ms == 45_000


@pytest.mark.django_db(transaction=True)
@override_settings(CACHES=LOCMEM_CACHES)
def test_concurrent_activation_of_one_ticket_has_single_winner() -> None:
    game = _game(technical_id="race_ticket_game")
    client, csrf = _client()
    result = _create(client, csrf, game)
    token = client.cookies[COOKIE_NAME].value
    session_id = UUID(str(result["session_id"]))
    ticket = str(result["ticket"])
    barrier = threading.Barrier(2)

    def worker() -> None:
        barrier.wait(timeout=10)
        activate_session(
            _service_request(token),
            session_id,
            ticket=ticket,
            binding_nonce=NONCE,
        )

    assert sorted(_run_parallel([worker, worker])) == ["E_TICKET_INVALID", "ok"]


@pytest.mark.django_db(transaction=True)
@override_settings(CACHES=LOCMEM_CACHES)
def test_concurrent_activation_cannot_exceed_active_limit() -> None:
    game = _game(technical_id="race_limit_game")
    client, csrf = _client()
    for _ in range(2):
        done = _create(client, csrf, game)
        assert (
            _activate(client, csrf, str(done["session_id"]), str(done["ticket"])).status_code == 200
        )
    tickets = [_create(client, csrf, game), _create(client, csrf, game)]
    token = client.cookies[COOKIE_NAME].value
    barrier = threading.Barrier(2)

    def make_worker(session_id: str, ticket: str):
        def worker() -> None:
            barrier.wait(timeout=10)
            activate_session(
                _service_request(token),
                UUID(session_id),
                ticket=ticket,
                binding_nonce=NONCE,
            )

        return worker

    workers = [make_worker(str(item["session_id"]), str(item["ticket"])) for item in tickets]
    assert sorted(_run_parallel(workers)) == ["E_RATE_LIMIT", "ok"]
    assert GameSession.objects.filter(game=game, state=GameSession.STATE_ACTIVE).count() == 3


@pytest.mark.django_db(transaction=True)
@override_settings(CACHES=LOCMEM_CACHES)
def test_concurrent_heartbeat_credits_once() -> None:
    game = _game(technical_id="race_heartbeat_game")
    client, csrf = _client()
    result = _create(client, csrf, game)
    _activate(client, csrf, str(result["session_id"]), str(result["ticket"]))
    token = client.cookies[COOKIE_NAME].value
    session_pk = UUID(str(result["session_id"]))
    base = timezone.now() - timedelta(seconds=100)
    GameSession.objects.filter(pk=session_pk).update(
        activated_at=base,
        last_heartbeat_at=base,
        credited_ms=0,
    )
    now = base + timedelta(seconds=10)
    barrier = threading.Barrier(2)

    def worker() -> None:
        barrier.wait(timeout=10)
        heartbeat(_service_request(token), session_pk, now=now)

    assert _run_parallel([worker, worker]) == ["ok", "ok"]
    session = GameSession.objects.get(pk=session_pk)
    assert session.credited_ms == 10_000
