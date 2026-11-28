"""EN/RU strings for the home genre discovery block and genre landing pages."""

from django.db import migrations

STRINGS = {
    "en": {
        "home": {
            "block_genres": "Genres",
            "meta_title": "Breaktime Arcade — short browser games",
            "meta_description": (
                "Play short browser games instantly — no downloads, no registration required."
            ),
        },
        "catalog": {
            "genre_games_one": "{count} game",
            "genre_games_other": "{count} games",
            "apply": "Apply",
            "all_games": "All games",
        },
        "nav": {"games": "Games"},
    },
    "ru": {
        "home": {
            "block_genres": "Жанры",
            "meta_title": "Breaktime Arcade — короткие игры в браузере",
            "meta_description": "Играйте в короткие браузерные игры без загрузки и регистрации.",
        },
        "catalog": {
            "genre_games_one": "{count} игра",
            "genre_games_few": "{count} игры",
            "genre_games_many": "{count} игр",
            "genre_games_other": "{count} игры",
            "apply": "Применить",
            "all_games": "Все игры",
        },
        "nav": {"games": "Игры"},
    },
}


def seed_strings(apps, schema_editor):
    Language = apps.get_model("i18n", "Language")
    TranslationEntry = apps.get_model("i18n", "TranslationEntry")
    for code, namespaces in STRINGS.items():
        try:
            language = Language.objects.get(code=code)
        except Language.DoesNotExist:
            continue
        for namespace, entries in namespaces.items():
            for key, value in entries.items():
                TranslationEntry.objects.update_or_create(
                    namespace=namespace,
                    key=key,
                    language=language,
                    defaults={
                        "value": value,
                        "status": "published",
                        "is_machine_translated": False,
                    },
                )


def unseed_strings(apps, schema_editor):
    TranslationEntry = apps.get_model("i18n", "TranslationEntry")
    Language = apps.get_model("i18n", "Language")
    for code, namespaces in STRINGS.items():
        try:
            language = Language.objects.get(code=code)
        except Language.DoesNotExist:
            continue
        for namespace, entries in namespaces.items():
            TranslationEntry.objects.filter(
                language=language, namespace=namespace, key__in=list(entries)
            ).delete()


class Migration(migrations.Migration):
    dependencies = [("i18n", "0015_seed_game_taxonomy_strings")]
    operations = [migrations.RunPython(seed_strings, unseed_strings)]
