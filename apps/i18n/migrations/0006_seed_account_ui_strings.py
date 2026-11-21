"""EN strings for the account cabinet personal game records (§2.10.4)."""

from django.db import migrations

STRINGS = {
    "account": {
        "my_games_title": "My games",
        "my_games_empty": (
            "You have no game records yet. Play a game to see your best results here."
        ),
        "game_label": "Game",
        "best_result_label": "Best result",
        "rank_label": "Rank",
        "achieved_label": "Achieved",
        "playtime_label": "Verified playtime",
        "playtime_seconds": "{seconds} s",
    },
}


def seed_strings(apps, schema_editor):
    Language = apps.get_model("i18n", "Language")
    TranslationEntry = apps.get_model("i18n", "TranslationEntry")
    try:
        en = Language.objects.get(code="en")
    except Language.DoesNotExist:
        return
    for namespace, entries in STRINGS.items():
        for key, value in entries.items():
            TranslationEntry.objects.update_or_create(
                namespace=namespace,
                key=key,
                language=en,
                defaults={
                    "value": value,
                    "status": "published",
                    "is_machine_translated": False,
                },
            )


def unseed_strings(apps, schema_editor):
    TranslationEntry = apps.get_model("i18n", "TranslationEntry")
    Language = apps.get_model("i18n", "Language")
    try:
        en = Language.objects.get(code="en")
    except Language.DoesNotExist:
        return
    for namespace, entries in STRINGS.items():
        TranslationEntry.objects.filter(
            language=en, namespace=namespace, key__in=list(entries)
        ).delete()


class Migration(migrations.Migration):
    dependencies = [("i18n", "0005_seed_catalog_ui_strings")]
    operations = [migrations.RunPython(seed_strings, unseed_strings)]
