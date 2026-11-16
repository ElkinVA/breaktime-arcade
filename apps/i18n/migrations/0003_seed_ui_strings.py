"""Строки интерфейса (EN) для ключей, используемых в шаблонах портала."""
from django.db import migrations

STRINGS = {
    "ui": {"skip_to_content": "Skip to content", "no_data": "No data", "no_cover": "No cover", "previous": "Previous", "next": "Next", "go_home": "Go to home page"},
    "nav": {"games": "Games", "genres": "Genres"},
    "auth": {"login": "Log in", "register": "Sign up"},
    "home": {"hero_title": "Short games for a quick break", "hero_subtitle": "Play instantly in your browser — no downloads, no registration required.", "block_popular": "Popular", "block_popular_hint": "What everyone is playing this week.", "block_rated": "Top rated", "block_rated_hint": "Games with the highest player ratings.", "block_new": "New", "block_new_hint": "Freshly published cartridges.", "browse_catalog": "Browse the catalog"},
    "catalog": {"title": "Game catalog", "empty": "The catalog is being filled — games will appear after publication."},
    "footer": {"tagline": "A portal of short browser mini-games for your break.", "legal": "Legal", "contact": "Contact", "email": "support@portal.test", "rights": "All rights reserved."},
    "legal": {"terms": "Terms of Service", "privacy": "Privacy Policy", "cookies": "Cookie Policy"},
    "error": {"400.title": "Bad request", "400.message": "The server could not process your request.", "403.title": "Access denied", "403.message": "You do not have access to this page.", "404.title": "Page not found", "404.message": "The page you requested does not exist or was moved.", "410.title": "Content removed", "410.message": "This content is no longer available.", "500.title": "Server error", "500.message": "Something went wrong on our side. Please try again later."},
    "crm": {"accept": "Accept from package", "keep": "Keep current"},
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
                namespace=namespace, key=key, language=en,
                defaults={"value": value, "status": "published", "is_machine_translated": False},
            )

def unseed_strings(apps, schema_editor):
    TranslationEntry = apps.get_model("i18n", "TranslationEntry")
    Language = apps.get_model("i18n", "Language")
    try:
        en = Language.objects.get(code="en")
    except Language.DoesNotExist:
        return
    for namespace, entries in STRINGS.items():
        TranslationEntry.objects.filter(language=en, namespace=namespace, key__in=list(entries)).delete()

class Migration(migrations.Migration):
    dependencies = [("i18n", "0002_seed_languages")]
    operations = [migrations.RunPython(seed_strings, unseed_strings)]
