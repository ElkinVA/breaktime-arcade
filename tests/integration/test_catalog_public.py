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


def _game(
    *,
    technical_id: str,
    slug: str,
    genre: Genre,
    status: str = Game.STATUS_PUBLISHED,
    mobile: bool = True,
    minutes: int = 5,
    name: str = "Game",
    translation_slug: str | None = None,
) -> Game:
    game = Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=slug,
        primary_genre=genre,
        status=status,
        published_at=timezone.now() if status == Game.STATUS_PUBLISHED else None,
        mobile_support=mobile,
        estimated_play_minutes=minutes,
    )
    for language in Language.objects.filter(code__in=["en", "de"]):
        GameTranslation.objects.create(
            game=game,
            language=language,
            name=f"{name} {language.code}",
            slug=(translation_slug or slug) + f"-{language.code}",
            short_description=f"Short {language.code}",
            description=f"Description {language.code}",
        )
    return game


@pytest.mark.django_db
def test_catalog_lists_only_published_games_and_filters() -> None:
    puzzle = _genre("puzzle", "Puzzle", "puzzle")
    arcade = _genre("arcade", "Arcade", "arcade")
    _game(
        technical_id="pub_game",
        slug="pub-game",
        genre=puzzle,
        mobile=True,
        minutes=5,
    )
    _game(
        technical_id="draft_game",
        slug="draft-game",
        genre=arcade,
        status=Game.STATUS_DRAFT,
    )
    client = Client()

    all_games = client.get("/en/games/")
    assert all_games.status_code == 200
    assert "/en/games/pub-game/" in all_games.content.decode()
    assert "/en/games/draft-game/" not in all_games.content.decode()

    filtered = client.get("/en/games/?genre=puzzle&mobile=1&duration=short")
    assert filtered.status_code == 200
    assert "/en/games/pub-game/" in filtered.content.decode()

    wrong_duration = client.get("/en/games/?duration=epic")
    assert "/en/games/pub-game/" not in wrong_duration.content.decode()


@pytest.mark.django_db
def test_catalog_filters_by_additional_genre_and_tags() -> None:
    primary = _genre("puzzle", "Puzzle", "puzzle")
    additional = _genre("strategy", "Strategy", "strategy")
    tag = _tag("retro", "Retro")
    game = _game(technical_id="tagged_game", slug="tagged-game", genre=primary)
    game.additional_genres.add(additional)
    game.tags.add(tag)
    client = Client()

    by_additional = client.get("/en/games/?genre=strategy")
    by_tag = client.get("/en/games/?tag=retro")

    assert "/en/games/tagged-game/" in by_additional.content.decode()
    assert "/en/games/tagged-game/" in by_tag.content.decode()
    assert "Retro-en" in by_tag.content.decode()
    genre_page = client.get("/en/genres/strategy-en/")
    assert "/en/games/tagged-game/" in genre_page.content.decode()


@pytest.mark.django_db
def test_catalog_search_requires_two_characters_and_matches_translation() -> None:
    genre = _genre("logic", "Logic", "logic")
    _game(
        technical_id="search_game",
        slug="search-game",
        genre=genre,
        name="UniqueWord",
    )
    client = Client()

    one_char = client.get("/en/games/?q=U")
    assert one_char.status_code == 200
    assert "UniqueWord en" not in one_char.content.decode()

    match = client.get("/en/games/?q=Unique")
    assert match.status_code == 200
    assert "UniqueWord en" in match.content.decode()


@pytest.mark.django_db
def test_catalog_fts_matches_terms_across_name_and_description() -> None:
    genre = _genre("platformer", "Platformer", "platformer")
    _game(
        technical_id="fts_game",
        slug="fts-game",
        genre=genre,
        name="Alpha Beta",
    )
    GameTranslation.objects.filter(game__technical_id="fts_game", language__code="en").update(
        description="Gamma Delta"
    )
    client = Client()

    response = client.get("/en/games/?q=Alpha+Gamma")

    assert response.status_code == 200
    assert "/en/games/fts-game/" in response.content.decode()
    assert (
        GameTranslation.objects.get(
            game__technical_id="fts_game", language__code="en"
        ).search_vector
        is not None
    )


@pytest.mark.django_db
def test_catalog_search_unaccents_diacritics_and_refresh_task() -> None:
    genre = _genre("simulator", "Simulator", "simulator")
    _game(
        technical_id="accent_game",
        slug="accent-game",
        genre=genre,
        name="Café",
    )
    translation = GameTranslation.objects.get(game__technical_id="accent_game", language__code="en")
    GameTranslation.objects.filter(pk=translation.pk).update(search_vector=None)

    from apps.catalog.tasks import refresh_catalog_search_vectors

    assert refresh_catalog_search_vectors() >= 1
    translation.refresh_from_db()
    assert translation.search_vector is not None

    response = Client().get("/en/games/?q=Cafe")
    assert response.status_code == 200
    assert "/en/games/accent-game/" in response.content.decode()


@pytest.mark.django_db
def test_catalog_detail_accepts_game_and_translation_slug_and_hides_draft() -> None:
    genre = _genre("casual", "Casual", "casual")
    _game(
        technical_id="detail_game",
        slug="detail-game",
        genre=genre,
        translation_slug="localized-detail",
    )
    client = Client()

    by_game = client.get("/en/games/detail-game/")
    by_translation = client.get("/en/games/localized-detail-en/")
    assert by_game.status_code == 200
    assert by_translation.status_code == 200
    assert "Game en" in by_game.content.decode()

    draft = _game(
        technical_id="draft_detail",
        slug="draft-detail",
        genre=genre,
        status=Game.STATUS_DRAFT,
    )
    assert client.get(f"/en/games/{draft.slug}/").status_code == 404
    assert client.get("/en/games/unknown-game/").status_code == 404


@pytest.mark.django_db
def test_catalog_falls_back_to_english_and_escapes_user_content() -> None:
    genre = _genre("strategy", "Strategy", "strategy")
    _game(
        technical_id="fallback_game",
        slug="fallback-game",
        genre=genre,
        name="<script>alert(1)</script>",
    )
    client = Client()

    german = client.get("/de/games/fallback-game/")

    assert german.status_code == 200
    content = german.content.decode()
    assert "<script>alert(1)</script>" not in content
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in content


@pytest.mark.django_db
def test_genre_page_and_htmx_partial() -> None:
    genre = _genre("racing", "Racing", "racing")
    _game(technical_id="race_game", slug="race-game", genre=genre)
    client = Client()

    genre_page = client.get("/en/genres/racing-en/")
    assert genre_page.status_code == 200
    assert "/en/games/race-game/" in genre_page.content.decode()

    partial = client.get("/en/games/?genre=racing", HTTP_HX_REQUEST="true")
    assert partial.status_code == 200
    assert "<html" not in partial.content.decode()
    assert "/en/games/race-game/" in partial.content.decode()
