"""Pagination and sort persistence on the public genre detail page (§2.19)."""

from __future__ import annotations

import html
import re
from datetime import timedelta

import pytest
from django.conf import settings
from django.test import Client
from django.utils import timezone

from apps.catalog.models import Game, Genre, GenreTranslation
from apps.catalog.services import pagination as pagination_service
from apps.i18n.models import Language

CANONICAL_RE = re.compile(r'<link rel="canonical" href="([^"]+)"')
ROBOTS_RE = re.compile(r'<meta name="robots" content="([^"]+)"')


def _genre(code: str, slug: str) -> Genre:
    genre = Genre.objects.create(code=code)
    GenreTranslation.objects.create(
        genre=genre,
        language=Language.objects.get(code="en"),
        name=f"{code.title()} en",
        slug=slug,
    )
    return genre


def _games(count: int, genre: Genre, *, prefix: str) -> list[Game]:
    """Published games with strictly increasing publication time."""
    base = timezone.now() - timedelta(days=count)
    return Game.objects.bulk_create(
        [
            Game(
                technical_id=f"{prefix}_{index:03d}",
                host_label=f"{prefix}-{index:03d}.games.test",
                slug=f"{prefix}-{index:03d}",
                primary_genre=genre,
                status=Game.STATUS_PUBLISHED,
                published_at=base + timedelta(minutes=index),
                mobile_support=True,
                estimated_play_minutes=5,
            )
            for index in range(count)
        ]
    )


def _canonical(response) -> str:
    match = CANONICAL_RE.search(response.content.decode())
    assert match is not None, "canonical link is missing"
    return html.unescape(match.group(1))


@pytest.mark.django_db
def test_page_bounds_clamp_instead_of_erroring() -> None:
    genre = _genre("genre-bounds", "genre-bounds-en")
    _games(30, genre, prefix="gbound")

    client = Client()
    for value in ["0", "-3", "abc", "1.5", "", " "]:
        response = client.get("/en/genres/genre-bounds-en/", {"page": value})
        assert response.status_code == 200, value
        assert response.context["page_obj"].number == 1, value
        assert "/en/games/gbound-029/" in response.content.decode(), value

    beyond = client.get("/en/genres/genre-bounds-en/?page=999")
    assert beyond.status_code == 200
    assert beyond.context["page_obj"].number == 2
    body = beyond.content.decode()
    assert "/en/games/gbound-000/" in body
    assert "/en/games/gbound-029/" not in body


@pytest.mark.django_db
def test_out_of_range_page_maps_to_the_last_page() -> None:
    genre = _genre("genre-last", "genre-last-en")
    _games(30, genre, prefix="glast")

    response = Client().get("/en/genres/genre-last-en/?page=1000")

    assert response.status_code == 200
    page_obj = response.context["page_obj"]
    assert page_obj.number == page_obj.paginator.num_pages == 2
    assert "/en/games/glast-000/" in response.content.decode()


@pytest.mark.django_db
def test_pagination_preserves_active_sort_and_filters() -> None:
    genre = _genre("genre-sort", "genre-sort-en")
    _games(60, genre, prefix="gsort")

    response = Client().get("/en/genres/genre-sort-en/?sort=old&duration=short&mobile=1&page=2")

    assert response.status_code == 200
    body = response.content.decode()
    assert 'data-testid="pagination"' in body
    # Oldest-first page 2 starts at gsort_024.
    assert "/en/games/gsort-024/" in body
    assert "/en/games/gsort-023/" not in body
    # Page links keep the active sort and filters.
    assert 'href="?sort=old&amp;duration=short&amp;mobile=1&amp;page=3"' in body
    assert 'href="?sort=old&amp;duration=short&amp;mobile=1&amp;page=1"' in body
    # Sort and filters survive the navigation targets too (no HTMX on genre).
    assert "sort=old&amp;duration=short&amp;mobile=1&amp;page=3" in body


@pytest.mark.django_db
def test_single_page_genre_has_no_pagination_chrome() -> None:
    genre = _genre("genre-single", "genre-single-en")
    _games(1, genre, prefix="gsingle")

    response = Client().get("/en/genres/genre-single-en/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "/en/games/gsingle-000/" in body
    assert 'data-testid="pagination"' not in body
    assert response.context["page_obj"].paginator.num_pages == 1


@pytest.mark.django_db
def test_genre_page_canonical_and_deep_page_noindex(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pagination_service, "CATALOG_PAGE_SIZE", 2)
    genre = _genre("genre-depth", "genre-depth-en")
    _games(11, genre, prefix="gdepth")
    origin = settings.PORTAL_ORIGIN.rstrip("/")
    client = Client()

    first = client.get("/en/genres/genre-depth-en/?sort=old")
    assert _canonical(first) == f"{origin}/en/genres/genre-depth-en/?sort=old"
    assert ROBOTS_RE.search(first.content.decode()) is None

    page_six = client.get("/en/genres/genre-depth-en/?sort=old&page=6")
    assert page_six.status_code == 200
    assert 'content="noindex,follow"' in page_six.content.decode()
    assert "sort=old" in _canonical(page_six)
    assert "page=6" in _canonical(page_six)
