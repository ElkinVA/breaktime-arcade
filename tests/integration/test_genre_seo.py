"""Genre landing page discovery, sorting and SEO (§2.6/§2.8/§2.19)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.conf import settings
from django.test import Client, override_settings
from django.utils import timezone

from apps.catalog.models import Game, Genre, GenreTranslation
from apps.i18n.models import Language

LOCMEM_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "throttle": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    from django.core.cache import caches

    caches["default"].clear()
    caches["throttle"].clear()
    yield
    caches["default"].clear()
    caches["throttle"].clear()


def _genre(*, with_ru: bool = True) -> Genre:
    genre = Genre.objects.create(code="logic", sort_order=1)
    en = Language.objects.get(code="en")
    GenreTranslation.objects.create(
        genre=genre,
        language=en,
        name="Logic",
        slug="logic-en",
        description="Deduction and planning games.",
        seo_title="Logic games",
        seo_description="Solve deduction and planning games.",
    )
    if with_ru:
        ru = Language.objects.get(code="ru")
        GenreTranslation.objects.create(
            genre=genre,
            language=ru,
            name="Логика",
            slug="logika",
            description="Игры на дедукцию и планирование.",
            seo_title="Логические игры",
            seo_description="Игры на дедукцию и планирование.",
        )
    return genre


def _game(slug: str, genre: Genre, *, published_at) -> Game:
    return Game.objects.create(
        technical_id=slug.replace("-", "_"),
        host_label=f"{slug}.games.test",
        slug=slug,
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED,
        published_at=published_at,
    )


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_genre_page_renders_localized_description_count_sort_and_seo() -> None:
    genre = _genre()
    _game("logic-old", genre, published_at=timezone.now() - timedelta(days=2))
    _game("logic-new", genre, published_at=timezone.now() - timedelta(days=1))

    response = Client().get("/en/genres/logic-en/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "<h1" in content and "Logic" in content
    assert "Deduction and planning games." in content
    assert 'data-testid="genre-game-count"' in content
    assert "2 games" in content
    assert 'id="genre-sort"' in content
    assert 'href="/en/games/?genre=logic"' in content
    assert 'href="/en/genres/logic-en/"' in content
    assert 'hreflang="ru"' in content
    assert 'hreflang="x-default"' in content
    assert "BreadcrumbList" in content
    assert "CollectionPage" in content
    assert "Logic games" in content

    old = Client().get("/en/genres/logic-en/?sort=old")
    old_content = old.content.decode()
    assert old_content.index("logic-old") < old_content.index("logic-new")

    russian = Client().get("/ru/genres/logika/")
    assert russian.status_code == 200
    assert "Логика" in russian.content.decode()
    assert "Игры на дедукцию и планирование." in russian.content.decode()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_genre_page_falls_back_to_english_and_handles_no_games() -> None:
    _genre(with_ru=False)

    response = Client().get("/ru/genres/logic-en/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Logic" in content
    assert "0 игр" in content
    assert "The catalog is being filled" in content


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_genre_page_canonical_uses_portal_origin() -> None:
    _genre()
    content = Client().get("/en/genres/logic-en/").content.decode()
    origin = settings.PORTAL_ORIGIN.rstrip("/")
    assert f'<link rel="canonical" href="{origin}/en/genres/logic-en/">' in content


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_genre_language_switcher_slug_redirects_to_canonical_language_slug() -> None:
    _genre()

    english_switcher = Client().get("/ru/genres/logika/")
    assert english_switcher.status_code == 200
    assert 'href="/en/genres/logika/"' in english_switcher.content.decode()

    redirected = Client().get("/en/genres/logika/")
    assert redirected.status_code == 301
    assert redirected["Location"] == "/en/genres/logic-en/"

    russian_redirect = Client().get("/ru/genres/logic-en/")
    assert russian_redirect.status_code == 301
    assert russian_redirect["Location"] == "/ru/genres/logika/"

    canonical = Client().get("/en/genres/logic-en/")
    assert canonical.status_code == 200
    origin = settings.PORTAL_ORIGIN.rstrip("/")
    canonical_content = canonical.content.decode()
    assert f'href="{origin}/en/genres/logic-en/"' in canonical_content
    assert f'hreflang="ru" href="{origin}/ru/genres/logika/"' in canonical_content
