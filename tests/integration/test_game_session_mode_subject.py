from __future__ import annotations

from uuid import uuid4

import pytest
from django.db import IntegrityError, transaction

from apps.catalog.models import Game, GameVersion, Genre
from apps.gameplay.models import GamePlayCredit, GameSession
from apps.gameplay.services.popularity import credit_session


def _game() -> Game:
    genre = Genre.objects.create(code="mode_subject")
    game = Game.objects.create(
        technical_id="mode_subject",
        host_label="mode-subject.games.test",
        slug="mode-subject",
        primary_genre=genre,
    )
    version = GameVersion.objects.create(
        game=game,
        semver="1.0.0",
        package_hash="a" * 64,
        runtime_hash="b" * 64,
        sdk_version="1.1.0",
        size_bytes=1,
        manifest={},
        supported_languages=["en"],
    )
    game.current_version = version
    game.save(update_fields=["current_version"])
    return game


def _session(game: Game, *, mode: str, subject_type: str) -> GameSession:
    return GameSession.objects.create(
        game=game,
        game_version=game.current_version,
        subject_type=subject_type,
        subject_id=uuid4(),
        mode=mode,
        seed="seed",
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("mode", "subject_type"),
    [
        (GameSession.MODE_USER, GameSession.SUBJECT_USER),
        (GameSession.MODE_GUEST, GameSession.SUBJECT_ANON),
        (GameSession.MODE_PREVIEW, GameSession.SUBJECT_USER),
        (GameSession.MODE_PREVIEW, GameSession.SUBJECT_ANON),
        (GameSession.MODE_AUTOTEST, GameSession.SUBJECT_USER),
    ],
)
def test_valid_mode_subject_combinations(mode: str, subject_type: str) -> None:
    game = _game()
    session = _session(game, mode=mode, subject_type=subject_type)
    assert session.mode == mode
    assert session.subject_type == subject_type


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("mode", "subject_type"),
    [
        (GameSession.MODE_USER, GameSession.SUBJECT_ANON),
        (GameSession.MODE_GUEST, GameSession.SUBJECT_USER),
        (GameSession.MODE_AUTOTEST, GameSession.SUBJECT_ANON),
    ],
)
def test_invalid_mode_subject_combinations_are_rejected(mode: str, subject_type: str) -> None:
    game = _game()
    with pytest.raises(IntegrityError), transaction.atomic():
        _session(game, mode=mode, subject_type=subject_type)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "mode",
    [
        GameSession.MODE_USER,
        GameSession.MODE_GUEST,
        GameSession.MODE_PREVIEW,
        GameSession.MODE_AUTOTEST,
    ],
)
def test_tombstoned_subject_is_allowed_for_any_mode(mode: str) -> None:
    game = _game()
    session = _session(game, mode=mode, subject_type=GameSession.SUBJECT_DELETED)
    assert session.subject_type == GameSession.SUBJECT_DELETED


@pytest.mark.django_db
def test_preview_and_autotest_do_not_credit_popularity() -> None:
    game = _game()
    preview = _session(
        game,
        mode=GameSession.MODE_PREVIEW,
        subject_type=GameSession.SUBJECT_USER,
    )
    autotest = _session(
        game,
        mode=GameSession.MODE_AUTOTEST,
        subject_type=GameSession.SUBJECT_USER,
    )

    assert credit_session(preview, duration_ms=30_000, completed=True) is False
    assert credit_session(autotest, duration_ms=30_000, completed=True) is False
    assert not GamePlayCredit.objects.exists()
