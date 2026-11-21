"""Публичный каталог: только published, фильтры и поиск (§2.8)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.contrib.postgres.search import (
    SearchQuery,
    SearchRank,
    SearchVector,
    TrigramSimilarity,
)
from django.db.models import (
    F,
    FloatField,
    IntegerField,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Value,
)
from django.db.models.functions import Coalesce

from apps.catalog.models import (
    Game,
    GameTranslation,
    GenreTranslation,
    TagTranslation,
)
from apps.catalog.services.localization import localization_coverage
from apps.catalog.services.popularity import popularity_counts, popularity_subquery
from apps.catalog.services.search import Unaccent
from apps.i18n.models import Language
from apps.ratings.models import GameRatingAggregate
from apps.ratings.services.aggregates import summaries as rating_summaries

DURATION_BUCKETS = {
    "short": (0, 5),
    "medium": (6, 15),
    "long": (16, 30),
    "epic": (31, 10_000),
}
SORT_NEW = "new"
SORT_OLD = "old"
SORT_POPULAR = "popular"
SORT_RATING = "rating"
SORT_VOTES = "votes"
SORT_CHOICES = {SORT_NEW, SORT_OLD, SORT_POPULAR, SORT_RATING, SORT_VOTES}

HOME_BLOCK_LIMIT = 6


@dataclass(frozen=True)
class CatalogFilters:
    q: str = ""
    genre: str = ""
    tags: tuple[str, ...] = ()
    mobile: bool = False
    duration: str = ""
    sort: str = SORT_NEW


def _tag_values(params: Any) -> tuple[str, ...]:
    if hasattr(params, "getlist"):
        values = params.getlist("tag")
    else:
        value = params.get("tag")
        values = [value] if value else []
    return tuple(str(value).strip()[:64] for value in values if str(value).strip())


def parse_filters(params: Any) -> CatalogFilters:
    duration = str(params.get("duration") or "")
    if duration not in DURATION_BUCKETS:
        duration = ""
    sort = str(params.get("sort") or SORT_NEW)
    if sort not in SORT_CHOICES:
        sort = SORT_NEW
    return CatalogFilters(
        q=str(params.get("q") or "").strip()[:80],
        genre=str(params.get("genre") or "").strip()[:32],
        tags=_tag_values(params),
        mobile=str(params.get("mobile") or "").lower() in {"1", "true", "on", "yes"},
        duration=duration,
        sort=sort,
    )


def _rating_sort_annotations() -> tuple[Coalesce, Coalesce]:
    aggregates = GameRatingAggregate.objects.filter(game=OuterRef("pk"))
    wr_score = Subquery(aggregates.values("wr_score")[:1], output_field=FloatField())
    vote_count = Subquery(aggregates.values("count")[:1], output_field=IntegerField())
    return (
        Coalesce(wr_score, Value(0.0), output_field=FloatField()),
        Coalesce(vote_count, Value(0), output_field=IntegerField()),
    )


def published_games() -> QuerySet[Game]:
    return (
        Game.objects.filter(status=Game.STATUS_PUBLISHED)
        .select_related("primary_genre", "current_version")
        .prefetch_related("translations__language")
    )


def _fts_config(language_code: str) -> str:
    configured = (
        Language.objects.filter(code=language_code).values_list("fts_config", flat=True).first()
    )
    return configured or "simple"


def filter_games(filters: CatalogFilters, language_code: str = "en") -> QuerySet[Game]:
    queryset = published_games()
    if filters.genre:
        queryset = queryset.filter(
            Q(primary_genre__code=filters.genre) | Q(additional_genres__code=filters.genre)
        ).distinct()
    if filters.tags:
        queryset = queryset.filter(tags__code__in=filters.tags).distinct()
    if filters.mobile:
        queryset = queryset.filter(mobile_support=True)
    if filters.duration:
        minimum, maximum = DURATION_BUCKETS[filters.duration]
        queryset = queryset.filter(
            estimated_play_minutes__gte=minimum,
            estimated_play_minutes__lte=maximum,
        )
    if filters.q:
        query = filters.q
        if len(query) >= 2:
            config = _fts_config(language_code)
            vector = (
                SearchVector(Unaccent("translations__name"), weight="A", config=config)
                + SearchVector(
                    Unaccent("translations__short_description"), weight="B", config=config
                )
                + SearchVector(Unaccent("translations__description"), weight="C", config=config)
            )
            search_query = SearchQuery(query, config=config, search_type="websearch")
            stored_query = SearchQuery(query, config="simple", search_type="websearch")
            queryset = (
                queryset.annotate(
                    search=vector,
                    similarity=TrigramSimilarity("translations__name", query),
                )
                .filter(
                    Q(translations__search_vector=stored_query)
                    | Q(search=search_query)
                    | Q(similarity__gt=0.2)
                    | Q(translations__name__icontains=query)
                    | Q(translations__short_description__icontains=query)
                    | Q(translations__description__icontains=query)
                )
                .distinct()
            )
        else:
            queryset = queryset.none()
    if filters.q and len(filters.q) >= 2:
        queryset = queryset.annotate(
            rank=SearchRank(F("translations__search_vector"), stored_query)
        )
        if filters.sort not in {SORT_OLD, SORT_POPULAR, SORT_RATING, SORT_VOTES}:
            return queryset.order_by("-rank", "-published_at", "-id")
    if filters.sort in {SORT_RATING, SORT_VOTES}:
        wr_score, vote_count = _rating_sort_annotations()
        queryset = queryset.annotate(
            rating_wr_score=wr_score,
            rating_vote_count=vote_count,
        )
        if filters.sort == SORT_RATING:
            return queryset.order_by("-rating_wr_score", "-rating_vote_count", "id")
        return queryset.order_by("-rating_vote_count", "-rating_wr_score", "id")
    if filters.sort == SORT_POPULAR:
        wr_score, _ = _rating_sort_annotations()
        return queryset.annotate(
            popularity_30d=popularity_subquery(),
            rating_wr_score=wr_score,
        ).order_by("-popularity_30d", "-rating_wr_score", "id")
    if filters.sort == SORT_OLD:
        return queryset.order_by("published_at", "id")
    return queryset.order_by("-published_at", "-id")


def popular_games(limit: int = HOME_BLOCK_LIMIT) -> QuerySet[Game]:
    """Top published games by 30-day popularity for the home block (§2.8).

    Reuses the ``popular`` catalog ordering (popularity ↓, WR ↓, id ↑) and
    keeps only games that actually earned credit in the window.
    """
    wr_score, _ = _rating_sort_annotations()
    return (
        published_games()
        .annotate(popularity_30d=popularity_subquery(), rating_wr_score=wr_score)
        .filter(popularity_30d__gt=0)
        .order_by("-popularity_30d", "-rating_wr_score", "id")[:limit]
    )


def top_rated_games(
    limit: int = HOME_BLOCK_LIMIT, *, min_votes: int | None = None
) -> QuerySet[Game]:
    """Top published games by WR that meet the minimum vote threshold (§2.8/§2.9).

    The threshold defaults to ``RATING_WR_M`` (``v >= m``), i.e. 20 votes with
    the shipped settings.
    """
    threshold = int(settings.RATING_WR_M) if min_votes is None else min_votes
    wr_score, vote_count = _rating_sort_annotations()
    return (
        published_games()
        .annotate(rating_wr_score=wr_score, rating_vote_count=vote_count)
        .filter(rating_vote_count__gte=threshold)
        .order_by("-rating_wr_score", "-rating_vote_count", "id")[:limit]
    )


def localized_translation(game: Game, language_code: str) -> GameTranslation | None:
    translations = list(game.translations.all())
    for translation in translations:
        if translation.language.code == language_code:
            return translation
    for translation in translations:
        if translation.language.code == "en":
            return translation
    return translations[0] if translations else None


def card_items(
    games: QuerySet[Game],
    language_code: str,
    active_language_codes: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Карточки каталога; покрытие считается, когда передан список языков."""
    game_list = list(games)
    ratings = rating_summaries(game.pk for game in game_list)
    popularity = popularity_counts(game.pk for game in game_list)
    localization_codes = tuple(active_language_codes) if active_language_codes is not None else None
    items: list[dict[str, Any]] = []
    for game in game_list:
        rating = ratings[game.pk]
        items.append(
            {
                "game": game,
                "translation": localized_translation(game, language_code),
                "rating_average": rating["average"],
                "rating_count": rating["count"],
                "popularity": popularity.get(game.pk, 0),
                "localization": (
                    localization_coverage(game, localization_codes)
                    if localization_codes is not None
                    else None
                ),
            }
        )
    return items


def tag_options(language_code: str) -> list[dict[str, str]]:
    rows = TagTranslation.objects.filter(language__code=language_code).select_related("tag")
    if not rows.exists():
        rows = TagTranslation.objects.filter(language__code="en").select_related("tag")
    return [{"code": row.tag.code, "name": row.name} for row in rows.order_by("tag__code")]


def genre_options(language_code: str) -> list[dict[str, str]]:
    rows = (
        GenreTranslation.objects.filter(language__code=language_code)
        .select_related("genre")
        .order_by("genre__sort_order", "genre__code")
    )
    if not rows.exists():
        rows = (
            GenreTranslation.objects.filter(language__code="en")
            .select_related("genre")
            .order_by("genre__sort_order", "genre__code")
        )
    return [{"code": row.genre.code, "name": row.name, "slug": row.slug} for row in rows]
