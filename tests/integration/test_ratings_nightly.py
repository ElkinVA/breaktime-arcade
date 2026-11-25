"""Nightly rating aggregate recalculation (§2.9)."""

from __future__ import annotations

import io
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Game, Genre
from apps.ratings.models import GameRatingAggregate, GameRatingVote
from apps.ratings.services import aggregates
from apps.ratings.services.aggregates import recalculate, recalculate_all
from apps.ratings.tasks import recalculate_rating_aggregates


def _game(technical_id: str, *, pk: UUID | None = None) -> Game:
    genre, _ = Genre.objects.get_or_create(code="nightly")
    return Game.objects.create(
        id=pk or uuid4(),
        technical_id=technical_id,
        host_label=f"{technical_id}.games.test",
        slug=f"slug-{technical_id}",
        primary_genre=genre,
    )


def _user(login: str) -> User:
    return User.objects.create_user(login=login, password="correct horse battery staple")


def _vote(game: Game, user: User, value: int) -> GameRatingVote:
    return GameRatingVote.objects.create(
        game=game,
        user=user,
        value=value,
        changed_at=timezone.now(),
        change_window_started_at=timezone.now(),
    )


@pytest.mark.django_db
def test_nightly_heals_directly_invalidated_vote() -> None:
    game = _game("nightly_invalid")
    alice = _user("nightly_alice")
    _vote(game, alice, 5)
    recalculate(game)
    GameRatingVote.objects.filter(game=game).update(is_valid=False)

    result = recalculate_all()

    aggregate = GameRatingAggregate.objects.get(game=game)
    assert result["updated"] == 1
    assert aggregate.count == 0
    assert aggregate.total == 0


@pytest.mark.django_db
def test_nightly_heals_directly_deactivated_user_vote() -> None:
    game = _game("nightly_inactive")
    alice = _user("nightly_alice")
    bob = _user("nightly_bob")
    _vote(game, alice, 5)
    _vote(game, bob, 3)
    aggregate = recalculate(game)
    assert aggregate.count == 2

    User.objects.filter(pk=bob.pk).update(is_active=False)

    result = recalculate_all()

    aggregate.refresh_from_db()
    assert result["updated"] == 1
    assert aggregate.count == 1
    assert float(aggregate.average) == 5.0


