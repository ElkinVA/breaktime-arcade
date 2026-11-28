from __future__ import annotations

import json
import re
import threading
import time
from datetime import timedelta
from unittest.mock import PropertyMock, patch
from uuid import UUID, uuid4

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.cache import caches
from django.db import connections
from django.db.models import ProtectedError
from django.http import HttpResponse
from django.test import Client, RequestFactory, override_settings
from django.utils import timezone
from redis.exceptions import RedisError

from apps.accounts.models import AnonymousIdentity, User
from apps.accounts.services.anonymous import COOKIE_NAME
from apps.accounts.services.profile import anonymize_user
from apps.catalog.models import Game, GameVersion, Genre
from apps.gameplay.api import throttling
from apps.gameplay.models import (
    GameDailyStats,
    GamePlayCredit,
    GameSession,
    UserGamePlaytime,
)
from apps.gameplay.services.results import submit_result
from apps.gameplay.services.sessions import (
    SessionError,
    activate_session,
    create_session,
    expire_stale_sessions,
    heartbeat,
)

LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    # Throttle uses a dedicated alias; tests keep the same separation.
    "throttle": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}
API = "/api/v1/sessions"
NONCE = "n" * 32


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    # Runs outside override_settings, so only the default alias is safe here.
    # The throttle alias is cleared in ``_client`` inside the test override.
    caches["default"].clear()
    yield
    caches["default"].clear()


def _client(user: User | None = None) -> tuple[Client, str]:
    caches["default"].clear()
    caches["throttle"].clear()
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


