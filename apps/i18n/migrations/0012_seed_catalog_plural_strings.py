"""RU CLDR plural forms for the legacy catalog rating/popularity keys (§2.15).

The original catalog seeds only contained English ``_one``/``_other``.  Russian
needs ``one``/``few``/``many``/``other``; the legacy key names are preserved and
only the missing suffix variants are added here.  Any language without a form
still falls back first to its own ``_other`` and then to English, so rendering
never produces an empty string.
"""

from django.db import migrations

STRINGS = {
    "catalog": {
        "rating_votes_one": "{count} голос",
        "rating_votes_few": "{count} голоса",
        "rating_votes_many": "{count} голосов",
        "rating_votes_other": "{count} голоса",
        "vote_one": "голос",
        "vote_few": "голоса",
        "vote_many": "голосов",
        "vote_other": "голоса",
        "credit_one": "кредит",
        "credit_few": "кредита",
        "credit_many": "кредитов",
        "credit_other": "кредита",
        "popularity_card_one": "кредит за 30 дней",
        "popularity_card_few": "кредита за 30 дней",
        "popularity_card_many": "кредитов за 30 дней",
        "popularity_card_other": "кредита за 30 дней",
    },
}


def seed_strings(apps, schema_editor):
    Language = apps.get_model("i18n", "Language")
    TranslationEntry = apps.get_model("i18n", "TranslationEntry")
    try:
        ru = Language.objects.get(code="ru")
    except Language.DoesNotExist:
        return
    for namespace, entries in STRINGS.items():
        for key, value in entries.items():
            TranslationEntry.objects.update_or_create(
                namespace=namespace,
                key=key,
                language=ru,
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
        ru = Language.objects.get(code="ru")
    except Language.DoesNotExist:
        return
    for namespace, entries in STRINGS.items():
        TranslationEntry.objects.filter(
            language=ru, namespace=namespace, key__in=list(entries)
        ).delete()


class Migration(migrations.Migration):
    dependencies = [("i18n", "0011_seed_rating_vote_leaderboard_strings")]
    operations = [migrations.RunPython(seed_strings, unseed_strings)]
