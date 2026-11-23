"""App F race and idempotency tests (§2.9, §2.11.2, §2.22).

These tests exercise the real service layer against PostgreSQL with several
threads; each thread uses its own connection, so the row/advisory locks that
guard production writes are the only thing serialising the race.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import timedelta

import pytest
from django.core.cache import caches
from django.db import connections
from django.test import RequestFactory, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Game, GameVersion, Genre
from apps.gameplay.models import (
    GameResult,
    GameSession,
    GameStorage,
    LeaderboardEntry,
    UserGamePlaytime,
)
from apps.gameplay.services.results import submit_result
from apps.gameplay.services.sessions import SessionError
from apps.gameplay.services.storage import put_storage
from apps.ratings.models import GameRatingVote
from apps.ratings.services.voting import vote

LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "throttle": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    caches["default"].clear()
    caches["throttle"].clear()
    yield
    caches["default"].clear()
    caches["throttle"].clear()


def _game(*, technical_id: str, direction: str = "higher_is_better") -> Game:
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
        rating_min_playtime_seconds=120,
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


def _user(login: str, game: Game | None = None) -> User:
    user = User.objects.create_user(login=login, password="correct horse battery staple")
    User.objects.filter(pk=user.pk).update(created_at=timezone.now() - timedelta(hours=2))
    user.refresh_from_db()
    if game is not None:
        UserGamePlaytime.objects.create(user=user, game=game, verified_seconds=120)
    return user


def _request(user: User):
    request = RequestFactory().post("/")
    request.user = user
    return request


def _active_session(user: User, game: Game, *, seed: str) -> GameSession:
    now = timezone.now()
    return GameSession.objects.create(
        game=game,
        game_version=game.current_version,
        subject_type=GameSession.SUBJECT_USER,
        subject_id=user.id,
        mode=GameSession.MODE_USER,
        state=GameSession.STATE_ACTIVE,
        seed=seed,
        max_session_seconds=1800,
        credited_ms=30_000,
        activated_at=now - timedelta(seconds=30),
        last_heartbeat_at=now,
    )


def _run_threads(workers: list[Callable[[], tuple[str, object]]]) -> list[tuple[str, object]]:
    """Run workers concurrently and collect ``("ok", payload)`` / ``("error", code)``."""
    outcomes: list[tuple[str, object]] = []
    failures: list[Exception] = []
    lock = threading.Lock()

    def wrap(worker: Callable[[], tuple[str, object]]) -> None:
        outcome: tuple[str, object] | None = None
        try:
            outcome = worker()
        except SessionError as exc:
            outcome = ("error", exc.code)
        except Exception as exc:  # noqa: BLE001 - re-raised on the test thread
            with lock:
                failures.append(exc)
        finally:
            connections.close_all()
        if outcome is not None:
            with lock:
                outcomes.append(outcome)

    threads = [threading.Thread(target=wrap, args=(worker,)) for worker in workers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads)
    if failures:
        raise failures[0]
    return outcomes


@pytest.mark.django_db(transaction=True)
@override_settings(CACHES=LOCMEM_CACHES)
@pytest.mark.parametrize(
    ("direction", "expected"),
    [("higher_is_better", "max"), ("lower_is_better", "min")],
)
def test_parallel_results_keep_single_best_entry(direction: str, expected: str) -> None:
    """§2.11.2: concurrent results never duplicate or lose the best value."""
    game = _game(technical_id=f"race_result_{direction}", direction=direction)
    user = _user(f"race_{direction}_u")
    count = 32
    sessions = [
        _active_session(user, game, seed=f"race-seed-{direction}-{index}") for index in range(count)
    ]
    values = list(range(count))
    boundary = threading.Barrier(count)

    def make_worker(session: GameSession, value: int) -> Callable[[], tuple[str, object]]:
        def worker() -> tuple[str, object]:
            boundary.wait(timeout=30)
            response = submit_result(
                _request(user),
                session.id,
                idempotency_key=f"key-{session.id}",
                value=value,
                duration_ms=30_000,
            )
            return ("ok", response)

        return worker

    outcomes = _run_threads(
        [make_worker(session, value) for session, value in zip(sessions, values, strict=True)]
    )
    assert [status for status, _ in outcomes] == ["ok"] * count
    assert GameResult.objects.filter(session__in=sessions).count() == count

    entries = LeaderboardEntry.objects.filter(game=game, epoch=game.leaderboard_epoch, user=user)
    assert entries.count() == 1
    entry = entries.get()
    best = max(values) if expected == "max" else min(values)
    assert entry.value == best
    assert entry.best_result.value == best
    # The winning row points at the actual result with the best value.
    best_result = GameResult.objects.get(session__in=sessions, value=best)
    assert entry.best_result_id == best_result.id


@pytest.mark.django_db(transaction=True)
@override_settings(CACHES=LOCMEM_CACHES)
def test_parallel_first_votes_keep_single_row_and_24h_limit() -> None:
    """§2.9: simultaneous first votes never violate UNIQUE(game_id, user_id)."""
    game = _game(technical_id="rating_race_first_vote")
    user = _user("rating_race_first_vote_user", game)
    values = [1, 2, 3, 4, 5]
    boundary = threading.Barrier(len(values))

    def make_worker(value: int) -> Callable[[], tuple[str, object]]:
        def worker() -> tuple[str, object]:
            boundary.wait(timeout=30)
            return ("ok", vote(_request(user), game.technical_id, value))

        return worker

    outcomes = _run_threads([make_worker(value) for value in values])
    winners = [payload for status, payload in outcomes if status == "ok"]
    errors = [payload for status, payload in outcomes if status == "error"]
    assert len(winners) == 1
    assert errors == ["E_RATE_LIMIT"] * (len(values) - 1)

    rows = GameRatingVote.objects.filter(game=game, user=user)
    assert rows.count() == 1
    row = rows.get()
    assert row.change_count_30d == 0
    assert row.value in values
    assert row.value == winners[0]["my_vote"]  # type: ignore[index]


@pytest.mark.django_db(transaction=True)
@override_settings(CACHES=LOCMEM_CACHES)
@pytest.mark.parametrize(
    ("initial_changes", "expected_changes", "expected_winners"),
    [(0, 1, 1), (4, 5, 1), (5, 5, 0)],
)
def test_parallel_rating_changes_stay_within_limits(
    initial_changes: int, expected_changes: int, expected_winners: int
) -> None:
    """§2.9: concurrent changes never exceed 1/24h, 5/30d or create a second row."""
    game = _game(technical_id=f"rating_race_change_{initial_changes}")
    user = _user(f"rating_race_change_{initial_changes}_user", game)
    now = timezone.now()
    GameRatingVote.objects.create(
        game=game,
        user=user,
        value=4,
        changed_at=now - timedelta(hours=25),
        change_count_30d=initial_changes,
        change_window_started_at=now - timedelta(days=10),
    )
    values = [1, 2, 3, 5]
    boundary = threading.Barrier(len(values))

    def make_worker(value: int) -> Callable[[], tuple[str, object]]:
        def worker() -> tuple[str, object]:
            boundary.wait(timeout=30)
            return ("ok", (value, vote(_request(user), game.technical_id, value)))

        return worker

    outcomes = _run_threads([make_worker(value) for value in values])
    winners = [payload for status, payload in outcomes if status == "ok"]
    errors = [payload for status, payload in outcomes if status == "error"]
    assert len(winners) == expected_winners
    assert errors == ["E_RATE_LIMIT"] * (len(values) - expected_winners)

    rows = GameRatingVote.objects.filter(game=game, user=user)
    assert rows.count() == 1
    row = rows.get()
    assert row.change_count_30d == expected_changes
    assert row.change_count_30d <= 5
    if expected_winners:
        assert row.value == winners[0][0]  # type: ignore[index]
    else:
        assert row.value == 4


@pytest.mark.django_db(transaction=True)
@override_settings(CACHES=LOCMEM_CACHES)
def test_concurrent_storage_updates_reject_stale_revision_without_corruption() -> None:
    """§2.22: only one writer wins a revision; a stale If-Match is rejected."""
    game = _game(technical_id="storage_race_game")
    user = _user("storage_race_user")
    _active_session(user, game, seed="storage-race-seed")
    request = _request(user)
    created = put_storage(request, game.technical_id, data={"writer": -1}, if_match="*")
    assert created == {"data": {"writer": -1}, "revision": 1}

    count = 8
    boundary = threading.Barrier(count)

    def make_worker(index: int) -> Callable[[], tuple[str, object]]:
        data = {"writer": index, "items": [index, index + 1]}

        def worker() -> tuple[str, object]:
            boundary.wait(timeout=30)
            response = put_storage(request, game.technical_id, data=data, if_match='"1"')
            return ("ok", (index, response))

        return worker

    outcomes = _run_threads([make_worker(index) for index in range(count)])
    winners = [payload for status, payload in outcomes if status == "ok"]
    errors = [payload for status, payload in outcomes if status == "error"]
    assert len(winners) == 1
    assert errors == ["E_STORAGE_CONFLICT"] * (count - 1)

    winner_index, response = winners[0]  # type: ignore[misc]
    row = GameStorage.objects.get(game=game, user=user)
    expected_data = {"writer": winner_index, "items": [winner_index, winner_index + 1]}
    assert row.revision == 2
    assert row.data == expected_data
    assert response == {"data": expected_data, "revision": 2}
    assert GameStorage.objects.filter(game=game, user=user).count() == 1

    # Replaying a stale ETag must not touch the winning document.
    with pytest.raises(SessionError) as excinfo:
        put_storage(request, game.technical_id, data={"writer": 99}, if_match='"1"')
    assert excinfo.value.code == "E_STORAGE_CONFLICT"
    row.refresh_from_db()
    assert row.revision == 2
    assert row.data == expected_data


@pytest.mark.django_db(transaction=True)
@override_settings(CACHES=LOCMEM_CACHES)
def test_concurrent_replay_of_idempotency_key_returns_single_outcome() -> None:
    """§2.11.3/§2.12: retrying one Idempotency-Key yields the stored outcome once."""
    game = _game(technical_id="idempotency_race_game")
    user = _user("idempotency_race_user")
    session = _active_session(user, game, seed="idempotency-race-seed")
    count = 8
    boundary = threading.Barrier(count)

    def worker() -> tuple[str, object]:
        boundary.wait(timeout=30)
        response = submit_result(
            _request(user),
            session.id,
            idempotency_key="shared-idempotency-key",
            value=42,
            duration_ms=30_000,
        )
        return ("ok", response)

    outcomes = _run_threads([worker] * count)
    assert [status for status, _ in outcomes] == ["ok"] * count
    responses = [payload for _, payload in outcomes]
    assert all(response == responses[0] for response in responses)
    first = responses[0]
    assert isinstance(first, dict)
    assert first["status"] == "saved"
    assert first["is_personal_best"] is True

    assert GameResult.objects.filter(session=session).count() == 1
    stored = GameResult.objects.get(session=session)
    assert stored.value == 42
    assert dict(stored.response) == first
    assert LeaderboardEntry.objects.filter(game=game, user=user).count() == 1
    session.refresh_from_db()
    assert session.state == GameSession.STATE_FINISHED
