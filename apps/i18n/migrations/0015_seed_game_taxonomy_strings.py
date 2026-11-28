"""EN source and RU translation for the public game taxonomy block (§2.2/§2.8).

The game detail page lists the localized primary genre, additional genres and
tags. Locales without a published translation resolve through the existing
English fallback of ``{% ba_t %}``.
"""

from django.db import migrations

STRINGS = {
    "en": {
        "catalog": {
            "taxonomy_title": "Genres and tags",
            "taxonomy_primary_genre": "Main genre",
            "taxonomy_additional_genres": "Additional genres",
            "taxonomy_tags": "Tags",
        },
    },
    "ru": {
        "catalog": {
            "taxonomy_title": "Жанры и теги",
            "taxonomy_primary_genre": "Основной жанр",
            "taxonomy_additional_genres": "Дополнительные жанры",
            "taxonomy_tags": "Теги",
        },
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
    dependencies = [("i18n", "0014_seed_game_credits_strings")]
    operations = [migrations.RunPython(seed_strings, unseed_strings)]
