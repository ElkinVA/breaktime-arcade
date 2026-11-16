#!/usr/bin/env bash
# fix_migration_graph.sh — исправление циклической/недостающей зависимости миграций
set -euo pipefail

echo "=== ИСПРАВЛЕНИЕ ГРАФА МИГРАЦИЙ ==="

# 1. Убираем run_before из core.0001_extensions
# Это ломает загрузку графа, если accounts ещё не имеет миграций
echo "1. Исправление apps/core/migrations/0001_extensions.py"
if grep -q 'run_before = \[("accounts", "0001_initial")\]' apps/core/migrations/0001_extensions.py; then
    sed -i '/run_before = \[("accounts", "0001_initial")\]/d' apps/core/migrations/0001_extensions.py
    echo "  ✓ run_before удалён"
else
    echo "  ! run_before уже удалён или отсутствует"
fi

# Исправляем type hint в dependencies, если он там есть, на обычный список
sed -i 's/dependencies: list\[tuple\[str, str\]\] = \[\]/dependencies = []/' apps/core/migrations/0001_extensions.py

# 2. Удаляем проблемные миграции i18n, которые ссылаются на несуществующие accounts и catalog
echo "2. Удаление ручных миграций i18n, блокирующих граф"
rm -f apps/i18n/migrations/0000_initial.py
rm -f apps/i18n/migrations/0001_initial.py
rm -f apps/i18n/migrations/0002_seed_languages.py
rm -f apps/i18n/migrations/0003_seed_ui_strings.py
echo "  ✓ Миграции i18n удалены"

# 3. Запускаем makemigrations для всех затронутых приложений
echo "3. Генерация миграций (makemigrations)"
docker compose -f compose.yml -f compose.dev-lite.yml run --rm --user "$(id -u):$(id -g)" \
    -e RUN_MIGRATIONS=0 -e RUN_COLLECTSTATIC=0 \
    web python manage.py makemigrations core accounts catalog i18n theme

# 4. Добавляем явную зависимость accounts от core, чтобы расширения БД (citext) создались до таблиц
echo "4. Добавление зависимости accounts от core"
if [[ -f apps/accounts/migrations/0001_initial.py ]]; then
    if grep -q 'dependencies = \[\]' apps/accounts/migrations/0001_initial.py; then
        sed -i 's/dependencies = \[\]/dependencies = [("core", "0001_extensions")]/' apps/accounts/migrations/0001_initial.py
        echo "  ✓ Зависимость добавлена в accounts.0001_initial.py"
    else
        echo "  ! Не удалось найти 'dependencies = []' в accounts.0001_initial.py. Проверьте вручную."
    fi
else
    echo "  ✗ Файл apps/accounts/migrations/0001_initial.py не создан!"
    exit 1
fi

# 5. Создаём сид-миграции для i18n
echo "5. Создание сид-миграций для i18n"
cat > apps/i18n/migrations/0002_seed_languages.py << 'BA_EOF'
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
BA_EOF

cat > apps/i18n/migrations/0003_seed_ui_strings.py << 'BA_EOF'
"""Строки интерфейса (EN) для ключей, используемых в шаблонах портала."""
from django.db import migrations

STRINGS = {
    "ui": {
        "skip_to_content": "Skip to content",
        "no_data": "No data",
        "no_cover": "No cover",
        "previous": "Previous",
        "next": "Next",
        "go_home": "Go to home page",
    },
    "nav": {"games": "Games", "genres": "Genres"},
    "auth": {"login": "Log in", "register": "Sign up"},
    "home": {
        "hero_title": "Short games for a quick break",
        "hero_subtitle": "Play instantly in your browser — no downloads, no registration required.",
        "block_popular": "Popular",
        "block_popular_hint": "What everyone is playing this week.",
        "block_rated": "Top rated",
        "block_rated_hint": "Games with the highest player ratings.",
        "block_new": "New",
        "block_new_hint": "Freshly published cartridges.",
        "browse_catalog": "Browse the catalog",
    },
    "catalog": {"title": "Game catalog", "empty": "The catalog is being filled — games will appear after publication."},
    "footer": {
        "tagline": "A portal of short browser mini-games for your break.",
        "legal": "Legal",
        "contact": "Contact",
        "email": "support@portal.test",
        "rights": "All rights reserved.",
    },
    "legal": {"terms": "Terms of Service", "privacy": "Privacy Policy", "cookies": "Cookie Policy"},
    "error": {
        "400.title": "Bad request", "400.message": "The server could not process your request.",
        "403.title": "Access denied", "403.message": "You do not have access to this page.",
        "404.title": "Page not found", "404.message": "The page you requested does not exist or was moved.",
        "410.title": "Content removed", "410.message": "This content is no longer available.",
        "500.title": "Server error", "500.message": "Something went wrong on our side. Please try again later.",
    },
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
                namespace=namespace,
                key=key,
                language=en,
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
        TranslationEntry.objects.filter(
            language=en, namespace=namespace, key__in=list(entries)
        ).delete()

class Migration(migrations.Migration):
    dependencies = [("i18n", "0002_seed_languages")]
    operations = [migrations.RunPython(seed_strings, unseed_strings)]
BA_EOF
echo "  ✓ Сид-миграции созданы"

# 6. Применяем миграции
echo "6. Применение миграций (migrate)"
docker compose -f compose.yml -f compose.dev-lite.yml run --rm -e RUN_MIGRATIONS=0 -e RUN_COLLECTSTATIC=0 \
    web python manage.py migrate --noinput

# 7. Перезапуск контейнеров
echo "7. Перезапуск контейнеров"
docker compose -f compose.yml -f compose.dev-lite.yml --profile beat up -d --force-recreate

echo "8. Ожидание запуска (15 секунд)..."
sleep 15

echo "9. Проверка статуса"
docker compose -f compose.yml -f compose.dev-lite.yml ps
echo "healthz: $(curl -sk https://portal.test:8443/healthz || echo 'нет ответа')"
echo "/en/: $(curl -sk -o /dev/null -w '%{http_code}' https://portal.test:8443/en/)"
