"""Block-vs-vote race against real PostgreSQL locks (§2.9 items 4-5).

``vote`` checks ``is_active`` on the in-memory request user before it opens a
transaction, then re-checks the flag under ``SELECT ... FOR UPDATE``. The CRM
block flips the flag under the same row lock and recalculates every affected
aggregate before committing. Whichever thread wins, a committed block must
leave no contribution from the blocked account.
"""

from __future__ import annotations

import threading
import unittest
from datetime import timedelta
from unittest import mock

import pytest
from django.db import connection, connections
from django.test import RequestFactory, TransactionTestCase
from django.utils import timezone

from apps.accounts.models import User, UserProfile
from apps.catalog.models import Game, Genre
from apps.crm.services import users as crm_users
from apps.gameplay.models import UserGamePlaytime
from apps.gameplay.services.sessions import SessionError
from apps.ratings.models import GameRatingAggregate, GameRatingVote
from apps.ratings.services import voting
from apps.ratings.services.voting import vote

PASSWORD = "correct horse battery staple"


def _user(login: str) -> User:
    user = User.objects.create_user(login=login, password=PASSWORD)
    UserProfile.objects.create(
        user=user,
        nickname=login,
        nickname_skeleton=login.lower(),
    )
    User.objects.filter(pk=user.pk).update(created_at=timezone.now() - timedelta(hours=2))
    user.refresh_from_db()
    return user


def _game(technical_id: str) -> Game:
    genre = Genre.objects.create(code=f"genre_{technical_id}")
    return Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=f"slug-{technical_id}",
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
    )


def _request(user: User):
    request = RequestFactory().post("/")
    request.user = user
    return request


