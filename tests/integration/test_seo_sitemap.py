from __future__ import annotations

from collections.abc import Iterator

import pytest
from django.conf import settings
from django.test import Client
from django.utils import timezone

from apps.catalog.models import Game, GameTranslation, Genre, GenreTranslation
from apps.i18n.models import Language
from apps.i18n.services.language_registry import invalidate_language_cache


@pytest.fixture(autouse=True)
def _fresh_language_cache() -> Iterator[None]:
    """Sitemap/middleware must not see a language list cached by another test."""
    invalidate_language_cache()
    yield
    invalidate_language_cache()


def _origin() -> str:
    return settings.PORTAL_ORIGIN.rstrip("/")


def _genre(code: str, slugs: dict[str, str]) -> Genre:
    genre = Genre.objects.create(code=code)
    for language_code, slug in slugs.items():
        GenreTranslation.objects.create(
            genre=genre,
            language=Language.objects.get(code=language_code),
            name=f"{code}-{language_code}",
            slug=slug,
        )
    return genre


def _game(
    *,
    technical_id: str,
    slug: str,
    genre: Genre,
    status: str = Game.STATUS_PUBLISHED,
    translation_slugs: dict[str, str] | None = None,
) -> Game:
    game = Game.objects.create(
        technical_id=technical_id,
        host_label=f"{technical_id.replace('_', '-')}.games.test",
        slug=slug,
        primary_genre=genre,
        status=status,
        published_at=timezone.now() if status == Game.STATUS_PUBLISHED else None,
    )
    for language_code, translation_slug in (translation_slugs or {}).items():
        GameTranslation.objects.create(
            game=game,
            language=Language.objects.get(code=language_code),
            name=f"{technical_id} {language_code}",
            slug=translation_slug,
            short_description=f"Short {language_code}",
            description=f"Description {language_code}",
        )
    return game


@pytest.mark.django_db
def test_sitemap_index_lists_one_entry_per_active_language() -> None:
    Language.objects.create(code="it", name="Italiano", sort_order=90, is_active=True)
    Language.objects.filter(code="fr").update(is_active=False)
    invalidate_language_cache()

    response = Client().get("/sitemap.xml")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/xml")
    body = response.content.decode()
    active_codes = list(
        Language.objects.filter(is_active=True)
        .order_by("sort_order", "code")
        .values_list("code", flat=True)
    )
    assert body.count("<sitemap>") == len(active_codes)
    for code in active_codes:
        assert f"<loc>{_origin()}/{code}/sitemap.xml</loc>" in body
    assert f"{_origin()}/fr/sitemap.xml" not in body


@pytest.mark.django_db
def test_language_sitemap_lists_localized_urls_for_published_games_only() -> None:
    genre = _genre("puzzle", {"en": "puzzle-en", "de": "puzzle-de"})
    _game(
        technical_id="published_game",
        slug="published-game",
        genre=genre,
        translation_slugs={"en": "published-game-en", "de": "published-game-de"},
    )
    _game(
        technical_id="draft_game",
        slug="draft-game",
        genre=genre,
        status=Game.STATUS_DRAFT,
        translation_slugs={"en": "draft-game-en", "de": "draft-game-de"},
    )
    client = Client()

    english = client.get("/en/sitemap.xml")

    assert english.status_code == 200
    assert english["Content-Type"].startswith("application/xml")
    english_body = english.content.decode()
    assert f"<loc>{_origin()}/en/</loc>" in english_body
    assert f"<loc>{_origin()}/en/games/</loc>" in english_body
    assert f"<loc>{_origin()}/en/games/published-game-en/</loc>" in english_body
    assert f"<loc>{_origin()}/en/genres/puzzle-en/</loc>" in english_body
    assert "published-game/" not in english_body
    assert "draft-game" not in english_body

    german = client.get("/de/sitemap.xml")

    assert german.status_code == 200
    german_body = german.content.decode()
    assert f"<loc>{_origin()}/de/games/published-game-de/</loc>" in german_body
    assert f"<loc>{_origin()}/de/genres/puzzle-de/</loc>" in german_body
    assert "published-game-en/" not in german_body


@pytest.mark.django_db
def test_language_sitemap_is_not_served_for_inactive_language() -> None:
    Language.objects.filter(code="fr").update(is_active=False)
    invalidate_language_cache()

    assert Client().get("/fr/sitemap.xml").status_code == 404


@pytest.mark.django_db
def test_robots_txt_disallows_private_and_play_urls_and_references_sitemap() -> None:
    response = Client().get("/robots.txt")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/plain")
    body = response.content.decode()
    assert "User-agent: *" in body
    assert "Disallow: /account/" in body
    assert "Disallow: /crm/" in body
    assert "Disallow: /*/games/*/play/" in body
    assert f"Sitemap: {_origin()}/sitemap.xml" in body
