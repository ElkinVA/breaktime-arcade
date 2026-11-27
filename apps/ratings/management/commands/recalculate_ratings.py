"""Deploy/manual backfill for rating aggregates (§2.9)."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.ratings.services.aggregates import recalculate_all


class Command(BaseCommand):
    help = "Recalculate rating aggregates for every game with votes or an aggregate."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="report what would change without locks or writes",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="process at most N games in pk order (smoke/backfill batches)",
        )
        parser.add_argument(
            "--offset",
            type=int,
            default=None,
            help="skip the first N eligible games in pk order before applying --limit",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        limit = options["limit"]
        if limit is not None and limit < 1:
            raise CommandError("--limit must be a positive integer")
        offset = options["offset"]
        if offset is not None and offset < 1:
            raise CommandError("--offset must be a positive integer")
        dry_run = bool(options["dry_run"])
        result = recalculate_all(
            apply=not dry_run,
            limit=limit,
            offset=offset if offset is not None else 0,
        )
        verb = "would_update" if dry_run else "updated"
        message = (
            f"scanned={result['scanned']} {verb}={result['updated']} "
            f"unchanged={result['unchanged']} failed={result['failed']}"
        )
        if result["failed"]:
            self.stderr.write(self.style.ERROR(message))
            raise CommandError(f"rating recalculation failed for {result['failed']} games")
        self.stdout.write(self.style.SUCCESS(message))