@pytest.mark.django_db
def test_nightly_zeroes_game_when_all_votes_are_excluded() -> None:
    game = _game("nightly_zero")
    alice = _user("nightly_alice")
    bob = _user("nightly_bob")
    _vote(game, alice, 5)
    _vote(game, bob, 3)
    recalculate(game)
    GameRatingVote.objects.filter(game=game).update(is_valid=False)

    first = recalculate_all()
    aggregate = GameRatingAggregate.objects.get(game=game)

    assert first["updated"] == 1
    assert aggregate.total == 0
    assert aggregate.count == 0
    assert aggregate.average == Decimal("0.00")
    assert aggregate.wr_score == 3.5
    assert aggregate.distribution == {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    stamped = aggregate.recalculated_at

    second = recalculate_all()

    assert second == {"scanned": 1, "updated": 0, "unchanged": 1, "failed": 0}
    aggregate.refresh_from_db()
    assert aggregate.recalculated_at == stamped


@pytest.mark.django_db
def test_nightly_union_of_votes_and_existing_aggregates() -> None:
    genre, _ = Genre.objects.get_or_create(code="nightly")
    voted = _game("nightly_voted")
    stale = _game("nightly_stale")
    untouched = _game("nightly_untouched")
    alice = _user("nightly_alice")
    _vote(voted, alice, 4)
    GameRatingAggregate.objects.create(
        game=stale,
        total=5,
        count=1,
        average=Decimal("5.00"),
        wr_score=4.8,
        distribution={"1": 0, "2": 0, "3": 0, "4": 0, "5": 1},
    )
    assert untouched.primary_genre_id == genre.id

    result = recalculate_all()

    assert result["scanned"] == 2
    assert result["updated"] == 2
    assert GameRatingAggregate.objects.get(game=voted).count == 1
    zeroed = GameRatingAggregate.objects.get(game=stale)
    assert zeroed.count == 0
    assert zeroed.average == Decimal("0.00")
    assert not GameRatingAggregate.objects.filter(game=untouched).exists()


@pytest.mark.django_db
def test_nightly_continues_after_one_game_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    broken = _game("nightly_broken", pk=UUID(int=1))
    healthy = _game("nightly_healthy", pk=UUID(int=2))
    alice = _user("nightly_alice")
    _vote(broken, alice, 5)
    _vote(healthy, alice, 4)
    real = aggregates._computed_values

    def flaky(game: Game) -> dict[str, object]:
        if game.pk == broken.pk:
            raise RuntimeError("boom")
        return real(game)

    monkeypatch.setattr(aggregates, "_computed_values", flaky)

    result = recalculate_all()

    assert result["failed"] == 1
    assert result["updated"] == 1
    assert not GameRatingAggregate.objects.filter(game=broken).exists()
    assert GameRatingAggregate.objects.get(game=healthy).count == 1


@pytest.mark.django_db
def test_nightly_processes_games_in_pk_order(monkeypatch: pytest.MonkeyPatch) -> None:
    genre, _ = Genre.objects.get_or_create(code="nightly")
    first = _game("nightly_first", pk=UUID(int=1))
    second = _game("nightly_second", pk=UUID(int=2))
    third = _game("nightly_third", pk=UUID(int=3))
    for position, game in enumerate((third, first, second), start=1):
        _vote(game, _user(f"nightly_user_{position}"), position)
    assert second.primary_genre_id == genre.id
    seen: list[UUID] = []
    monkeypatch.setattr(aggregates, "_lock", lambda game_id: seen.append(game_id))

    recalculate_all()

    assert seen == [first.id, second.id, third.id]


def test_nightly_task_and_beat_registration() -> None:
    entry = settings.CELERY_BEAT_SCHEDULE["ratings-nightly-recalc"]
    annotation = settings.CELERY_TASK_ANNOTATIONS[
        "apps.ratings.tasks.recalculate_rating_aggregates"
    ]

    assert entry["task"] == "apps.ratings.tasks.recalculate_rating_aggregates"
    assert entry["schedule"] == 60 * 60 * 24
    assert entry["options"] == {"expires": 60 * 60}
    assert recalculate_rating_aggregates.name == entry["task"]
    assert annotation["acks_late"] is True
    assert annotation["reject_on_worker_lost"] is True
    assert annotation["soft_time_limit"] == 2400
    assert annotation["time_limit"] == 3000


@pytest.mark.django_db
def test_recalculate_ratings_command_dry_run_and_apply() -> None:
    game = _game("nightly_command")
    alice = _user("nightly_alice")
    _vote(game, alice, 5)
    recalculate(game)
    _vote(game, _user("nightly_bob"), 3)

    dry_output = io.StringIO()
    call_command("recalculate_ratings", "--dry-run", stdout=dry_output)

    assert "would_update=1" in dry_output.getvalue()
    assert GameRatingAggregate.objects.get(game=game).count == 1

    output = io.StringIO()
    call_command("recalculate_ratings", stdout=output)

    assert "updated=1" in output.getvalue()
    assert GameRatingAggregate.objects.get(game=game).count == 2


@pytest.mark.django_db
def test_recalculate_ratings_command_reports_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "apps.ratings.management.commands.recalculate_ratings.recalculate_all",
        lambda **kwargs: {"scanned": 2, "updated": 1, "unchanged": 0, "failed": 1},
    )

    with pytest.raises(CommandError):
        call_command("recalculate_ratings")
    # A dry-run must not hide failures from CI smoke checks either.
    with pytest.raises(CommandError):
        call_command("recalculate_ratings", "--dry-run")
    with pytest.raises(CommandError):
        call_command("recalculate_ratings", "--limit", "0")


@pytest.mark.django_db
def test_nightly_dry_run_takes_no_locks_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = _game("nightly_dry")
    _vote(game, _user("nightly_alice"), 5)
    aggregate = recalculate(game)
    _vote(game, _user("nightly_bob"), 3)
    locks: list[UUID] = []
    monkeypatch.setattr(aggregates, "_lock", lambda game_id: locks.append(game_id))

    result = recalculate_all(apply=False)

    assert result["updated"] == 1
    assert locks == []
    aggregate.refresh_from_db()
    assert aggregate.count == 1


@pytest.mark.django_db
def test_nightly_propagates_soft_time_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    game = _game("nightly_soft_limit")
    _vote(game, _user("nightly_alice"), 5)

    def timeout(game: Game) -> dict[str, object]:
        raise SoftTimeLimitExceeded

    monkeypatch.setattr(aggregates, "_computed_values", timeout)

    with pytest.raises(SoftTimeLimitExceeded):
        recalculate_all()
