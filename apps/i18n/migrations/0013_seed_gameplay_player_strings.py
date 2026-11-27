"""EN source and RU translation for the player start-error message (§2.15).

The play page injects the localized value into ``data-start-error`` and
``player.js`` uses it as the fallback when a start error carries no message.
Every other active locale resolves through the existing English fallback of
``{% ba_t %}``; the coverage badge therefore keeps reflecting real published
translations instead of duplicated English rows.
"""

from django.db import migrations

STRINGS = {
    "en": {
        "gameplay": {
            "start_error": "Could not start the game",
        },
    },
    "ru": {
        "gameplay": {
            "start_error": "Не удалось начать игру",
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
    dependencies = [("i18n", "0012_seed_catalog_plural_strings")]
    operations = [migrations.RunPython(seed_strings, unseed_strings)]
