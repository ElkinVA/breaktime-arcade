"""EN strings for the new catalog rating, popularity and sort UI (§2.15)."""

from django.db import migrations

STRINGS = {
    "catalog": {
        "rating_title": "Ratings",
        "rating_out_of": "/ 5",
        "rating_votes_one": "{count} vote",
        "rating_votes_other": "{count} votes",
        "vote_one": "vote",
        "vote_other": "votes",
        "rating_empty": "No ratings yet.",
        "popularity_label": "Popularity (30 days)",
        "credit_one": "credit",
        "credit_other": "credits",
        "popularity_card_one": "credit in 30 days",
        "popularity_card_other": "credits in 30 days",
        "sort_label": "Sort",
        "sort_new": "Newest",
        "sort_rating": "Rating",
        "sort_votes": "Most voted",
        "sort_popular": "Popular",
        "sort_old": "Oldest",
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
    dependencies = [("i18n", "0004_seed_home_block_strings")]
    operations = [migrations.RunPython(seed_strings, unseed_strings)]
