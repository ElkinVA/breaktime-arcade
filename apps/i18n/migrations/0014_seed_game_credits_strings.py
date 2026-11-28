"""EN source and RU translation for the public game credits block (§2.21, App J).

``Game.credits`` is imported from ``manifest.credits``; every entry carries an
author, a license and an AI-generated flag and is rendered on the game page.
Locales without a published translation resolve through the existing English
fallback of ``{% ba_t %}``.
"""

from django.db import migrations

STRINGS = {
    "en": {
        "catalog": {
            "credits_title": "Credits",
            "credits_author": "Author",
            "credits_license": "License",
            "credits_ai_generated": "AI-generated",
        },
    },
    "ru": {
        "catalog": {
            "credits_title": "Авторы и лицензии",
            "credits_author": "Автор",
            "credits_license": "Лицензия",
            "credits_ai_generated": "Сгенерировано ИИ",
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
    dependencies = [("i18n", "0013_seed_gameplay_player_strings")]
    operations = [migrations.RunPython(seed_strings, unseed_strings)]
