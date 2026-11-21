"""Пагинация публичного каталога: страницы, фильтры, canonical, noindex (§2.19)."""

from __future__ import annotations

import html
import re
from datetime import timedelta

import pytest
from django.conf import settings
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.catalog.models import Game, Genre
from apps.catalog.services import pagination as pagination_service
from apps.catalog.services.pagination import CATALOG_PAGE_SIZE

CANONICAL_RE = re.compile(r'<link rel="canonical" href="([^"]+)"')
ROBOTS_RE = re.compile(r'<meta name="robots" content="([^"]+)"')


def _genre(code: str) -> Genre:
    return Genre.objects.create(code=code)


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
def test_page_two_returns_the_second_page() -> None:
    genre = _genre("puzzle")
    _games(30, genre, prefix="page")

    first = Client().get("/en/games/")
    second = Client().get("/en/games/?page=2")

    assert first.status_code == 200
    assert second.status_code == 200
    assert CATALOG_PAGE_SIZE == 24
    assert len(list(first.context["page_obj"].object_list)) == 24
    assert len(list(second.context["page_obj"].object_list)) == 6

    first_body = first.content.decode()
    second_body = second.content.decode()
    # Newest-first: page 1 holds page_029..page_006, page 2 holds page_005..page_000.
    assert "/en/games/page-029/" in first_body
    assert "/en/games/page-029/" not in second_body
    assert "/en/games/page-005/" in second_body
    assert "/en/games/page-005/" not in first_body
    assert "/en/games/page-000/" in second_body


@pytest.mark.django_db
def test_page_bounds_clamp_instead_of_erroring() -> None:
    genre = _genre("bounds")
    _games(30, genre, prefix="bound")

    client = Client()
    for value in ["0", "-3", "abc", "1.5", "", " "]:
        response = client.get("/en/games/", {"page": value})
        assert response.status_code == 200, value
        assert response.context["page_obj"].number == 1, value
        assert "/en/games/bound-029/" in response.content.decode(), value

    beyond = client.get("/en/games/?page=999")
    assert beyond.status_code == 200
    assert beyond.context["page_obj"].number == 2
    body = beyond.content.decode()
    assert "/en/games/bound-000/" in body
    assert "/en/games/bound-029/" not in body


@pytest.mark.django_db
def test_pagination_preserves_filters_and_sort() -> None:
    puzzle = _genre("puzzle")
    arcade = _genre("arcade")
    _games(60, puzzle, prefix="puzzle")
    _games(5, arcade, prefix="arcade")

    response = Client().get("/en/games/?genre=puzzle&sort=old&page=2")

    assert response.status_code == 200
    body = response.content.decode()
    assert 'data-testid="pagination"' in body
    # Oldest-first page 2: puzzle_024..puzzle_047, arcade games filtered out.
    assert "/en/games/puzzle-024/" in body
    assert "/en/games/puzzle-023/" not in body
    assert "/en/games/puzzle-047/" in body
    assert "/en/games/arcade-" not in body
    # Controls keep the active filter and sort next to the page number.
    assert 'href="?genre=puzzle&amp;sort=old&amp;page=3"' in body
    assert 'href="?genre=puzzle&amp;sort=old&amp;page=1"' in body


@pytest.mark.django_db
def test_htmx_partial_supports_page_and_filters() -> None:
    puzzle = _genre("puzzle")
    _games(60, puzzle, prefix="partial")

    response = Client().get(
        "/en/games/?genre=puzzle&sort=old&page=2",
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    body = response.content.decode()
    assert "<html" not in body
    assert "<!DOCTYPE" not in body
    assert "/en/games/partial-024/" in body
    assert "/en/games/partial-023/" not in body
    assert 'data-testid="pagination"' in body
    assert 'href="?genre=puzzle&amp;sort=old&amp;page=3"' in body
    assert 'hx-get="?genre=puzzle&amp;sort=old&amp;page=3"' in body
    assert 'hx-target="#game-results"' in body


@pytest.mark.django_db
def test_canonical_link_is_absolute_and_page_specific() -> None:
    genre = _genre("canonical")
    _games(30, genre, prefix="canon")
    origin = settings.PORTAL_ORIGIN.rstrip("/")
    client = Client()

    plain = _canonical(client.get("/en/games/"))
    assert plain == f"{origin}/en/games/"

    explicit_first = _canonical(client.get("/en/games/?page=1"))
    assert explicit_first == f"{origin}/en/games/"

    filtered = _canonical(client.get("/en/games/?genre=canonical&sort=old"))
    assert filtered.startswith(f"{origin}/en/games/?")
    assert "genre=canonical" in filtered
    assert "sort=old" in filtered
    assert "page=" not in filtered

    second = _canonical(client.get("/en/games/?genre=canonical&sort=old&page=2"))
    assert second.startswith(f"{origin}/en/games/?")
    assert "genre=canonical" in second
    assert "sort=old" in second
    assert "page=2" in second


@pytest.mark.django_db
def test_noindex_only_beyond_page_five(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pagination_service, "CATALOG_PAGE_SIZE", 2)
    genre = _genre("depth")
    _games(11, genre, prefix="depth")
    client = Client()

    page_five = client.get("/en/games/?page=5")
    page_six = client.get("/en/games/?page=6")

    assert page_five.status_code == 200
    assert page_six.status_code == 200
    assert ROBOTS_RE.search(page_five.content.decode()) is None
    assert 'content="noindex,follow"' in page_six.content.decode()
    assert "page=6" in _canonical(page_six)


@pytest.mark.django_db
def test_pagination_has_no_per_card_queries() -> None:
    puzzle = _genre("puzzle")
    arcade = _genre("arcade")
    _games(24, puzzle, prefix="many")
    _games(1, arcade, prefix="single")
    client = Client()

    # Warm language/popularity caches so only per-request work is measured.
    client.get("/en/games/?genre=puzzle")
    client.get("/en/games/?genre=arcade")

    with CaptureQueriesContext(connection) as many_queries:
        many = client.get("/en/games/?genre=puzzle")
    with CaptureQueriesContext(connection) as single_queries:
        single = client.get("/en/games/?genre=arcade")

    assert len(many.context["page_obj"].object_list) == 24
    assert len(single.context["page_obj"].object_list) == 1
    assert len(many_queries) == len(single_queries)