def _user_request(user: User):
    request = RequestFactory().post("/")
    request.user = user
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
        except Exception as exc:  # noqa: BLE001 - a deadlock must fail the test
            with lock:
                outcomes.append(f"{type(exc).__name__}: {exc}")
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
    assert set(result) == {"sessionId", "ticket", "expires_at"}
    session = GameSession.objects.get(pk=result["sessionId"])
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

    activated = _activate(client, csrf, str(result["sessionId"]), str(result["ticket"]))
    assert activated.status_code == 200, activated.content
    context = activated.json()["context"]
    assert context["sessionId"] == result["sessionId"]
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
    session = GameSession.objects.get(pk=result["sessionId"])
    assert context["seed"] == session.seed
    assert session.state == GameSession.STATE_ACTIVE
    assert session.ticket_hash is None

    reused = _activate(client, csrf, str(result["sessionId"]), str(result["ticket"]))
    assert reused.status_code == 400
    assert reused.json()["code"] == "E_TICKET_INVALID"


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_activation_rejects_wrong_ticket_and_expired_window() -> None:
    game = _game(technical_id="expired_game")
    client, csrf = _client()
    result = _create(client, csrf, game)
    session = GameSession.objects.get(pk=result["sessionId"])

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
    GameSession.objects.filter(pk=result["sessionId"]).update(
        ticket_expires_at=timezone.now() - timedelta(seconds=1)
    )
    response = _activate(client, csrf, str(result["sessionId"]), str(result["ticket"]))
    assert response.status_code == 410
    assert response.json()["code"] == "E_SESSION_EXPIRED"


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_other_subject_cannot_activate() -> None:
    game = _game(technical_id="owner_game")
    owner, csrf = _client()
    result = _create(owner, csrf, game)
    stranger, stranger_csrf = _client()
    response = _activate(stranger, stranger_csrf, str(result["sessionId"]), str(result["ticket"]))
    assert response.status_code == 403
    assert response.json()["code"] == "E_OWNERSHIP"


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_active_session_limit_is_three() -> None:
    game = _game(technical_id="limit_game")
    client, csrf = _client()
    for _ in range(3):
        result = _create(client, csrf, game)
        activated = _activate(client, csrf, str(result["sessionId"]), str(result["ticket"]))
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
    session = GameSession.objects.get(pk=result["sessionId"])
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
    session_id = result["sessionId"]
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
    _activate(client, csrf, str(result["sessionId"]), str(result["ticket"]))
    session = GameSession.objects.get(pk=result["sessionId"])
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
            _activate(client, csrf, str(done["sessionId"]), str(done["ticket"])).status_code == 200
        )
    first = _create(client, csrf, game)
    second = _create(client, csrf, game)
    assert _activate(client, csrf, str(first["sessionId"]), str(first["ticket"])).status_code == 200
    denied = _activate(client, csrf, str(second["sessionId"]), str(second["ticket"]))
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
    session = GameSession.objects.get(pk=result["sessionId"])
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
    assert GameSession.objects.filter(pk=result["sessionId"]).exists()
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
        caches["throttle"].set(key, [time.time()] * 30, timeout=3600)
        response = client.post(
            API,
            data=json.dumps({"game_id": game.technical_id}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
    finally:
        caches["throttle"].delete(key)
    assert response.status_code == 429


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_garbage_guest_cookie_falls_back_to_ip_throttle() -> None:
    game = _game(technical_id="ip_bucket_game")
    client, csrf = _client()
    key = "throttle_sessions_nosubject:127.0.0.1"
    client.cookies[COOKIE_NAME] = "garbage-token"
    try:
        caches["throttle"].set(key, [time.time()] * 30, timeout=3600)
        response = client.post(
            API,
            data=json.dumps({"game_id": game.technical_id}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
    finally:
        caches["throttle"].delete(key)
    assert response.status_code == 429


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_heartbeat_before_activation_is_rejected() -> None:
    game = _game(technical_id="pre_activation_game")
    client, csrf = _client()
    result = _create(client, csrf, game)
    token = client.cookies[COOKIE_NAME].value
    with pytest.raises(SessionError) as exc:
        heartbeat(_service_request(token), UUID(str(result["sessionId"])))
    assert exc.value.code == "E_SESSION_INVALID"
    assert exc.value.status == 400


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_heartbeat_after_finish_is_gone() -> None:
    game = _game(technical_id="finished_heartbeat_game")
    client, csrf = _client()
    result = _create(client, csrf, game)
    _activate(client, csrf, str(result["sessionId"]), str(result["ticket"]))
    GameSession.objects.filter(pk=result["sessionId"]).update(state=GameSession.STATE_FINISHED)
    token = client.cookies[COOKIE_NAME].value
    with pytest.raises(SessionError) as exc:
        heartbeat(_service_request(token), UUID(str(result["sessionId"])))
    assert exc.value.code == "E_SESSION_FINISHED"
    assert exc.value.status == 410


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_activation_is_allowed_at_ticket_and_window_boundary() -> None:
    game = _game(technical_id="boundary_game")
    client, csrf = _client()
    result = _create(client, csrf, game)
    now = timezone.now()
    GameSession.objects.filter(pk=result["sessionId"]).update(
        created_at=now - timedelta(seconds=300),
        ticket_expires_at=now,
    )
    token = client.cookies[COOKIE_NAME].value
    context = activate_session(
        _service_request(token),
        UUID(str(result["sessionId"])),
        ticket=str(result["ticket"]),
        binding_nonce=NONCE,
        now=now,
    )
    assert context["sessionId"] == result["sessionId"]


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_idle_and_max_duration_boundaries_are_inclusive() -> None:
    game = _game(technical_id="idle_boundary_game")
    client, csrf = _client()
    result = _create(client, csrf, game)
    _activate(client, csrf, str(result["sessionId"]), str(result["ticket"]))
    now = timezone.now()
    GameSession.objects.filter(pk=result["sessionId"]).update(
        activated_at=now - timedelta(seconds=100),
        last_heartbeat_at=now - timedelta(seconds=1800),
    )
    token = client.cookies[COOKIE_NAME].value
    heartbeat(_service_request(token), UUID(str(result["sessionId"])), now=now)
    session = GameSession.objects.get(pk=result["sessionId"])
    assert session.state == GameSession.STATE_ACTIVE
    assert session.credited_ms == 45_000


@pytest.mark.django_db(transaction=True)
@override_settings(CACHES=LOCMEM_CACHES)
def test_concurrent_activation_of_one_ticket_has_single_winner() -> None:
    game = _game(technical_id="race_ticket_game")
    client, csrf = _client()
    result = _create(client, csrf, game)
    token = client.cookies[COOKIE_NAME].value
    session_id = UUID(str(result["sessionId"]))
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
            _activate(client, csrf, str(done["sessionId"]), str(done["ticket"])).status_code == 200
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

    workers = [make_worker(str(item["sessionId"]), str(item["ticket"])) for item in tickets]
    assert sorted(_run_parallel(workers)) == ["E_RATE_LIMIT", "ok"]
    assert GameSession.objects.filter(game=game, state=GameSession.STATE_ACTIVE).count() == 3


@pytest.mark.django_db(transaction=True)
@override_settings(CACHES=LOCMEM_CACHES)
def test_concurrent_heartbeat_credits_once() -> None:
    game = _game(technical_id="race_heartbeat_game")
    client, csrf = _client()
    result = _create(client, csrf, game)
    _activate(client, csrf, str(result["sessionId"]), str(result["ticket"]))
    token = client.cookies[COOKIE_NAME].value
    session_pk = UUID(str(result["sessionId"]))
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


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_heartbeat_http_endpoint_requires_csrf_and_returns_204() -> None:
    game = _game(technical_id="hb_http_game")
    client, csrf = _client()
    result = _create(client, csrf, game)
    _activate(client, csrf, str(result["sessionId"]), str(result["ticket"]))
    url = f"{API}/{result['sessionId']}/heartbeat"
    without_csrf = client.post(url)
    assert without_csrf.status_code == 403
    accepted = client.post(url, HTTP_X_CSRFTOKEN=csrf)
    assert accepted.status_code == 204


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_heartbeat_throttle_is_per_session_with_structured_error() -> None:
    game = _game(technical_id="hb_throttle_game")
    client, csrf = _client()
    first = _create(client, csrf, game)
    _activate(client, csrf, str(first["sessionId"]), str(first["ticket"]))
    identity = AnonymousIdentity.objects.latest("created_at")
    key = f"throttle_heartbeat_anon:{identity.id}:{first['sessionId']}"
    try:
        caches["throttle"].set(key, [time.time()] * 3, timeout=60)
        response = client.post(f"{API}/{first['sessionId']}/heartbeat", HTTP_X_CSRFTOKEN=csrf)
    finally:
        caches["throttle"].delete(key)
    assert response.status_code == 429
    assert response.json() == {"code": "E_RATE_LIMIT", "message": "Too many requests"}
    assert "Retry-After" in response.headers

    second = _create(client, csrf, game)
    _activate(client, csrf, str(second["sessionId"]), str(second["ticket"]))
    other = client.post(f"{API}/{second['sessionId']}/heartbeat", HTTP_X_CSRFTOKEN=csrf)
    assert other.status_code == 204


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_heartbeat_invalid_session_ids_share_one_bucket() -> None:
    game = _game(technical_id="hb_invalid_bucket_game")
    client, csrf = _client()
    first = _create(client, csrf, game)
    _activate(client, csrf, str(first["sessionId"]), str(first["ticket"]))
    identity = AnonymousIdentity.objects.latest("created_at")

    # Unknown UUIDs must not mint a bucket each: the first 3/min share the
    # per-subject "invalid" bucket and the fourth is rejected.
    for _ in range(3):
        response = client.post(f"{API}/{uuid4()}/heartbeat", HTTP_X_CSRFTOKEN=csrf)
        assert response.status_code == 404
    blocked = client.post(f"{API}/{uuid4()}/heartbeat", HTTP_X_CSRFTOKEN=csrf)
    assert blocked.status_code == 429
    assert blocked.json() == {"code": "E_RATE_LIMIT", "message": "Too many requests"}
    assert "Retry-After" in blocked.headers
    invalid_key = f"throttle_heartbeat_anon:{identity.id}:invalid"
    assert caches["throttle"].get(invalid_key)

    # Two valid active sessions keep separate buckets.
    second = _create(client, csrf, game)
    _activate(client, csrf, str(second["sessionId"]), str(second["ticket"]))
    first_key = f"throttle_heartbeat_anon:{identity.id}:{first['sessionId']}"
    try:
        caches["throttle"].set(first_key, [time.time()] * 3, timeout=60)
        first_response = client.post(f"{API}/{first['sessionId']}/heartbeat", HTTP_X_CSRFTOKEN=csrf)
        assert first_response.status_code == 429
        other = client.post(f"{API}/{second['sessionId']}/heartbeat", HTTP_X_CSRFTOKEN=csrf)
        assert other.status_code == 204
    finally:
        caches["throttle"].delete(first_key)
        caches["throttle"].delete(invalid_key)


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_heartbeat_allows_three_per_active_session_then_429() -> None:
    game = _game(technical_id="hb_three_per_session_game")
    client, csrf = _client()
    result = _create(client, csrf, game)
    _activate(client, csrf, str(result["sessionId"]), str(result["ticket"]))
    url = f"{API}/{result['sessionId']}/heartbeat"

    for _ in range(3):
        response = client.post(url, HTTP_X_CSRFTOKEN=csrf)
        assert response.status_code == 204

    blocked = client.post(url, HTTP_X_CSRFTOKEN=csrf)
    assert blocked.status_code == 429
    assert blocked.json() == {"code": "E_RATE_LIMIT", "message": "Too many requests"}


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_heartbeat_preflight_blocks_before_session_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = _game(technical_id="hb_preflight_game")
    client, csrf = _client()
    result = _create(client, csrf, game)
    _activate(client, csrf, str(result["sessionId"]), str(result["ticket"]))
    ip_key = "throttle_heartbeat_preflight_ip:127.0.0.1"
    caches["throttle"].set(ip_key, [time.time()] * 120, timeout=60)
    called = False

    def fail_if_session_lookup(*args: object, **kwargs: object) -> None:
        nonlocal called
        called = True
        raise AssertionError("preflight must reject before GameSession lookup")

    monkeypatch.setattr(
        throttling.SessionScopedRateThrottle,
        "_active_session_id",
        fail_if_session_lookup,
    )
    try:
        response = client.post(f"{API}/{result['sessionId']}/heartbeat", HTTP_X_CSRFTOKEN=csrf)
    finally:
        caches["throttle"].delete(ip_key)
    assert response.status_code == 429
    assert called is False


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_authenticated_heartbeat_preflight_blocks_before_session_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = _game(technical_id="hb_auth_preflight_game")
    user = User.objects.create_user(login="hb_preflight_user", password="correct horse battery")
    client, csrf = _client(user)
    result = _create(client, csrf, game)
    _activate(client, csrf, str(result["sessionId"]), str(result["ticket"]))
    subject_key = f"throttle_heartbeat_preflight_subject:user:{user.id}"
    caches["throttle"].set(subject_key, [time.time()] * 30, timeout=60)
    called = False

    def fail_if_session_lookup(*args: object, **kwargs: object) -> None:
        nonlocal called
        called = True
        raise AssertionError("preflight must reject before GameSession lookup")

    monkeypatch.setattr(
        throttling.SessionScopedRateThrottle,
        "_active_session_id",
        fail_if_session_lookup,
    )
    try:
        response = client.post(f"{API}/{result['sessionId']}/heartbeat", HTTP_X_CSRFTOKEN=csrf)
    finally:
        caches["throttle"].delete(subject_key)
    assert response.status_code == 429
    assert called is False


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_authenticated_heartbeat_is_exempt_from_guest_ip_preflight() -> None:
    game = _game(technical_id="hb_auth_ip_exempt_game")
    user = User.objects.create_user(login="hb_ip_exempt_user", password="correct horse battery")
    client, csrf = _client(user)
    result = _create(client, csrf, game)
    _activate(client, csrf, str(result["sessionId"]), str(result["ticket"]))
    ip_key = "throttle_heartbeat_preflight_ip:127.0.0.1"
    caches["throttle"].set(ip_key, [time.time()] * 120, timeout=60)
    try:
        response = client.post(f"{API}/{result['sessionId']}/heartbeat", HTTP_X_CSRFTOKEN=csrf)
    finally:
        caches["throttle"].delete(ip_key)
    assert response.status_code == 204


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_heartbeat_preflight_is_shared_across_guest_identities() -> None:
    game = _game(technical_id="hb_shared_guest_ip_game")
    first_client, first_csrf = _client()
    second_client, second_csrf = _client()
    first = _create(first_client, first_csrf, game)
    second = _create(second_client, second_csrf, game)
    _activate(first_client, first_csrf, str(first["sessionId"]), str(first["ticket"]))
    _activate(second_client, second_csrf, str(second["sessionId"]), str(second["ticket"]))
    ip_key = "throttle_heartbeat_preflight_ip:127.0.0.1"
    caches["throttle"].set(ip_key, [time.time()] * 120, timeout=60)
    try:
        for client, csrf, result in (
            (first_client, first_csrf, first),
            (second_client, second_csrf, second),
        ):
            response = client.post(f"{API}/{result['sessionId']}/heartbeat", HTTP_X_CSRFTOKEN=csrf)
            assert response.status_code == 429
    finally:
        caches["throttle"].delete(ip_key)


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_heartbeat_resolves_guest_identity_once_per_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = _game(technical_id="hb_identity_cache_game")
    client, csrf = _client()
    result = _create(client, csrf, game)
    _activate(client, csrf, str(result["sessionId"]), str(result["ticket"]))
    calls: list[object] = []
    real_get_identity = throttling.get_anonymous_identity

    def counted(request: object) -> object:
        calls.append(request)
        return real_get_identity(request)

    monkeypatch.setattr(throttling, "get_anonymous_identity", counted)
    response = client.post(f"{API}/{result['sessionId']}/heartbeat", HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code == 204
    assert len(calls) == 1


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_heartbeat_throttles_fail_open_when_backend_is_unavailable() -> None:
    game = _game(technical_id="hb_throttle_down_game")
    client, csrf = _client()
    result = _create(client, csrf, game)
    _activate(client, csrf, str(result["sessionId"]), str(result["ticket"]))
    with patch.object(
        throttling.ThrottleCacheMixin,
        "cache",
        new_callable=PropertyMock,
        side_effect=RedisError("throttle backend down"),
    ):
        response = client.post(f"{API}/{result['sessionId']}/heartbeat", HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code == 204


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_guest_ip_secondary_cap_applies_across_identities() -> None:
    game = _game(technical_id="ip_cap_game")
    first_client, first_csrf = _client()
    _create(first_client, first_csrf, game)
    second_client, second_csrf = _client()
    _create(second_client, second_csrf, game)
    ip_key = "throttle_sessions_ip:127.0.0.1"
    try:
        caches["throttle"].set(ip_key, [time.time()] * 600, timeout=3600)
        for client, csrf in ((first_client, first_csrf), (second_client, second_csrf)):
            response = client.post(
                API,
                data=json.dumps({"game_id": game.technical_id}),
                content_type="application/json",
                HTTP_X_CSRFTOKEN=csrf,
            )
            assert response.status_code == 429
            assert response.json()["code"] == "E_RATE_LIMIT"
    finally:
        caches["throttle"].delete(ip_key)


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_authenticated_user_is_exempt_from_guest_ip_cap() -> None:
    game = _game(technical_id="user_ip_cap_game")
    user = User.objects.create_user(login="bob", password="correct horse battery staple")
    client, csrf = _client(user)
    ip_key = "throttle_sessions_ip:127.0.0.1"
    try:
        caches["throttle"].set(ip_key, [time.time()] * 600, timeout=3600)
        result = _create(client, csrf, game)
    finally:
        caches["throttle"].delete(ip_key)
    assert GameSession.objects.filter(pk=result["sessionId"]).exists()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_heartbeat_max_duration_boundary_is_inclusive() -> None:
    game = _game(technical_id="max_duration_boundary_game")
    client, csrf = _client()
    result = _create(client, csrf, game)
    _activate(client, csrf, str(result["sessionId"]), str(result["ticket"]))
    now = timezone.now()
    GameSession.objects.filter(pk=result["sessionId"]).update(
        activated_at=now - timedelta(seconds=1800),
        last_heartbeat_at=now - timedelta(seconds=10),
    )
    token = client.cookies[COOKIE_NAME].value
    heartbeat(_service_request(token), UUID(str(result["sessionId"])), now=now)
    session = GameSession.objects.get(pk=result["sessionId"])
    assert session.state == GameSession.STATE_ACTIVE
    assert session.credited_ms == 10_000


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_second_activation_after_expiry_is_gone() -> None:
    game = _game(technical_id="repeat_expired_game")
    client, csrf = _client()
    result = _create(client, csrf, game)
    GameSession.objects.filter(pk=result["sessionId"]).update(
        created_at=timezone.now() - timedelta(seconds=301)
    )
    first = _activate(client, csrf, str(result["sessionId"]), str(result["ticket"]))
    assert first.status_code == 410
    second = _activate(client, csrf, str(result["sessionId"]), str(result["ticket"]))
    assert second.status_code == 410
    assert second.json()["code"] == "E_SESSION_EXPIRED"


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_game_with_sessions_is_protected_from_delete() -> None:
    game = _game(technical_id="protect_game")
    client, csrf = _client()
    _create(client, csrf, game)
    with pytest.raises(ProtectedError):
        game.delete()


@pytest.mark.django_db
def test_user_deletion_tombstones_sessions_and_keeps_finished_history() -> None:
    user = User.objects.create_user(
        login="delete_sessions", password="correct horse battery staple"
    )
    game = _game(technical_id="delete_sessions_game")
    created = GameSession.objects.create(
        game=game,
        game_version=game.current_version,
        subject_type=GameSession.SUBJECT_USER,
        subject_id=user.id,
        mode=GameSession.MODE_USER,
        state=GameSession.STATE_CREATED,
        ticket_hash="c" * 64,
        ticket_expires_at=timezone.now() + timedelta(seconds=60),
        binding_nonce_hash="d" * 64,
        seed="seed-created",
    )
    active = GameSession.objects.create(
        game=game,
        game_version=game.current_version,
        subject_type=GameSession.SUBJECT_USER,
        subject_id=user.id,
        mode=GameSession.MODE_USER,
        state=GameSession.STATE_ACTIVE,
        seed="seed-active",
    )
    finished = GameSession.objects.create(
        game=game,
        game_version=game.current_version,
        subject_type=GameSession.SUBJECT_USER,
        subject_id=user.id,
        mode=GameSession.MODE_USER,
        state=GameSession.STATE_FINISHED,
        seed="seed-finished",
    )
    expired = GameSession.objects.create(
        game=game,
        game_version=game.current_version,
        subject_type=GameSession.SUBJECT_USER,
        subject_id=user.id,
        mode=GameSession.MODE_USER,
        state=GameSession.STATE_EXPIRED,
        seed="seed-expired",
    )
    anon_subject = uuid4()
    anon = GameSession.objects.create(
        game=game,
        game_version=game.current_version,
        subject_type=GameSession.SUBJECT_ANON,
        subject_id=anon_subject,
        mode=GameSession.MODE_GUEST,
        state=GameSession.STATE_ACTIVE,
        seed="seed-anon",
    )
    GamePlayCredit.objects.create(
        game=game,
        subject_type="user",
        subject_id=user.id,
        last_credited_at=timezone.now(),
    )

    anonymize_user(user)

    for session in (created, active, finished, expired):
        session.refresh_from_db()
        assert session.subject_type == GameSession.SUBJECT_DELETED
        assert session.subject_id != user.id
    assert created.state == GameSession.STATE_ABORTED
    assert created.ticket_hash is None
    assert created.ticket_expires_at is None
    assert created.binding_nonce_hash == ""
    assert active.state == GameSession.STATE_ABORTED
    assert finished.state == GameSession.STATE_FINISHED
    assert expired.state == GameSession.STATE_EXPIRED
    assert (
        len({created.subject_id, active.subject_id, finished.subject_id, expired.subject_id}) == 4
    )
    request = RequestFactory().post("/")
    request.user = user
    with pytest.raises(SessionError) as exc:
        submit_result(
            request,
            active.pk,
            idempotency_key="deleted-session",
            value=1,
            duration_ms=1,
        )
    assert exc.value.code == "E_OWNERSHIP"
    assert not GamePlayCredit.objects.filter(subject_type="user", subject_id=user.id).exists()
    anon.refresh_from_db()
    assert anon.subject_type == GameSession.SUBJECT_ANON
    assert anon.subject_id == anon_subject


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_throttle_fails_open_when_backend_is_unavailable() -> None:
    game = _game(technical_id="throttle_down_game")
    client, csrf = _client()
    with patch.object(
        throttling.ThrottleCacheMixin,
        "cache",
        new_callable=PropertyMock,
        side_effect=RedisError("throttle backend down"),
    ):
        result = _create(client, csrf, game)
    assert GameSession.objects.filter(pk=result["sessionId"]).exists()


def test_ipv6_is_aggregated_by_64_prefix() -> None:
    first = RequestFactory().get("/", REMOTE_ADDR="2001:db8:0:1::1")
    second = RequestFactory().get("/", REMOTE_ADDR="2001:db8:0:1::2")
    other = RequestFactory().get("/", REMOTE_ADDR="2001:db8:0:2::1")
    assert throttling._client_ip(first) == throttling._client_ip(second)
    assert throttling._client_ip(first) != throttling._client_ip(other)


def test_ipv4_mapped_address_uses_ipv4_bucket() -> None:
    mapped = RequestFactory().get("/", REMOTE_ADDR="::ffff:203.0.113.7")
    plain = RequestFactory().get("/", REMOTE_ADDR="203.0.113.7")
    assert throttling._client_ip(mapped) == throttling._client_ip(plain)


def test_guest_fallback_and_ip_throttle_use_different_keys() -> None:
    request = RequestFactory().post("/", REMOTE_ADDR="203.0.113.7")
    request.user = AnonymousUser()
    assert throttling._subject_ident(request) == "nosubject:203.0.113.7"
    ip_throttle = throttling.GuestIpRateThrottle()
    assert ip_throttle.get_cache_key(request, view=None) == "throttle_sessions_ip:203.0.113.7"


def test_rate_limits_match_appendix_e() -> None:
    from django.conf import settings

    rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    assert rates["sessions"] == "30/hour"
    assert rates["sessions_activate"] == "30/hour"
    assert rates["sessions_close"] == "30/hour"
    assert rates["sessions_ip"] == "600/hour"
    assert rates["results"] == "60/hour"
    assert rates["results_ip"] == "1200/hour"
    assert rates["heartbeat"] == "3/min"
    assert rates["heartbeat_preflight_subject"] == "30/min"
    assert rates["heartbeat_preflight_ip"] == "120/min"
    assert rates["reports"] == "5/day"
    assert rates["reports_ip"] == "30/day"


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_create_activate_and_close_have_separate_throttle_buckets() -> None:
    game = _game(technical_id="scope_split_game")
    user = User.objects.create_user(login="scope_split", password="correct horse battery staple")
    client, csrf = _client(user)
    created = _create(client, csrf, game)
    session_id = str(created["sessionId"])
    create_key = f"throttle_sessions_user:{user.id}"
    activate_key = f"throttle_sessions_activate_user:{user.id}"
    close_key = f"throttle_sessions_close_user:{user.id}"
    try:
        caches["throttle"].set(create_key, [time.time()] * 30, timeout=3600)
        blocked = client.post(
            API,
            data=json.dumps({"game_id": game.technical_id}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert blocked.status_code == 429
        assert _activate(client, csrf, session_id, str(created["ticket"])).status_code == 200
        closed = client.post(f"{API}/{session_id}/close", HTTP_X_CSRFTOKEN=csrf)
        assert closed.status_code == 204

        caches["throttle"].set(activate_key, [time.time()] * 30, timeout=3600)
        assert _activate(client, csrf, session_id, str(created["ticket"])).status_code == 429
        caches["throttle"].set(close_key, [time.time()] * 30, timeout=3600)
        assert client.post(f"{API}/{session_id}/close", HTTP_X_CSRFTOKEN=csrf).status_code == 429
    finally:
        for key in (create_key, activate_key, close_key):
            caches["throttle"].delete(key)


def test_client_ip_middleware_trusts_only_proxy_networks() -> None:
    from apps.core.middleware import ClientIPMiddleware

    middleware = ClientIPMiddleware(lambda request: HttpResponse())
    trusted = RequestFactory().get(
        "/", REMOTE_ADDR="172.18.0.6", HTTP_X_FORWARDED_FOR="203.0.113.5"
    )
    middleware(trusted)
    assert trusted.META["REMOTE_ADDR"] == "203.0.113.5"

    untrusted = RequestFactory().get("/", REMOTE_ADDR="8.8.8.8", HTTP_X_FORWARDED_FOR="203.0.113.5")
    middleware(untrusted)
    assert untrusted.META["REMOTE_ADDR"] == "8.8.8.8"


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_user_heartbeat_credits_playtime() -> None:
    game = _game(technical_id="playtime_game")
    user = User.objects.create_user(login="sven", password="correct horse battery staple")
    client, csrf = _client(user)
    result = _create(client, csrf, game)
    _activate(client, csrf, str(result["sessionId"]), str(result["ticket"]))
    session = GameSession.objects.get(pk=result["sessionId"])
    base = timezone.now() - timedelta(seconds=100)
    GameSession.objects.filter(pk=session.pk).update(
        activated_at=base, last_heartbeat_at=base, credited_ms=0
    )
    heartbeat(_user_request(user), session.pk, now=base + timedelta(seconds=30))
    playtime = UserGamePlaytime.objects.get(user=user, game=game)
    assert playtime.verified_seconds == 30

    heartbeat(_user_request(user), session.pk, now=base + timedelta(seconds=40))
    playtime.refresh_from_db()
    assert playtime.verified_seconds == 40


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_guest_and_preview_heartbeats_do_not_credit_playtime() -> None:
    game = _game(technical_id="no_playtime_game")
    guest, csrf = _client()
    result = _create(guest, csrf, game)
    _activate(guest, csrf, str(result["sessionId"]), str(result["ticket"]))
    session = GameSession.objects.get(pk=result["sessionId"])
    base = timezone.now() - timedelta(seconds=100)
    GameSession.objects.filter(pk=session.pk).update(
        activated_at=base, last_heartbeat_at=base, credited_ms=0
    )
    token = guest.cookies[COOKIE_NAME].value
    heartbeat(_service_request(token), session.pk, now=base + timedelta(seconds=30))

    user = User.objects.create_user(login="tara", password="correct horse battery staple")
    preview = GameSession.objects.create(
        game=game,
        game_version=game.current_version,
        subject_type=GameSession.SUBJECT_USER,
        subject_id=user.id,
        mode=GameSession.MODE_PREVIEW,
        state=GameSession.STATE_ACTIVE,
        seed="preview-playtime",
        max_session_seconds=1800,
        credited_ms=0,
        activated_at=base,
        last_heartbeat_at=base,
    )
    heartbeat(_user_request(user), preview.pk, now=base + timedelta(seconds=30))
    assert not UserGamePlaytime.objects.exists()


@pytest.mark.django_db(transaction=True)
@override_settings(CACHES=LOCMEM_CACHES)
def test_parallel_first_heartbeats_do_not_break_playtime_upsert() -> None:
    game = _game(technical_id="playtime_race_game")
    user = User.objects.create_user(login="ursula", password="correct horse battery staple")
    base = timezone.now() - timedelta(seconds=100)
    sessions = [
        GameSession.objects.create(
            game=game,
            game_version=game.current_version,
            subject_type=GameSession.SUBJECT_USER,
            subject_id=user.id,
            mode=GameSession.MODE_USER,
            state=GameSession.STATE_ACTIVE,
            seed=f"seed-{index}",
            max_session_seconds=1800,
            credited_ms=0,
            activated_at=base,
            last_heartbeat_at=base,
        )
        for index in range(2)
    ]
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def worker(session_pk) -> None:
        try:
            barrier.wait(timeout=10)
            heartbeat(_user_request(user), session_pk, now=base + timedelta(seconds=30))
        except SessionError as exc:
            with lock:
                outcomes.append(exc.code)
        else:
            with lock:
                outcomes.append("ok")
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker, args=(session.pk,)) for session in sessions]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert outcomes == ["ok", "ok"]
    playtime = UserGamePlaytime.objects.get(user=user, game=game)
    assert playtime.verified_seconds == 60


@pytest.mark.django_db
def test_stale_active_sessions_do_not_block_create() -> None:
    client, csrf = _client()
    game = _game()
    active_ids: list[str] = []
    for _index in range(3):
        created = _create(client, csrf, game)
        response = _activate(client, csrf, str(created["sessionId"]), str(created["ticket"]))
        assert response.status_code == 200
        active_ids.append(str(created["sessionId"]))

    stale_id = active_ids[0]
    GameSession.objects.filter(pk=stale_id).update(
        last_heartbeat_at=timezone.now() - timedelta(seconds=31 * 60)
    )

    created = _create(client, csrf, game)
    assert created["sessionId"]
    stale = GameSession.objects.get(pk=stale_id)
    assert stale.state == GameSession.STATE_EXPIRED
    assert (
        GameSession.objects.filter(
            subject_type=GameSession.SUBJECT_ANON,
            game=game,
            state=GameSession.STATE_ACTIVE,
        ).count()
        == 2
    )


@pytest.mark.django_db
def test_stale_active_sessions_do_not_block_activation() -> None:
    client, csrf = _client()
    game = _game()
    tickets = [(_create(client, csrf, game)) for _index in range(4)]
    for created in tickets[:2]:
        response = _activate(client, csrf, str(created["sessionId"]), str(created["ticket"]))
        assert response.status_code == 200
    third = _activate(client, csrf, str(tickets[2]["sessionId"]), str(tickets[2]["ticket"]))
    assert third.status_code == 200
    GameSession.objects.filter(pk=str(tickets[0]["sessionId"])).update(
        last_heartbeat_at=timezone.now() - timedelta(seconds=31 * 60)
    )

    fourth = _activate(client, csrf, str(tickets[3]["sessionId"]), str(tickets[3]["ticket"]))
    assert fourth.status_code == 200
    assert GameSession.objects.get(pk=str(tickets[0]["sessionId"])).state == (
        GameSession.STATE_EXPIRED
    )


@pytest.mark.django_db
def test_expire_stale_sessions_task_is_idempotent() -> None:
    client, csrf = _client()
    game = _game()
    created = _create(client, csrf, game)
    assert (
        _activate(client, csrf, str(created["sessionId"]), str(created["ticket"])).status_code
        == 200
    )
    GameSession.objects.filter(pk=str(created["sessionId"])).update(
        last_heartbeat_at=timezone.now() - timedelta(seconds=31 * 60)
    )

    assert expire_stale_sessions() == 1
    assert GameSession.objects.get(pk=str(created["sessionId"])).state == (
        GameSession.STATE_EXPIRED
    )
    assert expire_stale_sessions() == 0


@pytest.mark.django_db
def test_expire_stale_sessions_records_popularity_credit_once() -> None:
    client, csrf = _client()
    game = _game()
    created = _create(client, csrf, game)
    response = _activate(client, csrf, str(created["sessionId"]), str(created["ticket"]))
    assert response.status_code == 200
    session = GameSession.objects.get(pk=str(created["sessionId"]))
    now = timezone.now()
    GameSession.objects.filter(pk=session.pk).update(
        activated_at=now - timedelta(seconds=120),
        last_heartbeat_at=now - timedelta(seconds=120),
        max_session_seconds=60,
        credited_ms=20_000,
    )

    assert expire_stale_sessions() == 1
    assert GamePlayCredit.objects.filter(
        game=game,
        subject_type=GameSession.SUBJECT_ANON,
        subject_id=session.subject_id,
    ).exists()
    stats = GameDailyStats.objects.get(game=game)
    assert stats.sessions == 1
    assert stats.completions == 0

    assert expire_stale_sessions() == 0
    stats.refresh_from_db()
    assert stats.sessions == 1


@pytest.mark.django_db(transaction=True)
def test_create_sweep_and_beat_task_do_not_deadlock() -> None:
    game = _game()
    user = User.objects.create_user(login="sweep_race_user")
    old = timezone.now() - timedelta(seconds=31 * 60)
    [
        GameSession.objects.create(
            game=game,
            game_version=game.current_version,
            subject_type=GameSession.SUBJECT_USER,
            subject_id=user.id,
            mode=GameSession.MODE_USER,
            state=GameSession.STATE_ACTIVE,
            seed=f"race-{index}",
            max_session_seconds=1800,
            credited_ms=20_000,
            activated_at=old,
            last_heartbeat_at=old,
        )
        for index in range(2)
    ]
    barrier = threading.Barrier(2)

    def sweep() -> None:
        request = _user_request(user)
        response = HttpResponse()
        barrier.wait(timeout=10)
        create_session(request, response, game_id=game.technical_id)

    def beat_task() -> None:
        barrier.wait(timeout=10)
        expire_stale_sessions()

    outcomes = _run_parallel([sweep, beat_task])
    assert len(outcomes) == 2, outcomes
    assert all(outcome == "ok" for outcome in outcomes), outcomes
