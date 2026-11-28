"""Home genre discovery block and home SEO (§2.6/§2.19)."""

from __future__ import annotations

import pytest
from django.conf import settings
from django.core.cache import caches
from django.test import Client, override_settings

from apps.catalog import views as catalog_views
from apps.catalog.models import Genre, GenreTranslation
from apps.i18n.models import Language

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


def _genre(code: str, name_en: str, slug_en: str, name_ru: str, slug_ru: str, order: int) -> Genre:
    genre = Genre.objects.create(code=code, sort_order=order)
    en = Language.objects.get(code="en")
    ru = Language.objects.get(code="ru")
    GenreTranslation.objects.create(genre=genre, language=en, name=name_en, slug=slug_en)
    GenreTranslation.objects.create(genre=genre, language=ru, name=name_ru, slug=slug_ru)
    return genre


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_home_genres_render_localized_links_in_sort_order() -> None:
    _genre("puzzle", "Puzzle", "puzzle-en", "Головоломки", "puzzle-ru", 10)
    _genre("arcade", "Arcade", "arcade-en", "Аркады", "arcade-ru", 20)

    english = Client().get("/en/")
    assert english.status_code == 200
    content = english.content.decode()
    assert 'data-testid="home-genres"' in content
    assert 'href="/en/genres/puzzle-en/"' in content
    assert 'href="/en/genres/arcade-en/"' in content
    block_start = content.index('data-testid="home-genres"')
    block = content[block_start : content.index("</nav>", block_start)]
    assert block.index("Puzzle") < block.index("Arcade")
    assert 'data-testid="home-genre-link"' in content
    origin = settings.PORTAL_ORIGIN.rstrip("/")
    assert f'<link rel="canonical" href="{origin}/en/">' in content
    assert "Play short browser games instantly" in content
    assert "<title>Breaktime Arcade — short browser games</title>" in content
    assert 'hreflang="x-default"' in content

    russian = Client().get("/ru/")
    assert russian.status_code == 200
    russian_content = russian.content.decode()
    assert 'href="/ru/genres/puzzle-ru/"' in russian_content
    assert "Головоломки" in russian_content
    assert "Играйте в короткие браузерные игры" in russian_content
    assert "Breaktime Arcade — короткие игры в браузере" in russian_content
    assert "Puzzle" not in russian_content


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_home_genres_block_is_omitted_when_no_genres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(catalog_views, "genre_options", lambda language_code: [])
    response = Client().get("/en/")
    assert response.status_code == 200
    content = response.content.decode()
    assert 'data-testid="home-genres"' not in content
    assert 'data-testid="home-popular"' in content
    assert 'data-testid="home-rated"' in content
