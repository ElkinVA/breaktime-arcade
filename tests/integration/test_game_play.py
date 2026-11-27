from __future__ import annotations

import re

import pytest
from django.core.cache import caches
from django.test import Client, override_settings
from django.utils import timezone

from apps.catalog.models import Game, GameVersion, Genre
from apps.gameplay.models import GameSession
from apps.i18n.models import Language

LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "throttle": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


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


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_play_page_injects_localized_start_error_for_each_active_locale() -> None:
    _game()
    active_codes = list(
        Language.objects.filter(is_active=True)
        .order_by("sort_order", "code")
        .values_list("code", flat=True)
    )
    assert {"en", "ru"} <= set(active_codes)
    expected = {
        "en": "Could not start the game",
        "ru": "Не удалось начать игру",
    }

    for code in active_codes:
        caches["default"].clear()
        response = Client().get(f"/{code}/games/play-runtime/play/")
        assert response.status_code == 200
        match = re.search(r'data-start-error="([^"]*)"', response.content.decode())
        assert match is not None, f"start-error attribute missing for {code}"
        # Locales without a published entry receive the English fallback (§2.15).
        assert match.group(1), f"empty start-error message for {code}"
        if code in expected:
            assert match.group(1) == expected[code]
        else:
            assert match.group(1) == expected["en"]
