"""Rating vote UI on the public game detail page (§2.9)."""

from __future__ import annotations

import json
import re
from datetime import timedelta

import pytest
from django.core.cache import caches
from django.test import Client, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Game, GameVersion, Genre
from apps.gameplay.models import UserGamePlaytime
from apps.ratings.models import GameRatingVote
from apps.ratings.services.aggregates import recalculate

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


def _game(*, technical_id: str = "rating_ui_game", min_seconds: int = 120) -> Game:
    genre = Genre.objects.create(code=f"genre_{technical_id}")
    game = Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=f"slug-{technical_id}",
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
        rating_min_playtime_seconds=min_seconds,
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


def _user(login: str, game: Game | None = None, *, seconds: int = 120) -> User:
    user = User.objects.create_user(login=login, password="correct horse battery staple")
    User.objects.filter(pk=user.pk).update(created_at=timezone.now() - timedelta(hours=2))
    user.refresh_from_db()
    if game is not None:
        UserGamePlaytime.objects.create(user=user, game=game, verified_seconds=seconds)
    return user


def _detail(game: Game) -> str:
    return f"/en/games/{game.slug}/"


def _form_value(content: str, value: int) -> bool:
    return bool(
        re.search(
            rf'<input[^>]*name="value"[^>]*value="{value}"[^>]*checked',
            content,
        )
    )


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_eligible_user_sees_one_to_five_rating_form() -> None:
    game = _game()
    user = _user("eligible", game, seconds=120)
    client = Client()
    client.force_login(user)

    response = client.get(_detail(game))
    content = response.content.decode()

    assert response.status_code == 200
    assert 'data-testid="rating-form"' in content
    assert f"/api/v1/games/{game.technical_id}/rating" in content
    assert 'name="csrfmiddlewaretoken"' in content
    for value in range(1, 6):
        assert f'data-testid="rating-vote-{value}"' in content
    assert 'data-testid="rating-guest-invitation"' not in content
    assert 'data-testid="rating-playtime-required"' not in content
    assert 'data-testid="rating-submit"' in content


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_guest_sees_registration_invitation_and_no_vote_form() -> None:
    game = _game(technical_id="rating_guest_game")

    response = Client().get(_detail(game))
    content = response.content.decode()

    assert response.status_code == 200
    assert 'data-testid="rating-guest-invitation"' in content
    assert "/en/auth/register/" in content
    assert 'data-testid="rating-form"' not in content
    assert 'data-testid="rating-vote-1"' not in content
    assert 'data-testid="rating-submit"' not in content
    assert f"/api/v1/games/{game.technical_id}/rating" not in content


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
@pytest.mark.parametrize("seconds", [0, 119])
def test_user_below_playtime_threshold_sees_requirement_not_form(seconds: int) -> None:
    game = _game(technical_id=f"rating_below_{seconds}_game", min_seconds=120)
    user = _user(f"below_{seconds}", game, seconds=seconds)
    client = Client()
    client.force_login(user)

    content = client.get(_detail(game)).content.decode()

    assert 'data-testid="rating-playtime-required"' in content
    assert 'data-testid="rating-form"' not in content
    assert "120" in content
    assert f"{seconds} s" in content


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_playtime_threshold_is_inclusive_for_the_widget() -> None:
    game = _game(technical_id="rating_threshold_game", min_seconds=90)
    user = _user("threshold", game, seconds=90)
    client = Client()
    client.force_login(user)

    content = client.get(_detail(game)).content.decode()

    assert 'data-testid="rating-form"' in content
    assert 'data-testid="rating-playtime-required"' not in content


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_existing_vote_is_preselected_and_summary_is_visible() -> None:
    game = _game(technical_id="rating_preselected_game")
    user = _user("preselected", game)
    GameRatingVote.objects.create(
        game=game,
        user=user,
        value=3,
        changed_at=timezone.now(),
        change_window_started_at=timezone.now(),
    )
    recalculate(game)

    client = Client()
    client.force_login(user)
    content = client.get(_detail(game)).content.decode()

    assert _form_value(content, 3)
    assert not _form_value(content, 5)
    assert 'data-testid="rating-average">3.00<' in content
    assert 'data-testid="rating-count">1<' in content


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_vote_can_be_submitted_from_the_detail_page_context() -> None:
    game = _game(technical_id="rating_page_submit_game")
    user = _user("page_voter", game)
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)

    page = client.get(_detail(game))
    match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.content.decode())
    assert match is not None

    response = client.post(
        f"/api/v1/games/{game.technical_id}/rating",
        data=json.dumps({"value": 5}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=match.group(1),
    )

    assert response.status_code == 200, response.content
    assert response.json()["my_vote"] == 5
    assert _form_value(client.get(_detail(game)).content.decode(), 5)
