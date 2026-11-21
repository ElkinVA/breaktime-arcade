"""Dev-only search benchmark: seed, EXPLAIN/ANALYZE, candidate indexes.

Baseline and candidate runs seed rows inside a rolled-back transaction; no
catalog data is persisted. Candidate GIN indexes are created outside the
transaction (PostgreSQL forbids CREATE INDEX with pending trigger events),
measured, and always dropped in a finally block.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from typing import Any

from django.conf import settings
from django.contrib.postgres.search import SearchQuery
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connection, transaction

from apps.catalog.models import Game, GameTranslation, Genre
from apps.catalog.services.catalog import (
    CatalogFilters,
    filter_games,
    published_games,
)
from apps.catalog.services.search import Unaccent
from apps.core.ids import uuid7
from apps.i18n.models import Language

CANDIDATE_INDEXES = ("bench_trgm_name", "bench_trgm_unaccent_name")


class Command(BaseCommand):
    help = "Seed catalog rows in a rolled-back transaction and print EXPLAIN/ANALYZE plans."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--games", type=int, default=1000)
        parser.add_argument("--query", default="puzzle game")
        parser.add_argument(
            "--no-candidate-index",
            action="store_true",
            help="skip temporary trigram/unaccent GIN indexes",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG and not os.environ.get("PYTEST_CURRENT_TEST"):
            raise CommandError("catalog_benchmark is a dev-only diagnostic command")
        games_count = min(max(1, int(options["games"])), 100_000)
        query = str(options["query"])[:80]
        self._measure(games_count, query, "baseline")
        if options["no_candidate_index"]:
            return
        self._drop_indexes()
        try:
            self._create_indexes()
            self._measure(games_count, query, "candidate indexes")
        finally:
            self._drop_indexes()

    def _measure(self, games_count: int, query: str, phase: str) -> None:
        with transaction.atomic():
            try:
                self._seed(games_count)
                self.stdout.write(f"\n===== {phase}: games={games_count} query={query!r}")
                stored_query = SearchQuery(query, config="simple", search_type="websearch")
                fts = GameTranslation.objects.filter(search_vector=stored_query)
                trigram = GameTranslation.objects.filter(name__trigram_similar=query)
                unaccent = GameTranslation.objects.annotate(
                    unaccented_name=Unaccent("name")
                ).filter(unaccented_name__icontains=query)
                full = filter_games(CatalogFilters(q=query), "en")
                listing = published_games().order_by("-published_at", "-id")[:24]

                self._plan("listing 24", listing)
                self._plan("fts-only (persisted search_vector GIN)", fts)
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL enable_seqscan = off")
                try:
                    self._plan("fts-only forced GIN (enable_seqscan=off)", fts)
                finally:
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL enable_seqscan = on")
                self._plan("trigram-only (raw name)", trigram)
                self._plan("unaccent icontains", unaccent)
                self._plan("full filter_games(q)", full)
            finally:
                transaction.set_rollback(True)

    def _seed(self, games_count: int) -> None:
        language, _ = Language.objects.get_or_create(code="en", defaults={"name": "English"})
        genre, _ = Genre.objects.get_or_create(code="benchmark", defaults={"sort_order": 999})
        now = datetime.now(UTC)
        games: list[Game] = []
        translations: list[GameTranslation] = []
        for index in range(games_count):
            game_id = uuid7()
            suffix = f"{index:05d}"
            hit = index % 10 == 0
            games.append(
                Game(
                    id=game_id,
                    technical_id=f"bench{suffix}",
                    host_label=f"bench{suffix}",
                    slug=f"bench-{suffix}",
                    primary_genre=genre,
                    status=Game.STATUS_PUBLISHED,
                    published_at=now,
                    mobile_support=True,
                    estimated_play_minutes=5,
                )
            )
            translations.append(
                GameTranslation(
                    id=uuid7(),
                    game_id=game_id,
                    language=language,
                    name=(f"Puzzle game {suffix}" if hit else f"Benchmark game {suffix}"),
                    slug=f"bench-{suffix}",
                    short_description=(
                        f"Short {suffix} puzzle arcade" if hit else f"Short {suffix} arcade"
                    ),
                    description=(
                        f"Description {suffix} puzzle action arcade"
                        if hit
                        else f"Description {suffix} action arcade"
                    ),
                )
            )
        Game.objects.bulk_create(games, batch_size=500)
        GameTranslation.objects.bulk_create(translations, batch_size=500)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE catalog_game_translation
                SET search_vector = to_tsvector(
                    'simple',
                    unaccent(
                        coalesce(name, '') || ' ' ||
                        coalesce(short_description, '') || ' ' ||
                        coalesce(description, '')
                    )
                )
                """
            )
            cursor.execute("ANALYZE catalog_game")
            cursor.execute("ANALYZE catalog_game_translation")

    def _create_indexes(self) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "CREATE INDEX bench_trgm_name ON catalog_game_translation "
                "USING gin (name gin_trgm_ops)"
            )
            try:
                cursor.execute(
                    "CREATE INDEX bench_trgm_unaccent_name ON catalog_game_translation "
                    "USING gin (unaccent(name) gin_trgm_ops)"
                )
            except DatabaseError as exc:
                self.stdout.write(
                    f"unaccent(name) expression index is not IMMUTABLE; skipped: {exc}"
                )
            cursor.execute("ANALYZE catalog_game_translation")

    def _drop_indexes(self) -> None:
        with connection.cursor() as cursor:
            for name in CANDIDATE_INDEXES:
                cursor.execute(f"DROP INDEX IF EXISTS {name}")

    def _plan(self, label: str, queryset: Any) -> None:
        started = time.perf_counter()
        rows = list(queryset[:20])
        elapsed = (time.perf_counter() - started) * 1000
        self.stdout.write(f"\n### {label}: rows={len(rows)} fetch_ms={elapsed:.1f}")
        try:
            self.stdout.write(queryset.explain(analyze=True, buffers=True))
        except Exception as exc:  # pragma: no cover - diagnostic command
            self.stdout.write(f"EXPLAIN failed: {exc}")
