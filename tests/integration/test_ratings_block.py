"""Blocked accounts disappear from rating aggregates immediately (§2.9 item 4)."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest
from django.test import RequestFactory
from django.utils import timezone

from apps.accounts.models import User, UserProfile
from apps.catalog.models import Game, Genre
from apps.crm.services.users import block_user, unblock_user
from apps.gameplay.models import UserGamePlaytime
from apps.gameplay.services.sessions import SessionError
from apps.ratings.models import GameRatingAggregate, GameRatingVote
from apps.ratings.services.aggregates import recalculate
from apps.ratings.services.voting import vote

PASSWORD = "correct horse battery staple"


def _user(login: str) -> User:
    user = User.objects.create_user(login=login, password=PASSWORD)
    UserProfile.objects.create(
        user=user,
        nickname=login,
        nickname_skeleton=login.lower(),
    )
    return user


def _game(technical_id: str = "ratings_block_game", game_id: UUID | None = None) -> Game:
    genre = Genre.objects.create(code=f"genre_{technical_id}")
    fields: dict[str, object] = {
        "technical_id": technical_id,
        "host_label": f"{technical_id.replace('_', '-')}.games.test",
        "slug": f"slug-{technical_id}",
        "primary_genre": genre,
        "status": Game.STATUS_PUBLISHED,
        "published_at": timezone.now(),
    }
    if game_id is not None:
        fields["id"] = game_id
    return Game.objects.create(**fields)


@pytest.mark.django_db
def test_block_excludes_votes_and_unblock_restores_them() -> None:
    owner = _user("ratings_owner")
    target = _user("ratings_target")
    game = _game()
    GameRatingVote.objects.create(game=game, user=target, value=5)
    aggregate = recalculate(game)
    assert aggregate.count == 1
    assert aggregate.total == 5

    blocked = block_user(actor=owner, target_id=target.id)
    assert blocked.ok and blocked.changed
    aggregate.refresh_from_db()
    assert aggregate.count == 0
    assert aggregate.total == 0
    assert aggregate.distribution == {str(star): 0 for star in range(1, 6)}

    unblocked = unblock_user(actor=owner, target_id=target.id)
    assert unblocked.ok and unblocked.changed
    aggregate.refresh_from_db()
    assert aggregate.count == 1
    assert aggregate.total == 5


@pytest.mark.django_db
def test_vote_rechecks_active_flag_under_the_account_lock() -> None:
    user = _user("ratings_stale")
    User.objects.filter(pk=user.pk).update(created_at=timezone.now() - timedelta(hours=2))
    game = _game("ratings_stale_game")
    UserGamePlaytime.objects.create(user=user, game=game, verified_seconds=600)
    stale_user = User.objects.get(pk=user.pk)
    User.objects.filter(pk=user.pk).update(is_active=False)

    request = RequestFactory().post("/api/v1/games/x/rating")
    request.user = stale_user

    with pytest.raises(SessionError) as exc:
        vote(request, game.technical_id, 5)
    assert exc.value.code == "E_AUTH_REQUIRED"
    assert not GameRatingVote.objects.filter(game=game, user=user).exists()


@pytest.mark.django_db
def test_block_recalculates_all_games_in_deterministic_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.ratings.services import aggregates

    owner = _user("ratings_order_owner")
    target = _user("ratings_order_target")
    # UUIDv4 values chosen so creation order is 4, 1, 3 while lock order must
    # be 1, 3, 4; UUIDv7 creation order would mask an insertion-order bug.
    game_ids = [
        UUID("00000000-0000-4000-8000-000000000004"),
        UUID("00000000-0000-4000-8000-000000000001"),
        UUID("00000000-0000-4000-8000-000000000003"),
    ]
    games = [
        _game(f"ratings_order_{index}", game_id=game_id) for index, game_id in enumerate(game_ids)
    ]
    for game in games:
        GameRatingVote.objects.create(game=game, user=target, value=4)
    order: list[object] = []
    monkeypatch.setattr(aggregates, "recalculate", lambda game: order.append(game.pk))

    result = block_user(actor=owner, target_id=target.id)

    assert result.ok and result.changed
    assert order == sorted(game_ids)


@pytest.mark.django_db
def test_blocked_user_cannot_vote_and_non_voter_unblock_is_safe() -> None:
    owner = _user("ratings_no_votes_owner")
    target = _user("ratings_no_votes_target")
    game = _game("ratings_no_votes_game")
    assert block_user(actor=owner, target_id=target.id).ok
    blocked = User.objects.get(pk=target.pk)
    request = RequestFactory().post("/api/v1/games/x/rating")
    request.user = blocked
    with pytest.raises(SessionError) as exc:
        vote(request, game.technical_id, 5)
    assert exc.value.code == "E_AUTH_REQUIRED"
    assert unblock_user(actor=owner, target_id=target.id).ok
    assert not GameRatingAggregate.objects.filter(game=game).exists()


@pytest.mark.django_db
def test_recalculate_ignores_blocked_votes() -> None:
    user = _user("ratings_blocked_only")
    game = _game("ratings_blocked_only_game")
    GameRatingVote.objects.create(game=game, user=user, value=4)
    User.objects.filter(pk=user.pk).update(is_active=False)

    aggregate = recalculate(game)

    assert aggregate.count == 0
    assert GameRatingAggregate.objects.get(game=game).count == 0
