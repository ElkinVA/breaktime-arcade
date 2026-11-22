"""EN strings for the rating vote widget and TOP-100 leaderboard (§2.9, §2.11)."""

from django.db import migrations

STRINGS = {
    "catalog": {
        "rating_vote_title": "Rate this game",
        "rating_vote_submit": "Submit rating",
        "rating_vote_saved": "Thanks! Your rating has been saved.",
        "rating_vote_error": "Could not save your rating. Please try again.",
        "rating_vote_playtime_error": "You need more verified playtime to rate this game.",
        "rating_vote_limit_error": "You have reached a rating limit. Please try again later.",
        "rating_playtime_required": (
            "Play at least {min} seconds to rate this game. "
            "Your verified playtime: {verified} s."
        ),
        "rating_guest_invitation": "Ratings are available to registered players.",
        "rating_guest_cta": "Create an account",
        "leaderboard_title": "Leaderboard",
        "leaderboard_player_label": "Player",
        "leaderboard_score_label": "Score",
        "leaderboard_empty": "No records yet.",
        "leaderboard_your_row": "Your row",
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
    dependencies = [("i18n", "0010_seed_catalog_empty_search_strings")]
    operations = [migrations.RunPython(seed_strings, unseed_strings)]
