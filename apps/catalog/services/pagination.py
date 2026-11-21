"""Deterministic pagination for the public catalog (§2.19).

The page size is fixed server-side. Page links and the canonical URL reuse
the incoming query string so active filters and sort survive navigation.
Pages deeper than ``NOINDEX_AFTER_PAGE`` are excluded from search indexing
while their links stay crawlable (``noindex,follow``).
"""

from __future__ import annotations

from django.conf import settings
from django.core.paginator import Page, Paginator
from django.db.models import QuerySet
from django.http import HttpRequest, QueryDict

from apps.catalog.models import Game

CATALOG_PAGE_SIZE = 24
NOINDEX_AFTER_PAGE = 5


def _page_number(params: QueryDict) -> int:
    """Blank, non-integer and non-positive input maps to the first page."""
    raw = params.get("page")
    if raw is None:
        return 1
    value = raw.strip()
    if not value:
        return 1
    try:
        number = int(value)
    except ValueError:
        return 1
    return number if number >= 1 else 1


def paginate_games(
    games: QuerySet[Game],
    params: QueryDict,
    *,
    page_size: int | None = None,
) -> Page[Game]:
    """Return the requested page, clamping invalid and out-of-range values.

    Blank/non-integer/non-positive input maps to page 1; values beyond the
    last page map to the last page, so public URLs never 500.
    """
    return Paginator(games, page_size or CATALOG_PAGE_SIZE).get_page(_page_number(params))


def _query_without_page(params: QueryDict) -> QueryDict:
    query = params.copy()
    query.pop("page", None)
    return query


def pagination_query(params: QueryDict) -> str:
    """Active filters/sort as a query string with ``page`` removed."""
    return _query_without_page(params).urlencode()


def page_query(params: QueryDict, page_number: int) -> str:
    """Query string for ``page_number`` preserving filters; page 1 is bare."""
    query = _query_without_page(params)
    if page_number > 1:
        query["page"] = str(page_number)
    return query.urlencode()


def canonical_url(request: HttpRequest, params: QueryDict, page_number: int) -> str:
    """Absolute canonical URL for the rendered page (page 1 omits ``page``)."""
    base = f"{settings.PORTAL_ORIGIN.rstrip('/')}{request.path}"
    query = page_query(params, page_number)
    return f"{base}?{query}" if query else base


def should_noindex(page_number: int) -> bool:
    """Pages deeper than the indexed window are ``noindex,follow``."""
    return page_number > NOINDEX_AFTER_PAGE
