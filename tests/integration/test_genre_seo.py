"""Genre landing page discovery, sorting and SEO (§2.6/§2.8/§2.19)."""

from __future__ import annotations

from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from django.conf import settings
from django.test import Client, override_settings
from django.utils import timezone
from django.utils.html import escape

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


def _genre_variant(
    code: str,
    *,
    name_en: str,
    slug_en: str,
    name_ru: str,
    slug_ru: str,
    order: int = 10,
) -> Genre:
    genre = Genre.objects.create(code=code, sort_order=order)
    en = Language.objects.get(code="en")
    ru = Language.objects.get(code="ru")
    GenreTranslation.objects.create(genre=genre, language=en, name=name_en, slug=slug_en)
    GenreTranslation.objects.create(genre=genre, language=ru, name=name_ru, slug=slug_ru)
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
    assert 'href="/en/genres/logic-en/"' in english_switcher.content.decode()

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


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_cross_language_redirect_preserves_query_and_canonical_matches_page_language() -> None:
    genre = _genre()
    now = timezone.now()
    for index in range(25):
        _game(
            f"logic-{index:02d}",
            genre,
            published_at=now - timedelta(minutes=index),
        )

    english = Client().get("/en/genres/logika/?sort=old&page=2&utm_source=e2e")

    assert english.status_code == 301
    assert english["Location"] == "/en/genres/logic-en/?sort=old&page=2&utm_source=e2e"
    english_page = Client().get(english["Location"])
    assert english_page.status_code == 200
    origin = settings.PORTAL_ORIGIN.rstrip("/")
    english_canonical = english_page.context["seo"].canonical_url
    english_parts = urlsplit(english_canonical)
    assert english_canonical.startswith(f"{origin}/en/genres/logic-en/?")
    assert english_parts.path == "/en/genres/logic-en/"
    assert parse_qs(english_parts.query) == {
        "sort": ["old"],
        "page": ["2"],
        "utm_source": ["e2e"],
    }
    assert (
        f'<link rel="canonical" href="{escape(english_canonical)}">'
        in english_page.content.decode()
    )
    assert f'hreflang="en" href="{origin}/en/genres/logic-en/"' in english_page.content.decode()

    russian = Client().get("/ru/genres/logic-en/?sort=old&page=2")

    assert russian.status_code == 301
    assert russian["Location"] == "/ru/genres/logika/?sort=old&page=2"
    russian_page = Client().get(russian["Location"])
    assert russian_page.status_code == 200
    russian_canonical = russian_page.context["seo"].canonical_url
    russian_parts = urlsplit(russian_canonical)
    assert russian_parts.path == "/ru/genres/logika/"
    assert parse_qs(russian_parts.query) == {"sort": ["old"], "page": ["2"]}
    assert f'hreflang="ru" href="{origin}/ru/genres/logika/"' in russian_page.content.decode()


@pytest.mark.django_db
@override_settings(CACHES=LOCMEM_CACHES)
def test_ambiguous_genre_slug_is_deterministic_and_switcher_keeps_the_same_genre() -> None:
    _genre_variant(
        "alpha",
        name_en="Alpha",
        slug_en="shared",
        name_ru="Альфа",
        slug_ru="alfa",
        order=1,
    )
    _genre_variant(
        "beta",
        name_en="Beta",
        slug_en="beta-en",
        name_ru="Бета",
        slug_ru="shared",
        order=2,
    )

    english = Client().get("/en/genres/shared/")
    assert english.status_code == 200
    english_content = english.content.decode()
    assert "<h1" in english_content and "Alpha" in english_content
    assert "Beta" not in english_content
    assert urlsplit(english.context["seo"].canonical_url).path == "/en/genres/shared/"

    russian = Client().get("/ru/genres/shared/?sort=old")
    assert russian.status_code == 200
    russian_content = russian.content.decode()
    assert "<h1" in russian_content and "Бета" in russian_content
    assert "Альфа" not in russian_content
    assert urlsplit(russian.context["seo"].canonical_url).path == "/ru/genres/shared/"
    # A path-prefix swap would point at /en/genres/shared/, which is Alpha.
    # The genre page therefore supplies its own localized alternates.
    assert 'href="/en/genres/beta-en/?sort=old"' in russian_content

    beta = Client().get("/en/genres/beta-en/")
    assert beta.status_code == 200
    assert "Beta" in beta.content.decode()
    assert 'href="/ru/genres/shared/"' in beta.content.decode()

    alpha = Client().get("/ru/genres/alfa/")
    assert alpha.status_code == 200
    assert "Альфа" in alpha.content.decode()
    assert 'href="/en/genres/shared/"' in alpha.content.decode()

    old_language_path = Client().get("/en/genres/alfa/")
    assert old_language_path.status_code == 301
    assert old_language_path["Location"] == "/en/genres/shared/"
