#!/usr/bin/env bash
# =============================================================================
#  fix_views_force.sh — принудительная перезапись views для CRM и Catalog
#
#  Проблема: файлы views существуют, но пусты или неполны. URL-маршруты падают
#  при импорте. Скрипт перезаписывает оба файла с полным содержимым.
#
#  Запуск: bash fix_views_force.sh [КАТАЛОГ] [--dry-run]
# =============================================================================
set -euo pipefail

TARGET="$PWD"; DRY=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) TARGET="$arg" ;;
  esac
done
cd "$TARGET"

COMPOSE=(docker compose -f compose.yml -f compose.dev-lite.yml)

# =============================================================================
#  1. CRM views
# =============================================================================
printf '\n== 1. Перезапись apps/crm/views.py ==\n'
if (( DRY )); then
  printf '  DRY: перезапись apps/crm/views.py\n'
else
  cat > apps/crm/views.py <<'BA_EOF'
"""Заглушки представлений CRM. Шаг 2 (блок 2/3)."""
from __future__ import annotations

from django.http import HttpRequest, HttpResponseRedirect, JsonResponse
from django.template.response import TemplateResponse
from django.urls import reverse


def login_view(request: HttpRequest) -> TemplateResponse:
    return TemplateResponse(request, "crm/login.html")


def logout_view(request: HttpRequest) -> HttpResponseRedirect:
    return HttpResponseRedirect(reverse("crm:login"))


def dashboard(request: HttpRequest) -> TemplateResponse:
    if not request.user.is_authenticated or not request.user.is_staff:
        return HttpResponseRedirect(reverse("crm:login"))
    return TemplateResponse(request, "crm/dashboard.html", {
        "title": "CRM",
        "stage": "блок 2/3 — каркас",
    })
BA_EOF
  chmod 644 apps/crm/views.py
  printf '  OK   apps/crm/views.py\n'
fi

# =============================================================================
#  2. Catalog views
# =============================================================================
printf '\n== 2. Перезапись apps/catalog/views.py ==\n'
if (( DRY )); then
  printf '  DRY: перезапись apps/catalog/views.py\n'
else
  cat > apps/catalog/views.py <<'BA_EOF'
"""Заглушки представлений каталога. Наполняются блоком 5."""
from __future__ import annotations

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.template.response import TemplateResponse


def home(request: HttpRequest) -> TemplateResponse:
    return TemplateResponse(request, "catalog/home.html", {"title": "Breaktime Arcade"})


def game_list(request: HttpRequest) -> TemplateResponse:
    return TemplateResponse(request, "catalog/game_list.html", {"title": "Каталог"})


def game_detail(request: HttpRequest, slug: str) -> JsonResponse:
    return JsonResponse({"status": "stub", "slug": slug, "stage": "block-5"})


def game_play(request: HttpRequest, slug: str) -> JsonResponse:
    return JsonResponse({"status": "stub", "slug": slug, "stage": "block-3-player"})


def game_leaderboard(request: HttpRequest, slug: str) -> JsonResponse:
    return JsonResponse({"status": "stub", "slug": slug, "stage": "block-3-leaderboard"})


def genre_detail(request: HttpRequest, slug: str) -> JsonResponse:
    return JsonResponse({"status": "stub", "slug": slug, "stage": "block-5"})
BA_EOF
  chmod 644 apps/catalog/views.py
  printf '  OK   apps/catalog/views.py\n'
fi

# =============================================================================
#  3. Права доступа
# =============================================================================
printf '\n== 3. Права доступа ==\n'
if (( DRY == 0 )); then
  find apps config templates static/src infra scripts schemas sdk tests \
       -type f -exec chmod 644 {} + 2>/dev/null || true
  find apps config templates static/src infra scripts schemas sdk tests \
       -type d -exec chmod 755 {} + 2>/dev/null || true
  find . -maxdepth 3 -name '*.sh' -type f -exec chmod 755 {} + 2>/dev/null || true
  chmod 755 manage.py 2>/dev/null || true
  printf '  OK\n'
else
  printf '  DRY\n'
fi

# =============================================================================
#  4. makemigrations
# =============================================================================
printf '\n== 4. makemigrations ==\n'
if (( DRY )); then
  printf '  DRY: makemigrations\n'
else
  "${COMPOSE[@]}" run --rm --user "$(id -u):$(id -g)" \
      -e RUN_MIGRATIONS=0 -e RUN_COLLECTSTATIC=0 \
      web python manage.py makemigrations --noinput accounts catalog i18n theme
fi

# =============================================================================
#  5. Сид-миграции (если ещё не созданы)
# =============================================================================
printf '\n== 5. Проверка сид-миграций ==\n'
if [[ -f apps/i18n/migrations/0002_seed_languages.py ]]; then
  printf '  SKIP apps/i18n/migrations/0002_seed_languages.py (уже существует)\n'
else
  if (( DRY )); then
    printf '  FILL apps/i18n/migrations/0002_seed_languages.py\n'
  else
    cat > apps/i18n/migrations/0002_seed_languages.py <<'BA_EOF'
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
    chmod 644 apps/i18n/migrations/0002_seed_languages.py
    printf '  OK   apps/i18n/migrations/0002_seed_languages.py\n'
  fi
fi

if [[ -f apps/i18n/migrations/0003_seed_ui_strings.py ]]; then
  printf '  SKIP apps/i18n/migrations/0003_seed_ui_strings.py (уже существует)\n'
else
  if (( DRY )); then
    printf '  FILL apps/i18n/migrations/0003_seed_ui_strings.py\n'
  else
    cat > apps/i18n/migrations/0003_seed_ui_strings.py <<'BA_EOF'
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
    chmod 644 apps/i18n/migrations/0003_seed_ui_strings.py
    printf '  OK   apps/i18n/migrations/0003_seed_ui_strings.py\n'
  fi
fi

# =============================================================================
#  6. migrate
# =============================================================================
printf '\n== 6. migrate ==\n'
if (( DRY )); then
  printf '  DRY: migrate\n'
else
  "${COMPOSE[@]}" run --rm -e RUN_MIGRATIONS=0 -e RUN_COLLECTSTATIC=0 \
      web python manage.py migrate --noinput
fi

# =============================================================================
#  7. Подъём стека
# =============================================================================
printf '\n== 7. Подъём стека ==\n'
if (( DRY )); then
  printf '  DRY: up -d\n'
else
  "${COMPOSE[@]}" --profile beat up -d --force-recreate
  sleep 20

  printf '\n== 8. Проверка ==\n'
  "${COMPOSE[@]}" ps
  printf '\nhealthz: '
  curl -sk https://portal.test:8443/healthz || printf '(нет ответа)'
  printf '\n/ (root): %s\n' "$(curl -sk -o /dev/null -w '%{http_code}' https://portal.test:8443/)"
  printf '/en/:   %s\n' "$(curl -sk -o /dev/null -w '%{http_code}' https://portal.test:8443/en/)"
fi
