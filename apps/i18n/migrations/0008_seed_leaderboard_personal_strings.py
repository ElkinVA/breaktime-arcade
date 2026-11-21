"""EN strings for the leaderboard personal section (§2.11 item 6, §2.15)."""

from django.db import migrations

STRINGS = {
    "catalog": {
        "leaderboard_personal_title": "Your results",
        "leaderboard_best_label": "Best result",
        "leaderboard_rank_label": "Rank",
        "leaderboard_achieved_label": "Achieved",
        "leaderboard_personal_empty": "No personal results yet.",
        "leaderboard_attempts_title": "Last attempts",
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
    dependencies = [("i18n", "0007_seed_localization_badge_strings")]
    operations = [migrations.RunPython(seed_strings, unseed_strings)]
