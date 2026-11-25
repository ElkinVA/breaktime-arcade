from __future__ import annotations

import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.catalog.models import Game, GameVersion, Genre

PROBE_RUNTIME_HASH = "a" * 64


class Command(BaseCommand):
    help = "Create/refresh the test-only runtime probe game (not a product game)."

    def handle(self, *args, **options) -> None:
        if not settings.DEBUG and not os.environ.get("PYTEST_CURRENT_TEST"):
            raise CommandError("probe_seed is a dev-only diagnostic command")
        genre, _ = Genre.objects.get_or_create(code="probe")
        game, _ = Game.objects.get_or_create(
            technical_id="probe",
            defaults={
                "host_label": "probe.games.test",
                "slug": "probe",
                "primary_genre": genre,
                "status": Game.STATUS_PUBLISHED,
                "published_at": timezone.now(),
            },
        )
        version, _ = GameVersion.objects.get_or_create(
            game=game,
            semver="1.0.0",
            defaults={
                "package_hash": "b" * 64,
                "runtime_hash": PROBE_RUNTIME_HASH,
                "sdk_version": "1.1.0",
                "size_bytes": 1,
                "manifest": {"id": "probe", "version": "1.0.0"},
                "supported_languages": ["en"],
            },
        )
        game.status = Game.STATUS_PUBLISHED
        game.published_at = game.published_at or timezone.now()
        game.current_version = version
        game.save(update_fields=["status", "published_at", "current_version"])
        self.stdout.write(f"probe seeded: {game.technical_id} v{version.semver}")
