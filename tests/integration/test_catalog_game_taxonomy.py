"""Localized genres and tags on the public game detail page (§2.2/§2.8)."""

from __future__ import annotations

import pytest
from django.test import Client
from django.utils import timezone

from apps.catalog.models import (
    Game,
    GameTranslation,
    Genre,
    GenreTranslation,
    Tag,
    TagTranslation,
)
from apps.i18n.models import Language


def _genre(code: str, name: str, slug: str) -> Genre:
    genre = Genre.objects.create(code=code)
    for language in Language.objects.filter(code__in=["en", "de"]):
        GenreTranslation.objects.create(
            genre=genre,
            language=language,
            name=f"{name}-{language.code}",
            slug=f"{slug}-{language.code}",
        )
    return genre


def _tag(code: str, name: str) -> Tag:
    tag = Tag.objects.create(code=code)
    for language in Language.objects.filter(code__in=["en", "de"]):
        TagTranslation.objects.create(
            tag=tag,
            language=language,
            name=f"{name}-{language.code}",
            slug=f"{code}-{language.code}",
        )
    return tag


def _game(*, technical_id: str, genre: Genre) -> Game:
    slug = technical_id.replace("_", "-")
    game = Game.objects.create(
        technical_id=technical_id,
        host_label=f"{slug}.games.test",
        slug=slug,
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
    )
    for language in Language.objects.filter(code__in=["en", "de"]):
        GameTranslation.objects.create(
            game=game,
            language=language,
            name=f"{technical_id} {language.code}",
            slug=f"{slug}-{language.code}",
            short_description=f"Short {language.code}",
            description=f"Description {language.code}",
        )
    return game


@pytest.mark.django_db
def test_game_detail_renders_localized_genres_and_tags_with_links() -> None:
    primary = _genre("puzzle", "Puzzle", "puzzle")
    additional = _genre("strategy", "Strategy", "strategy")
    tag = _tag("retro", "Retro")
    game = _game(technical_id="taxonomy_game", genre=primary)
    game.additional_genres.add(additional)
    game.tags.add(tag)
    client = Client()

    english = client.get("/en/games/taxonomy-game/")
    content = english.content.decode()

    assert english.status_code == 200
    assert 'data-testid="game-taxonomy"' in content
    assert 'href="/en/genres/puzzle-en/"' in content
    assert "Puzzle-en" in content
    assert 'href="/en/genres/strategy-en/"' in content
    assert "Strategy-en" in content
    assert 'href="/en/games/?tag=retro"' in content
    assert "Retro-en" in content
    assert ">strategy<" not in content
    assert ">retro<" not in content
    assert client.get("/en/genres/strategy-en/").status_code == 200
    tagged = client.get("/en/games/?tag=retro")
    assert "/en/games/taxonomy-game/" in tagged.content.decode()

    german = client.get("/de/games/taxonomy-game/")
    german_content = german.content.decode()

    assert german.status_code == 200
    assert 'href="/de/genres/puzzle-de/"' in german_content
    assert 'href="/de/genres/strategy-de/"' in german_content
    assert 'href="/de/games/?tag=retro"' in german_content
    assert "Puzzle-de" in german_content
    assert "Strategy-de" in german_content
    assert "Retro-de" in german_content


@pytest.mark.django_db
def test_game_detail_without_additional_genres_or_tags_has_no_taxonomy_block() -> None:
    primary = _genre("casual", "Casual", "casual")
    _game(technical_id="plain_game", genre=primary)
    client = Client()

    response = client.get("/en/games/plain-game/")
    content = response.content.decode()

    assert response.status_code == 200
    assert 'data-testid="game-taxonomy"' not in content
    assert "/en/genres/" not in content
    assert "?tag=" not in content
    # The existing primary-genre breadcrumb is unchanged.
    assert "· casual" in content


@pytest.mark.django_db
def test_game_detail_taxonomy_falls_back_to_english_per_term() -> None:
    primary = _genre("logic", "Logic", "logic")
    additional = Genre.objects.create(code="puzzle")
    GenreTranslation.objects.create(
        genre=additional,
        language=Language.objects.get(code="en"),
        name="Puzzle EN only",
        slug="puzzle-en-only",
    )
    game = _game(technical_id="fallback_taxonomy_game", genre=primary)
    game.additional_genres.add(additional)

    response = Client().get("/de/games/fallback-taxonomy-game/")
    content = response.content.decode()

    assert response.status_code == 200
    assert 'href="/de/genres/puzzle-en-only/"' in content
    assert "Puzzle EN only" in content
    assert Client().get("/de/genres/puzzle-en-only/").status_code == 200
