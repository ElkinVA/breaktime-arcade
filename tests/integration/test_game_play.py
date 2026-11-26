from __future__ import annotations

import pytest
from django.test import Client
from django.utils import timezone

from apps.catalog.models import Game, GameVersion, Genre
from apps.gameplay.models import GameSession


def _game(*, with_version: bool = True) -> Game:
    genre = Genre.objects.create(code="play_runtime")
    game = Game.objects.create(
        technical_id="play_runtime",
        host_label="play-runtime.games.test",
        slug="play-runtime",
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
    )
    if with_version:
        version = GameVersion.objects.create(
            game=game,
            semver="1.0.0",
            package_hash="a" * 64,
            runtime_hash="abcdef1234567890" + "0" * 48,
            sdk_version="1.1.0",
            size_bytes=1,
            manifest={},
            supported_languages=["en"],
        )
        game.current_version = version
        game.save(update_fields=["current_version"])
    return game


@pytest.mark.django_db
def test_play_page_does_not_create_or_embed_a_session() -> None:
    game = _game()
    client = Client()
    response = client.get("/en/games/play-runtime/play/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "game-frame" in body
    assert "play-runtime.games.test" in body
    assert "/v/abcdef1234567890" + "0" * 48 + "/index.html" in body
    assert "#p=https%3A%2F%2Fportal.test%3A8443" in body
    assert "&s=" not in body
    assert "data-context=" not in body
    assert "data-session-id=" not in body
    assert response["Cache-Control"] == "no-store"
    assert "ba_anon" not in response.cookies
    assert not GameSession.objects.filter(game=game).exists()


@pytest.mark.django_db
def test_play_page_requires_current_version() -> None:
    _game(with_version=False)
    response = Client().get("/en/games/play-runtime/play/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_play_shell_has_no_session_or_ticket_material() -> None:
    _game()
    response = Client().get("/en/games/play-runtime/play/")
    assert response.status_code == 200
    body = response.content.decode()
    assert "ticket" not in body
    assert "sessionId" not in body
    assert not GameSession.objects.exists()


@pytest.mark.django_db
def test_play_page_pins_the_site_language_for_the_session_api() -> None:
    from django.conf import settings

    _game()
    response = Client().get("/ru/games/play-runtime/play/")

    assert response.status_code == 200
    assert response.cookies[settings.LANGUAGE_COOKIE_NAME].value == "ru"
