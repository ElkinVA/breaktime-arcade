"""Permanent 301 redirects for changed game and translation slugs (§2.4.1, §2.6)."""

from __future__ import annotations

import pytest
from django.test import Client
from django.utils import timezone

from apps.catalog.models import Game, GameSlugHistory, GameTranslation, Genre
from apps.i18n.models import Language


def _genre(code: str) -> Genre:
    return Genre.objects.create(code=code)


def _game(*, technical_id: str, slug: str) -> Game:
    return Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=slug,
        primary_genre=_genre(f"genre_{technical_id}"),
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
    )


def _translation(game: Game, code: str, slug: str) -> GameTranslation:
    return GameTranslation.objects.create(
        game=game,
        language=Language.objects.get(code=code),
        name=f"Name {code}",
        slug=slug,
        short_description="Short",
        description="Description",
    )


@pytest.mark.django_db
def test_game_slug_change_records_old_slug_and_redirects() -> None:
    game = _game(technical_id="slug_game", slug="old-game-slug")

    game.slug = "new-game-slug"
    game.save()

    history = GameSlugHistory.objects.get(game=game)
    assert history.slug == "old-game-slug"
    assert history.language_id is None

    response = Client().get("/en/games/old-game-slug/")

    assert response.status_code == 301
    assert response["Location"] == "/en/games/new-game-slug/"
    assert Client().get("/en/games/new-game-slug/").status_code == 200


@pytest.mark.django_db
def test_translation_slug_change_records_old_slug_and_redirects_to_language() -> None:
    game = _game(technical_id="translated_slug_game", slug="translated-game")
    translation = _translation(game, "en", "old-localized-slug")
    _translation(game, "de", "de-current-slug")

    translation.slug = "new-localized-slug"
    # The importer persists translations with explicit update_fields.
    translation.save(update_fields=["slug", "updated_at"])

    history = GameSlugHistory.objects.get(game=game, language__code="en")
    assert history.slug == "old-localized-slug"

    response = Client().get("/en/games/old-localized-slug/")

    assert response.status_code == 301
    assert response["Location"] == "/en/games/new-localized-slug/"
    assert Client().get("/en/games/new-localized-slug/").status_code == 200


@pytest.mark.django_db
def test_multi_change_chain_redirects_to_current_slug() -> None:
    game = _game(technical_id="chained_slug_game", slug="chain-a")

    game.slug = "chain-b"
    game.save()
    game.slug = "chain-c"
    game.save()

    assert set(GameSlugHistory.objects.filter(game=game).values_list("slug", flat=True)) == {
        "chain-a",
        "chain-b",
    }

    client = Client()
    first = client.get("/en/games/chain-a/")
    second = client.get("/en/games/chain-b/")

    assert first.status_code == 301
    assert first["Location"] == "/en/games/chain-c/"
    assert second.status_code == 301
    assert second["Location"] == "/en/games/chain-c/"
    assert client.get("/en/games/chain-c/").status_code == 200


@pytest.mark.django_db
def test_unknown_slug_still_returns_404() -> None:
    _game(technical_id="known_slug_game", slug="known-game")

    response = Client().get("/en/games/never-existed/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_old_slug_of_unpublished_and_unknown_slugs_does_not_redirect() -> None:
    draft = _game(technical_id="draft_slug_game", slug="draft-old-slug")
    draft.status = Game.STATUS_DRAFT
    draft.published_at = None
    draft.save()
    draft.slug = "draft-new-slug"
    draft.save()
    assert GameSlugHistory.objects.filter(game=draft, slug="draft-old-slug").exists()

    assert Client().get("/en/games/draft-old-slug/").status_code == 404
