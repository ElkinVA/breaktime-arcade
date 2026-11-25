from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from django.core.cache import caches
from django.db import DatabaseError, connections, transaction
from django.test import Client, RequestFactory, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Game, GameVersion, Genre
from apps.gameplay.api.serializers import SessionResultSerializer
from apps.gameplay.models import GameResult, GameSession, LeaderboardEntry
from apps.gameplay.services.results import anonymize_user_results, submit_result

LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "throttle": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}
API = "/api/v1/sessions"


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    caches["default"].clear()
    caches["throttle"].clear()
    yield
    caches["default"].clear()
    caches["throttle"].clear()


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


def _game(
    *,
    technical_id: str = "result_game",
    direction: str = "higher_is_better",
    verification: dict[str, object] | None = None,
) -> Game:
    genre = Genre.objects.create(code=f"genre_{technical_id}")
    game = Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=f"slug-{technical_id}",
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
        max_session_seconds=1800,
        score_direction=direction,
    )
    version = GameVersion.objects.create(
        game=game,
        semver="1.0.0",
        package_hash="a" * 64,
        runtime_hash="b" * 64,
        sdk_version="1.1.0",
        size_bytes=1000,
        manifest={"verification": verification} if verification else {},
        supported_languages=["en"],
    )
    game.current_version = version
    game.save(update_fields=["current_version"])
    return game