@unittest.skipUnless(
    connection.vendor == "postgresql",
    "race semantics depend on PostgreSQL row and advisory locks",
)
@pytest.mark.django_db(transaction=True)
class TestRatingBlockRace(TransactionTestCase):
    databases = {"default"}

    def test_block_committed_after_vote_early_check_rejects_vote(self) -> None:
        """A block that commits after the in-memory check still rejects the vote.

        The vote thread is parked after its early ``is_active`` check and before
        its transaction. The block thread then commits in full. When the vote
        resumes, the ``SELECT ... FOR UPDATE`` re-check must observe the flag and
        raise ``E_AUTH_REQUIRED`` without writing a vote or an aggregate.
        """
        user = _user("race_after_check_user")
        owner = _user("race_after_check_owner")
        game = _game("race_after_check")
        UserGamePlaytime.objects.create(user=user, game=game, verified_seconds=600)

        barrier = threading.Barrier(2)
        vote_reached_early_check = threading.Event()
        release_vote = threading.Event()
        outcomes: list[tuple[str, object]] = []
        errors: list[Exception] = []
        guard = threading.Lock()
        original_published_game = voting._published_game

        def pausing_published_game(game_id: str) -> Game:
            vote_reached_early_check.set()
            if not release_vote.wait(timeout=30):
                raise AssertionError("vote was never released")
            return original_published_game(game_id)

        def vote_worker() -> None:
            try:
                barrier.wait(timeout=30)
                try:
                    vote(_request(user), game.technical_id, 5)
                except SessionError as exc:
                    with guard:
                        outcomes.append(("error", exc.code))
                else:
                    with guard:
                        outcomes.append(("ok", None))
            except Exception as exc:  # noqa: BLE001 - surfaced on the test thread
                with guard:
                    errors.append(exc)
            finally:
                connections.close_all()

        def block_worker() -> None:
            try:
                barrier.wait(timeout=30)
                if not vote_reached_early_check.wait(timeout=30):
                    raise AssertionError("vote never reached its early auth check")
                result = crm_users.block_user(actor=owner, target_id=user.id)
                if not (result.ok and result.changed):
                    raise AssertionError(f"block failed: {result}")
            except Exception as exc:  # noqa: BLE001 - surfaced on the test thread
                with guard:
                    errors.append(exc)
            finally:
                connections.close_all()

        with mock.patch.object(voting, "_published_game", pausing_published_game):
            vote_thread = threading.Thread(target=vote_worker, name="rating-vote")
            block_thread = threading.Thread(target=block_worker, name="crm-block")
            vote_thread.start()
            block_thread.start()
            block_thread.join(timeout=60)
            block_alive = block_thread.is_alive()
            release_vote.set()
            vote_thread.join(timeout=60)
            vote_alive = vote_thread.is_alive()

        assert not block_alive
        assert not vote_alive
        if errors:
            raise errors[0]

        assert outcomes == [("error", "E_AUTH_REQUIRED")]
        assert not GameRatingVote.objects.filter(game=game, user=user).exists()
        assert not GameRatingAggregate.objects.filter(game=game).exists()
        user.refresh_from_db()
        assert user.is_active is False

    def test_vote_committed_before_block_is_excluded_from_aggregate(self) -> None:
        """A vote that wins the row lock is recalculated out once the block commits.

        The vote thread pauses inside its transaction after taking the account
        row lock and inserting the vote, so the block thread must wait for it.
        When the vote commits, the block proceeds and its recalculation must
        leave the aggregate without the blocked account's vote.
        """
        user = _user("race_vote_first_user")
        owner = _user("race_vote_first_owner")
        game = _game("race_vote_first")
        UserGamePlaytime.objects.create(user=user, game=game, verified_seconds=600)

        barrier = threading.Barrier(2)
        vote_holds_account_lock = threading.Event()
        block_attempted = threading.Event()
        release_vote = threading.Event()
        outcomes: list[str] = []
        errors: list[Exception] = []
        guard = threading.Lock()
        original_recalculate = voting.recalculate

        def pausing_recalculate(game_obj: Game) -> GameRatingAggregate:
            vote_holds_account_lock.set()
            if not release_vote.wait(timeout=30):
                raise AssertionError("vote was never released")
            return original_recalculate(game_obj)

        def vote_worker() -> None:
            try:
                barrier.wait(timeout=30)
                vote(_request(user), game.technical_id, 5)
                with guard:
                    outcomes.append("ok")
            except SessionError as exc:
                with guard:
                    outcomes.append(exc.code)
            except Exception as exc:  # noqa: BLE001 - surfaced on the test thread
                with guard:
                    errors.append(exc)
            finally:
                connections.close_all()

        def block_worker() -> None:
            try:
                barrier.wait(timeout=30)
                if not vote_holds_account_lock.wait(timeout=30):
                    raise AssertionError("vote never reached its aggregate recalculation")
                block_attempted.set()
                result = crm_users.block_user(actor=owner, target_id=user.id)
                if not (result.ok and result.changed):
                    raise AssertionError(f"block failed: {result}")
            except Exception as exc:  # noqa: BLE001 - surfaced on the test thread
                with guard:
                    errors.append(exc)
            finally:
                connections.close_all()

        with mock.patch.object(voting, "recalculate", pausing_recalculate):
            vote_thread = threading.Thread(target=vote_worker, name="rating-vote")
            block_thread = threading.Thread(target=block_worker, name="crm-block")
            vote_thread.start()
            block_thread.start()
            try:
                if not vote_holds_account_lock.wait(timeout=30):
                    raise AssertionError("vote never reached its aggregate recalculation")
                if not block_attempted.wait(timeout=30):
                    raise AssertionError("block never attempted the account update")
            finally:
                release_vote.set()
                vote_thread.join(timeout=60)
                vote_alive = vote_thread.is_alive()
                block_thread.join(timeout=60)
                block_alive = block_thread.is_alive()

        assert not vote_alive
        assert not block_alive
        if errors:
            raise errors[0]

        assert outcomes == ["ok"]
        assert GameRatingVote.objects.filter(game=game, user=user).exists()
        aggregate = GameRatingAggregate.objects.get(game=game)
        assert aggregate.count == 0
        assert aggregate.total == 0
        assert aggregate.distribution == {str(star): 0 for star in range(1, 6)}
        user.refresh_from_db()
        assert user.is_active is False
