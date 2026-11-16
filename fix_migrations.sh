#!/usr/bin/env bash
# =============================================================================
#  fix_migrations.sh — устранение блокировки web: генерация миграций и сид-данные
#
#  1) диагностика (логи web)
#  2) удаление дефектных рукописных миграций i18n (с резервной копией)
#  3) права доступа на исходники
#  4) makemigrations через одноразовый контейнер (docker compose run)
#  5) сид-миграции: 6 языков + строки интерфейса (EN)
#  6) migrate, подъём стека, проверка healthz
#
#  Запуск: bash fix_migrations.sh [КАТАЛОГ] [--dry-run]
# =============================================================================
set -euo pipefail

TARGET="$PWD"; DRY=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) TARGET="$arg" ;;
  esac
done
cd "$TARGET"

COMPOSE=(docker compose -f compose.yml -f compose.dev-lite.yml)
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR=".backups/$STAMP"
run() { if (( DRY )); then printf '  DRY: %s\n' "$*"; else "$@"; fi; }

# --- 1. Диагностика ----------------------------------------------------------
printf '\n== 1. Последние логи web ==\n'
if (( DRY == 0 )); then "${COMPOSE[@]}" logs --tail=40 web || true; fi

# --- 2. Удаление дефектных рукописных миграций i18n --------------------------
printf '\n== 2. Удаление рукописных миграций i18n ==\n'
for f in apps/i18n/migrations/0000_initial.py apps/i18n/migrations/0001_initial.py; do
  if [[ -f "$f" ]]; then
    if (( DRY == 0 )); then
      mkdir -p "$BACKUP_DIR/apps/i18n/migrations"
      mv -f "$f" "$BACKUP_DIR/$f"
    fi
    printf '  REMOVED %s (копия в %s)\n' "$f" "$BACKUP_DIR"
  fi
done

# --- 3. Права доступа --------------------------------------------------------
printf '\n== 3. Права на исходники (644/755) ==\n'
if (( DRY == 0 )); then
  find apps config templates static/src infra scripts schemas sdk tests \
       -type f -exec chmod 644 {} + 2>/dev/null || true
  find apps config templates static/src infra scripts schemas sdk tests \
       -type d -exec chmod 755 {} + 2>/dev/null || true
  find . -maxdepth 3 -name '*.sh' -type f -exec chmod 755 {} + 2>/dev/null || true
  chmod 755 manage.py 2>/dev/null || true
fi
printf '  OK\n'

# --- 4. Автогенерация миграций -----------------------------------------------
printf '\n== 4. makemigrations (одноразовый контейнер) ==\n'
run "${COMPOSE[@]}" run --rm --user "$(id -u):$(id -g)" \
    -e RUN_MIGRATIONS=0 -e RUN_COLLECTSTATIC=0 \
    web python manage.py makemigrations --noinput accounts catalog i18n theme

if (( DRY == 0 )) && [[ ! -f apps/i18n/migrations/0001_initial.py ]]; then
  printf 'ОШИБКА: makemigrations не создал i18n/0001_initial.py — смотрите вывод выше\n' >&2
  exit 1
fi

# --- 5. Сид-миграции ---------------------------------------------------------
printf '\n== 5. Сид-миграции: языки + строки интерфейса ==\n'

write_seed() {
  local rel="$1"
  if [[ -e "$rel" && -s "$rel" ]]; then printf '  SKIP %s\n' "$rel"; return; fi
  if (( DRY )); then printf '  FILL %s\n' "$rel"; cat > /dev/null; return; fi
  cat > "$rel"
  chmod 644 "$rel"
  printf '  OK   %s\n' "$rel"
}

write_seed apps/i18n/migrations/0002_seed_languages.py <<'BA_EOF'
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

write_seed apps/i18n/migrations/0003_seed_ui_strings.py <<'BA_EOF'
"""Строки интерфейса (EN) для ключей, используемых в шаблонах портала.

Остальные языки заполняются через CRM (этап 6); до этого работает fallback en.
"""
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
    en = Language.objects.get(code="en")
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

# --- 6. Применение миграций и подъём стека ------------------------------------
printf '\n== 6. migrate ==\n'
run "${COMPOSE[@]}" run --rm -e RUN_MIGRATIONS=0 -e RUN_COLLECTSTATIC=0 \
    web python manage.py migrate --noinput

printf '\n== 7. Подъём стека ==\n'
run "${COMPOSE[@]}" --profile beat up -d --force-recreate

if (( DRY == 0 )); then
  sleep 20
  printf '\n== 8. Проверка ==\n'
  "${COMPOSE[@]}" ps
  printf '\nhealthz: '
  curl -sk https://portal.test:8443/healthz || printf '(нет ответа)'
  printf '\n/ (root): %s\n' "$(curl -sk -o /dev/null -w '%{http_code}' https://portal.test:8443/)"
  printf '/en/:   %s\n' "$(curl -sk -o /dev/null -w '%{http_code}' https://portal.test:8443/en/)"
  cat <<'BA_EOF'

Если web снова unhealthy — пришлите вывод:
  docker compose -f compose.yml -f compose.dev-lite.yml logs --tail=60 web
BA_EOF
fi