def _create(client: Client, csrf: str, game: Game) -> dict[str, object]:
    response = client.post(
        API,
        data=json.dumps({"game_id": game.technical_id}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 201, response.content
    return response.json()


def _activate(client: Client, csrf: str, session_id: str, ticket: str) -> None:
    response = client.post(
        f"{API}/{session_id}/activate",
        data=json.dumps({"ticket": ticket, "binding_nonce": "n" * 32}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 200, response.content


def _ready_session(client: Client, csrf: str, game: Game) -> str:
    result = _create(client, csrf, game)
    _activate(client, csrf, str(result["sessionId"]), str(result["ticket"]))
    now = timezone.now()
    GameSession.objects.filter(pk=result["sessionId"]).update(
        credited_ms=30_000,
        activated_at=now - timedelta(seconds=30),
        last_heartbeat_at=now,
    )
    return str(result["sessionId"])


def _result(
    client: Client,
    csrf: str,
    session_id: str,
    *,
    key: str = "idem-1",
    value: int = 100,
    duration_ms: int = 30_000,
    seed: str | None = None,
    event_log: object | None = None,
    with_csrf: bool = True,
) -> object:
    headers = {"HTTP_X_CSRFTOKEN": csrf} if with_csrf else {}
    payload: dict[str, object] = {"value": value, "durationMs": duration_ms}
    if seed is not None:
        payload["seed"] = seed
    if event_log is not None:
        payload["eventLog"] = event_log
    return client.post(
        f"{API}/{session_id}/result",
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=key,
        **headers,
    )


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_user_result_is_stored_and_creates_leaderboard_entry() -> None:
    game = _game()
    user = User.objects.create_user(login="carol", password="correct horse battery staple")
    client, csrf = _client(user)
    session_id = _ready_session(client, csrf, game)

    response = _result(client, csrf, session_id, value=100)
    assert response.status_code == 200, response.content
    assert response.json() == {
        "status": "saved",
        "rank": 1,
        "is_personal_best": True,
        "is_record": True,
        "trust_level": "client_reported",
    }
    result = GameResult.objects.get(session_id=session_id)
    assert result.value == 100
    assert result.user_id == user.id
    assert result.game_version_id == game.current_version_id
    session = GameSession.objects.get(pk=session_id)
    assert session.state == GameSession.STATE_FINISHED
    entry = LeaderboardEntry.objects.get(game=game, user=user)
    assert entry.best_result_id == result.id
    assert entry.value == 100


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_same_idempotency_key_returns_saved_response() -> None:
    game = _game(technical_id="idem_game")
    user = User.objects.create_user(login="dave", password="correct horse battery staple")
    client, csrf = _client(user)
    session_id = _ready_session(client, csrf, game)
    first = _result(client, csrf, session_id, key="same")
    second = _result(client, csrf, session_id, key="same")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert GameResult.objects.filter(session_id=session_id).count() == 1


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_different_key_after_finish_is_rejected() -> None:
    game = _game(technical_id="finished_key_game")
    user = User.objects.create_user(login="erin", password="correct horse battery staple")
    client, csrf = _client(user)
    session_id = _ready_session(client, csrf, game)
    assert _result(client, csrf, session_id, key="first").status_code == 200
    second = _result(client, csrf, session_id, key="second")
    assert second.status_code == 410
    assert second.json()["code"] == "E_SESSION_FINISHED"


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_guest_result_is_forbidden_and_not_stored() -> None:
    game = _game(technical_id="guest_result_game")
    client, csrf = _client()
    session_id = _ready_session(client, csrf, game)
    response = _result(client, csrf, session_id)
    assert response.status_code == 403
    assert response.json()["code"] == "E_GUEST_FORBIDDEN"
    assert not GameResult.objects.exists()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_other_user_cannot_submit_result() -> None:
    game = _game(technical_id="owner_result_game")
    owner = User.objects.create_user(login="frank", password="correct horse battery staple")
    owner_client, owner_csrf = _client(owner)
    session_id = _ready_session(owner_client, owner_csrf, game)
    stranger = User.objects.create_user(login="grace", password="correct horse battery staple")
    stranger_client, stranger_csrf = _client(stranger)
    response = _result(stranger_client, stranger_csrf, session_id)
    assert response.status_code == 403
    assert response.json()["code"] == "E_OWNERSHIP"


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_result_validation_rejects_score_and_duration() -> None:
    game = _game(technical_id="range_result_game")
    user = User.objects.create_user(login="heidi", password="correct horse battery staple")
    client, csrf = _client(user)
    session_id = _ready_session(client, csrf, game)

    out_of_range = _result(client, csrf, session_id, value=game.score_max_value + 1)
    assert out_of_range.status_code == 400
    assert out_of_range.json()["code"] == "E_SCORE_RANGE"

    bad_duration = _result(client, csrf, session_id, duration_ms=1_000)
    assert bad_duration.status_code == 400
    assert bad_duration.json()["code"] == "E_DURATION_INVALID"
    assert not GameResult.objects.exists()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_lower_result_does_not_replace_best() -> None:
    game = _game(technical_id="better_result_game")
    user = User.objects.create_user(login="ivan", password="correct horse battery staple")
    client, csrf = _client(user)
    first_session = _ready_session(client, csrf, game)
    assert _result(client, csrf, first_session, key="k1", value=100).status_code == 200
    rival = User.objects.create_user(login="ivan_rival", password="correct horse battery staple")
    rival_client, rival_csrf = _client(rival)
    rival_session = _ready_session(rival_client, rival_csrf, game)
    assert _result(rival_client, rival_csrf, rival_session, key="r1", value=80).status_code == 200
    second_session = _ready_session(client, csrf, game)
    response = _result(client, csrf, second_session, key="k2", value=50)
    assert response.status_code == 200
    assert response.json()["is_personal_best"] is False
    # The user's board position is their best entry (100), not the
    # hypothetical position of this worse run (which would be 2).
    assert response.json()["rank"] == 1
    assert response.json()["is_record"] is False
    entry = LeaderboardEntry.objects.get(game=game, user=user)
    assert entry.value == 100


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_lower_is_better_replaces_best() -> None:
    game = _game(technical_id="lower_result_game", direction="lower_is_better")
    user = User.objects.create_user(login="judy", password="correct horse battery staple")
    client, csrf = _client(user)
    first_session = _ready_session(client, csrf, game)
    assert _result(client, csrf, first_session, key="k1", value=100).status_code == 200
    second_session = _ready_session(client, csrf, game)
    response = _result(client, csrf, second_session, key="k2", value=50)
    assert response.status_code == 200
    assert response.json()["is_personal_best"] is True
    assert response.json()["is_record"] is True
    assert LeaderboardEntry.objects.get(game=game, user=user).value == 50


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_disabled_leaderboard_keeps_result_without_entry() -> None:
    game = _game(technical_id="disabled_board_game")
    game.leaderboard_enabled = False
    game.save(update_fields=["leaderboard_enabled"])
    user = User.objects.create_user(login="mallory", password="correct horse battery staple")
    client, csrf = _client(user)
    session_id = _ready_session(client, csrf, game)
    response = _result(client, csrf, session_id)
    assert response.status_code == 200
    assert response.json()["rank"] is None
    assert response.json()["is_record"] is False
    assert GameResult.objects.filter(session_id=session_id).exists()
    assert not LeaderboardEntry.objects.exists()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_account_anonymisation_nulls_result_and_removes_entry() -> None:
    game = _game(technical_id="anonymise_result_game")
    user = User.objects.create_user(login="nina", password="correct horse battery staple")
    client, csrf = _client(user)
    session_id = _ready_session(client, csrf, game)
    assert _result(client, csrf, session_id).status_code == 200

    anonymize_user_results(user)
    result = GameResult.objects.get(session_id=session_id)
    assert result.subject_type == GameResult.SUBJECT_DELETED
    assert result.user_id is None
    assert not LeaderboardEntry.objects.filter(user=user).exists()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_result_endpoint_requires_csrf() -> None:
    game = _game(technical_id="csrf_result_game")
    user = User.objects.create_user(login="olga", password="correct horse battery staple")
    client, csrf = _client(user)
    session_id = _ready_session(client, csrf, game)
    response = _result(client, csrf, session_id, with_csrf=False)
    assert response.status_code == 403


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_result_throttle_returns_structured_error() -> None:
    game = _game(technical_id="throttle_result_game")
    user = User.objects.create_user(login="peter", password="correct horse battery staple")
    client, csrf = _client(user)
    session_id = _ready_session(client, csrf, game)
    key = f"throttle_results_user:{user.id}"
    try:
        caches["throttle"].set(key, [time.time()] * 60, timeout=3600)
        response = _result(client, csrf, session_id)
    finally:
        caches["throttle"].delete(key)
    assert response.status_code == 429
    assert response.json()["code"] == "E_RATE_LIMIT"


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_result_ip_throttle_returns_structured_error() -> None:
    game = _game(technical_id="throttle_ip_result_game")
    user = User.objects.create_user(login="peter_ip", password="correct horse battery staple")
    client, csrf = _client(user)
    session_id = _ready_session(client, csrf, game)
    key = "throttle_results_ip:127.0.0.1"
    try:
        caches["throttle"].set(key, [time.time()] * 1200, timeout=3600)
        response = _result(client, csrf, session_id)
    finally:
        caches["throttle"].delete(key)
    assert response.status_code == 429
    assert response.json()["code"] == "E_RATE_LIMIT"


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_invalid_content_length_returns_400() -> None:
    game = _game(technical_id="bad_content_length_game")
    user = User.objects.create_user(login="bad_cl", password="correct horse battery staple")
    client, csrf = _client(user)
    session_id = _ready_session(client, csrf, game)

    response = client.post(
        f"{API}/{session_id}/result",
        data=json.dumps({"value": 10, "durationMs": 30_000}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
        CONTENT_LENGTH="not-a-number",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "E_INVALID_REQUEST"


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_preview_result_is_test_and_not_on_leaderboard() -> None:
    game = _game(technical_id="preview_result_game")
    user = User.objects.create_user(login="rita", password="correct horse battery staple")
    now = timezone.now()
    session = GameSession.objects.create(
        game=game,
        game_version=game.current_version,
        subject_type=GameSession.SUBJECT_USER,
        subject_id=user.id,
        mode=GameSession.MODE_PREVIEW,
        state=GameSession.STATE_ACTIVE,
        seed="preview-seed",
        max_session_seconds=1800,
        credited_ms=30_000,
        activated_at=now - timedelta(seconds=30),
        last_heartbeat_at=now,
    )
    request = RequestFactory().post("/")
    request.user = user
    submit_result(
        request,
        session.id,
        idempotency_key="preview-key",
        value=100,
        duration_ms=30_000,
    )
    result = GameResult.objects.get(session=session)
    assert result.is_test is True
    assert not LeaderboardEntry.objects.exists()


@pytest.mark.django_db(transaction=True)
@override_settings(CACHES=LOCMEM_CACHES)
def test_hundred_parallel_results_keep_single_best() -> None:
    game = _game(technical_id="parallel_result_game")
    user = User.objects.create_user(login="quinn", password="correct horse battery staple")
    now = timezone.now()
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
            credited_ms=30_000,
            activated_at=now - timedelta(seconds=30),
            last_heartbeat_at=now,
        )
        for index in range(100)
    ]

    def worker(index: int) -> str:
        request = RequestFactory().post("/")
        request.user = user
        try:
            submit_result(
                request,
                sessions[index].id,
                idempotency_key=f"key-{index}",
                value=index,
                duration_ms=30_000,
            )
            return "ok"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = list(executor.map(worker, range(100)))
    assert outcomes.count("ok") == 100
    entries = LeaderboardEntry.objects.filter(game=game, epoch=game.leaderboard_epoch, user=user)
    assert entries.count() == 1
    assert entries.get().value == 99
    assert GameResult.objects.filter(session__in=sessions).count() == 100


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_eventlog_seed_and_event_kinds_are_validated() -> None:
    game = _game(technical_id="eventlog_game")
    user = User.objects.create_user(login="eventlog", password="correct horse battery staple")
    client, csrf = _client(user)
    session_id = _ready_session(client, csrf, game)
    session = GameSession.objects.get(pk=session_id)

    valid = _result(
        client,
        csrf,
        session_id,
        event_log={"v": 1, "seed": session.seed, "events": []},
    )
    assert valid.status_code == 200, valid.content

    wrong_session_id = _ready_session(client, csrf, game)
    wrong_seed = _result(
        client,
        csrf,
        wrong_session_id,
        key="eventlog-wrong-seed",
        event_log={"v": 1, "seed": "wrong", "events": []},
    )
    assert wrong_seed.status_code == 400
    assert wrong_seed.json()["code"] == "E_MESSAGE_INVALID"

    game = _game(technical_id="eventlog_kind_game")
    session_id = _ready_session(client, csrf, game)
    session = GameSession.objects.get(pk=session_id)
    undeclared = _result(
        client,
        csrf,
        session_id,
        key="eventlog-kind",
        event_log={
            "v": 1,
            "seed": session.seed,
            "events": [{"t": 0, "k": "not-declared", "d": {}}],
        },
    )
    assert undeclared.status_code == 400
    assert undeclared.json()["code"] == "E_MESSAGE_INVALID"

    invalid_schema = _result(
        client,
        csrf,
        session_id,
        key="eventlog-schema",
        event_log={"seed": session.seed, "events": []},
    )
    assert invalid_schema.status_code == 400
    assert invalid_schema.json()["code"] == "E_INVALID_REQUEST"


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_seed_mismatch_and_missing_idempotency_key_are_rejected() -> None:
    game = _game(technical_id="seed_result_game")
    user = User.objects.create_user(login="sam", password="correct horse battery staple")
    client, csrf = _client(user)
    session_id = _ready_session(client, csrf, game)
    wrong_seed = _result(client, csrf, session_id, seed="wrong-seed")
    assert wrong_seed.status_code == 400
    assert wrong_seed.json()["code"] == "E_MESSAGE_INVALID"

    missing_key = client.post(
        f"{API}/{session_id}/result",
        data=json.dumps({"value": 100, "durationMs": 30_000}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert missing_key.status_code == 400
    assert missing_key.json()["code"] == "E_INVALID_REQUEST"


def test_event_log_limits_are_enforced_by_serializer() -> None:
    too_many = SessionResultSerializer(
        data={"value": 1, "durationMs": 1000, "eventLog": {"events": [{}] * 20_001}}
    )
    assert not too_many.is_valid()
    not_object = SessionResultSerializer(data={"value": 1, "durationMs": 1000, "eventLog": []})
    assert not not_object.is_valid()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_verifier_marks_suspicious_result_quarantined() -> None:
    verification = {
        "profile": {"maxPointsPerSecond": 2, "maxIdleGapMs": 1000},
        "eventKinds": ["start", "eat"],
        "eventSchema": {"type": "object"},
    }
    game = _game(technical_id="verifier_game", verification=verification)
    user = User.objects.create_user(login="vera", password="correct horse battery staple")
    client, csrf = _client(user)
    session_id = _ready_session(client, csrf, game)
    session = GameSession.objects.get(pk=session_id)

    suspicious = _result(
        client,
        csrf,
        session_id,
        key="verifier-suspicious",
        value=100,
        duration_ms=30_000,
        seed=session.seed,
        event_log={
            "v": 1,
            "seed": session.seed,
            "events": [
                {"t": 0, "k": "start", "d": {}},
                {"t": 5000, "k": "eat", "d": {}},
            ],
        },
    )

    assert suspicious.status_code == 200
    assert suspicious.json()["status"] == "quarantined"
    result = GameResult.objects.get(session_id=session_id)
    assert result.is_quarantined is True
    assert result.trust_level == GameResult.TRUST_CLIENT_REPORTED
    assert "points_per_second" in result.verifier_flags["flags"]
    assert "idle_gap" in result.verifier_flags["flags"]
    assert not LeaderboardEntry.objects.filter(game=game, user=user).exists()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_verifier_accepts_valid_heuristic_result() -> None:
    verification = {
        "profile": {"maxPointsPerSecond": 10, "maxIdleGapMs": 1000},
        "eventKinds": ["start"],
        "eventSchema": {"type": "object"},
    }
    game = _game(technical_id="verifier_valid_game", verification=verification)
    user = User.objects.create_user(login="victor", password="correct horse battery staple")
    client, csrf = _client(user)
    session_id = _ready_session(client, csrf, game)
    session = GameSession.objects.get(pk=session_id)

    response = _result(
        client,
        csrf,
        session_id,
        key="verifier-valid",
        value=10,
        duration_ms=30_000,
        seed=session.seed,
        event_log={
            "v": 1,
            "seed": session.seed,
            "events": [{"t": 0, "k": "start", "d": {}}],
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "saved"
    result = GameResult.objects.get(session_id=session_id)
    assert result.is_quarantined is False
    assert result.trust_level == GameResult.TRUST_HEURISTIC_VALIDATED
    assert LeaderboardEntry.objects.filter(game=game, user=user).exists()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_profile_result_without_eventlog_is_quarantined() -> None:
    verification = {
        "profile": {"maxPointsPerSecond": 10, "maxIdleGapMs": 1000},
        "eventKinds": ["start"],
        "eventSchema": {"type": "object"},
    }
    game = _game(technical_id="missing_log_game", verification=verification)
    user = User.objects.create_user(login="missing_log", password="correct horse battery staple")
    client, csrf = _client(user)
    session_id = _ready_session(client, csrf, game)

    response = _result(client, csrf, session_id, key="missing-log", value=10)

    assert response.status_code == 200
    assert response.json()["status"] == "quarantined"
    result = GameResult.objects.get(session_id=session_id)
    assert result.is_quarantined is True
    assert "missing_event_log" in result.verifier_flags["flags"]
    assert not LeaderboardEntry.objects.filter(game=game, user=user).exists()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_profile_result_without_seed_is_quarantined() -> None:
    verification = {
        "profile": {"maxPointsPerSecond": 10, "maxIdleGapMs": 1000},
        "eventKinds": ["start"],
        "eventSchema": {"type": "object"},
    }
    game = _game(technical_id="missing_seed_game", verification=verification)
    user = User.objects.create_user(login="missing_seed", password="correct horse battery staple")
    client, csrf = _client(user)
    session_id = _ready_session(client, csrf, game)
    session = GameSession.objects.get(pk=session_id)

    response = _result(
        client,
        csrf,
        session_id,
        key="missing-seed",
        value=10,
        event_log={"v": 1, "seed": session.seed, "events": [{"t": 0, "k": "start", "d": {}}]},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "quarantined"
    result = GameResult.objects.get(session_id=session_id)
    assert result.is_quarantined is True
    assert "missing_seed" in result.verifier_flags["flags"]
    assert not LeaderboardEntry.objects.filter(game=game, user=user).exists()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_profile_result_with_blank_seed_is_quarantined() -> None:
    verification = {
        "profile": {"maxPointsPerSecond": 10, "maxIdleGapMs": 1000},
        "eventKinds": ["start"],
        "eventSchema": {"type": "object"},
    }
    game = _game(technical_id="blank_seed_game", verification=verification)
    user = User.objects.create_user(login="blank_seed", password="correct horse battery staple")
    client, csrf = _client(user)
    session_id = _ready_session(client, csrf, game)
    session = GameSession.objects.get(pk=session_id)

    response = _result(
        client,
        csrf,
        session_id,
        key="blank-seed",
        value=10,
        seed="",
        event_log={"v": 1, "seed": session.seed, "events": [{"t": 0, "k": "start", "d": {}}]},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "quarantined"
    result = GameResult.objects.get(session_id=session_id)
    assert result.is_quarantined is True
    assert "missing_seed" in result.verifier_flags["flags"]
    assert not LeaderboardEntry.objects.filter(game=game, user=user).exists()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_leaderboard_only_verified_skips_entry() -> None:
    game = _game(technical_id="verified_only_game")
    game.leaderboard_only_verified = True
    game.save(update_fields=["leaderboard_only_verified"])
    user = User.objects.create_user(login="tina", password="correct horse battery staple")
    client, csrf = _client(user)
    session_id = _ready_session(client, csrf, game)
    response = _result(client, csrf, session_id)
    assert response.status_code == 200
    assert response.json()["rank"] is None
    assert not LeaderboardEntry.objects.exists()
    assert GameResult.objects.filter(session_id=session_id).exists()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_result_trigger_rejects_mismatched_session_game() -> None:
    game = _game(technical_id="trigger_result_game")
    other = _game(technical_id="trigger_other_game")
    user = User.objects.create_user(login="uma", password="correct horse battery staple")
    client, csrf = _client(user)
    session_id = _ready_session(client, csrf, game)
    session = GameSession.objects.get(pk=session_id)
    with pytest.raises(DatabaseError), transaction.atomic():
        GameResult.objects.create(
            session=session,
            game=other,
            game_version=other.current_version,
            subject_type=GameResult.SUBJECT_USER,
            user=user,
            epoch=1,
            value=1,
            unit="points",
            duration_ms=30_000,
            idempotency_key="bad",
        )


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_leaderboard_trigger_rejects_foreign_result() -> None:
    game = _game(technical_id="trigger_board_game")
    first = User.objects.create_user(login="vera", password="correct horse battery staple")
    second = User.objects.create_user(login="walt", password="correct horse battery staple")

    def make_result(user: User, login: str) -> GameResult:
        client, csrf = _client(user)
        session_id = _ready_session(client, csrf, game)
        response = _result(client, csrf, session_id, key=f"key-{login}")
        assert response.status_code == 200
        return GameResult.objects.get(session_id=session_id)

    result_first = make_result(first, "vera")
    result_second = make_result(second, "walt")
    with pytest.raises(DatabaseError), transaction.atomic():
        LeaderboardEntry.objects.create(
            game=game,
            epoch=game.leaderboard_epoch,
            user=first,
            best_result=result_second,
            value=result_second.value,
            achieved_at=result_second.created_at,
            trust_level=GameResult.TRUST_CLIENT_REPORTED,
        )

    entry = LeaderboardEntry.objects.get(game=game, user=first)
    assert entry.best_result_id == result_first.id
    with pytest.raises(DatabaseError), transaction.atomic():
        entry.best_result = result_second
        entry.value = result_second.value
        entry.achieved_at = result_second.created_at
        entry.save()
