from __future__ import annotations

import html
import json

import pytest
from django.test import Client
from django.utils import timezone

from apps.accounts.services.anonymous import COOKIE_NAME
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
def test_play_page_activates_guest_session_and_embeds_runtime() -> None:
    game = _game()
    client = Client()
    response = client.get("/en/games/play-runtime/play/")

    assert response.status_code == 200
    body = html.unescape(response.content.decode())
    assert "game-frame" in body
    assert "play-runtime.games.test" in body
    assert "/v/abcdef1234567890" + "0" * 48 + "/index.html" in body
    assert "#p=https%3A%2F%2Fportal.test%3A8443&s=" in body
    assert response["Cache-Control"] == "no-store"
    assert COOKIE_NAME in response.cookies

    session = GameSession.objects.get(game=game)
    assert session.state == GameSession.STATE_ACTIVE
    assert session.subject_type == GameSession.SUBJECT_ANON
    assert f"&s={session.id}" in body
    assert '"sessionId":' in body


@pytest.mark.django_db
def test_play_page_requires_current_version() -> None:
    _game(with_version=False)
    response = Client().get("/en/games/play-runtime/play/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_play_context_json_is_public_and_camel_case() -> None:
    _game()
    response = Client().get("/en/games/play-runtime/play/")
    assert response.status_code == 200
    raw_body = response.content.decode()
    marker = 'data-context="'
    start = raw_body.index(marker) + len(marker)
    end = raw_body.index('"', start)
    context = json.loads(html.unescape(raw_body[start:end]))
    assert context["sessionId"]
    assert context["gameId"] == "play_runtime"
    assert context["mode"] == "guest"
    assert "ticket" not in context
