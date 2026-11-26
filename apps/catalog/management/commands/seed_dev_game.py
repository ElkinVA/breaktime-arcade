"""Dev-only ZIP import + publish helper for browser E2E fixtures."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.catalog.models import Genre, GenreTranslation
from apps.i18n.models import Language
from apps.pipeline.services.importer import import_package
from apps.pipeline.services.publishing import publish_version


class Command(BaseCommand):
    help = "Import and publish a development game ZIP through the real pipeline."

    def add_arguments(self, parser) -> None:
        parser.add_argument("zip_path", help="Path to the cartridge ZIP")
        parser.add_argument("--genre", default="casual", help="Primary genre code")
        parser.add_argument("--genre-name-en", default="")
        parser.add_argument("--genre-name-ru", default="")

    def handle(self, *args, **options) -> None:
        if not settings.DEBUG:
            raise CommandError("seed_dev_game is a dev-only command")
        path = Path(str(options["zip_path"]))
        if not path.is_file():
            raise CommandError(f"ZIP not found: {path}")
        genre = self._ensure_genre(
            str(options["genre"]),
            str(options["genre_name_en"] or options["genre"]).title(),
            str(options["genre_name_ru"] or options["genre"]),
        )
        result = import_package(path.read_bytes(), original_filename=path.name)
        if result.status == "rejected" or result.game is None or result.version is None:
            messages = "; ".join(
                f"{item.code}: {item.message}" for item in result.report.diagnostics[:5]
            )
            raise CommandError(f"import rejected: {messages}")
        if result.game.primary_genre_id != genre.id:
            result.game.primary_genre = genre
            result.game.save(update_fields=["primary_genre", "updated_at"])
        published = publish_version(result.game, result.version)
        if not published.ok:
            raise CommandError(f"publish rejected: {published.reason}")
        self.stdout.write(
            f"seeded {result.game.technical_id} v{result.version.semver} "
            f"({result.status}) genre={genre.code}"
        )

    @staticmethod
    def _ensure_genre(code: str, name_en: str, name_ru: str) -> Genre:
        genre, _ = Genre.objects.get_or_create(code=code)
        for language_code, name in (("en", name_en), ("ru", name_ru)):
            language = Language.objects.filter(code=language_code).first()
            if language:
                GenreTranslation.objects.get_or_create(
                    genre=genre,
                    language=language,
                    defaults={"name": name, "slug": f"{code}-{language_code}"},
                )
        return genre
