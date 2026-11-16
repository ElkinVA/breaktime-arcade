"""Стартовый набор языков портала (§2.15): en, de, nl, ru, fr, es."""
from django.db import migrations

LANGUAGES = [
    ("en", "English", "English", False, 1, "one", "english"),
    ("de", "Deutsch", "Deutsch", False, 2, "one", "german"),
    ("nl", "Nederlands", "Nederlands", False, 3, "one", "dutch"),
    ("ru", "Русский", "Русский", False, 4, "many", "russian"),
    ("fr", "Français", "Français", False, 5, "one", "french"),
    ("es", "Español", "Español", False, 6, "one", "spanish"),
]
CODES = [row[0] for row in LANGUAGES]

def seed_languages(apps, schema_editor):
    Language = apps.get_model("i18n", "Language")
    for code, name, native_name, is_rtl, sort_order, plural_rule, fts_config in LANGUAGES:
        Language.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "native_name": native_name,
                "is_active": True,
                "is_rtl": is_rtl,
                "sort_order": sort_order,
                "plural_rule": plural_rule,
                "fts_config": fts_config,
            },
        )

def unseed_languages(apps, schema_editor):
    apps.get_model("i18n", "Language").objects.filter(code__in=CODES).delete()

class Migration(migrations.Migration):
    dependencies = [("i18n", "0001_initial")]
    operations = [migrations.RunPython(seed_languages, unseed_languages)]
