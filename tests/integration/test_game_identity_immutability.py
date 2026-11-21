from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.utils import timezone

from apps.catalog.models import Game, Genre


def _game(*, published: bool = False) -> Game:
    genre = Genre.objects.create(code="identity_immutability")
    return Game.objects.create(
        technical_id="identity_immutability",
        host_label="identity-immutability.games.test",
        slug="identity-immutability",
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED if published else Game.STATUS_DRAFT,
        published_at=timezone.now() if published else None,
    )


@pytest.mark.django_db
def test_identity_can_change_before_publication() -> None:
    game = _game()
    game.technical_id = "identity_changed"
    game.host_label = "identity-changed.games.test"
    game.save()

    game.refresh_from_db()
    assert game.technical_id == "identity_changed"
    assert game.host_label == "identity-changed.games.test"


@pytest.mark.django_db
def test_draft_identity_raw_update_is_allowed() -> None:
    game = _game()
    Game.objects.filter(pk=game.pk).update(technical_id="identity_changed")

    game.refresh_from_db()
    assert game.technical_id == "identity_changed"


@pytest.mark.django_db
def test_identity_is_immutable_after_publication() -> None:
    game = _game(published=True)
    game.technical_id = "identity_changed"

    with pytest.raises(ValidationError):
        game.save()


@pytest.mark.django_db
def test_database_trigger_blocks_published_identity_update() -> None:
    game = _game(published=True)

    with pytest.raises(DatabaseError), transaction.atomic():
        Game.objects.filter(pk=game.pk).update(technical_id="identity_changed")


@pytest.mark.django_db
def test_game_delete_is_forbidden() -> None:
    game = _game()

    with pytest.raises(DatabaseError), transaction.atomic():
        game.delete()

    assert Game.objects.filter(pk=game.pk).exists()
