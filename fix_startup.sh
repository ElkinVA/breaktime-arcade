#!/usr/bin/env bash
# =============================================================================
#  fix_startup.sh — восстановление запуска web-контейнера
#
#  Создаёт недостающие URL-модули (catalog, crm) и view-заглушки,
#  исправляет миграцию i18n, перезапускает контейнеры.
#
#  Запуск: bash fix_startup.sh [КАТАЛОГ] [--force] [--dry-run] [--restart]
# =============================================================================
set -euo pipefail

TARGET="$PWD"; FORCE=0; DRY=0; RESTART=0
for arg in "$@"; do
  case "$arg" in
    --force)    FORCE=1 ;;
    --dry-run)  DRY=1 ;;
    --restart)  RESTART=1 ;;
    -h|--help)  sed -n '2,8p' "$0"; exit 0 ;;
    -*) printf 'Неизвестный ключ: %s\n' "$arg" >&2; exit 2 ;;
    *) TARGET="$arg" ;;
  esac
done
cd "$TARGET"
if [[ ! -d apps/core || ! -d config/settings ]]; then
  printf 'Каталог %s не содержит ядра. Сначала выполните bootstrap_structure.sh\n' "$TARGET" >&2
  exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR=".backups/$STAMP"
filled=0; skipped=0; backed=0; updated=0

write_file() {
  local rel="$1" tmp
  tmp="$(mktemp)"
  cat > "$tmp"
  if [[ -e "$rel" && -s "$rel" && $FORCE -eq 0 ]]; then
    printf '  SKIP  %s (не пустой)\n' "$rel"; skipped=$((skipped+1)); rm -f "$tmp"; return
  fi
  if (( DRY )); then
    printf '  FILL  %s\n' "$rel"; filled=$((filled+1)); rm -f "$tmp"; return
  fi
  mkdir -p -- "$(dirname -- "$rel")"
  if [[ -e "$rel" && -s "$rel" ]]; then
    mkdir -p -- "$BACKUP_DIR/$(dirname -- "$rel")"
    cp -p -- "$rel" "$BACKUP_DIR/$rel"; backed=$((backed+1))
  fi
  mv -f -- "$tmp" "$rel"
  chmod 644 "$rel"
  printf '  OK    %s\n' "$rel"; filled=$((filled+1))
}

# Патч: точная замена одной строки по подстроке
patch_line() {
  local rel="$1" from="$2" to="$3" tmp
  if [[ ! -f "$rel" ]]; then
    printf '  MISS  %s\n' "$rel"; return 1
  fi
  if ! grep -qF -- "$from" "$rel"; then
    if grep -qF -- "$to" "$rel"; then
      printf '  ALREADY %s\n' "$rel"; return 0
    fi
    printf '  NOTFOUND %s\n' "$rel"; return 1
  fi
  if (( DRY )); then
    printf '  PATCH %s\n' "$rel"; updated=$((updated+1)); return 0
  fi
  tmp="$(mktemp)"
  awk -v from="$from" -v to="$to" 'index($0, from) > 0 { sub(from, to) } { print }' "$rel" > "$tmp"
  mkdir -p -- "$BACKUP_DIR/$(dirname -- "$rel")"
  cp -p -- "$rel" "$BACKUP_DIR/$rel"; backed=$((backed+1))
  mv -f -- "$tmp" "$rel"
  chmod 644 "$rel"
  printf '  PATCH %s\n' "$rel"; updated=$((updated+1))
}

# =============================================================================
#  1. Catalog: URL и views (заглушки для стартового блока 2)
# =============================================================================
write_file apps/catalog/urls.py <<'BA_EOF'
"""Маршруты каталога. Заглушки; наполняются блоками 3 и 5."""
from __future__ import annotations

from django.urls import path

from apps.catalog import views

app_name = "catalog"

urlpatterns = [
    path("", views.home, name="home"),
    path("games/", views.game_list, name="game_list"),
    path("games/<str:slug>/", views.game_detail, name="game_detail"),
    path("games/<str:slug>/play/", views.game_play, name="game_play"),
    path("games/<str:slug>/leaderboard/", views.game_leaderboard, name="game_leaderboard"),
    path("genres/<str:slug>/", views.genre_detail, name="genre_detail"),
]
BA_EOF

write_file apps/catalog/views.py <<'BA_EOF'
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

write_file apps/catalog/templates/catalog/home.html <<'BA_EOF'
{% extends "base.html" %}
{% load ba_i18n %}

{% block title %}Breaktime Arcade{% endblock %}

{% block content %}
<section class="max-w-7xl mx-auto px-4 py-12">
    <div class="text-center mb-12">
        <h1 class="text-4xl md:text-5xl font-display font-bold mb-4">
            {% ba_t "home.hero_title" %}
        </h1>
        <p class="text-muted text-lg max-w-2xl mx-auto">
            {% ba_t "home.hero_subtitle" %}
        </p>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
        <div class="p-6 bg-surface rounded-card border border-text/10">
            <h3 class="font-semibold mb-2">{% ba_t "home.block_popular" %}</h3>
            <p class="text-muted text-sm">{% ba_t "home.block_popular_hint" %}</p>
        </div>
        <div class="p-6 bg-surface rounded-card border border-text/10">
            <h3 class="font-semibold mb-2">{% ba_t "home.block_rated" %}</h3>
            <p class="text-muted text-sm">{% ba_t "home.block_rated_hint" %}</p>
        </div>
        <div class="p-6 bg-surface rounded-card border border-text/10">
            <h3 class="font-semibold mb-2">{% ba_t "home.block_new" %}</h3>
            <p class="text-muted text-sm">{% ba_t "home.block_new_hint" %}</p>
        </div>
    </div>

    <div class="text-center">
        <a href="/{{ current_language_code }}/games/" class="btn btn-primary inline-block px-8 py-3">
            {% ba_t "home.browse_catalog" %}
        </a>
    </div>
</section>
{% endblock %}
BA_EOF

write_file apps/catalog/templates/catalog/game_list.html <<'BA_EOF'
{% extends "base.html" %}
{% load ba_i18n %}

{% block title %}{% ba_t "catalog.title" %} — Breaktime Arcade{% endblock %}

{% block content %}
<section class="max-w-7xl mx-auto px-4 py-8">
    <h1 class="text-3xl font-display font-bold mb-6">{% ba_t "catalog.title" %}</h1>
    <p class="text-muted mb-8">{% ba_t "catalog.empty" %}</p>
</section>
{% endblock %}
BA_EOF

# =============================================================================
#  2. CRM: URL и views (заглушка дашборда)
# =============================================================================
write_file apps/crm/urls.py <<'BA_EOF'
"""Маршруты CRM. Каркас; наполняется блоками 2 (продолжение) и 3."""
from __future__ import annotations

from django.urls import path

from apps.crm import views

app_name = "crm"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
]
BA_EOF

write_file apps/crm/views.py <<'BA_EOF'
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

write_file apps/crm/templates/crm/login.html <<'BA_EOF'
{% extends "base.html" %}
{% load ba_i18n %}

{% block title %}Вход в CRM{% endblock %}

{% block content %}
<section class="max-w-md mx-auto px-4 py-16">
    <h1 class="text-2xl font-display font-bold mb-6 text-center">CRM · Вход</h1>
    <p class="text-muted text-center">
        Каркас CRM готов. Аутентификация, роли, 2FA и экраны добавятся в следующих блоках.
    </p>
</section>
{% endblock %}
BA_EOF

write_file apps/crm/templates/crm/dashboard.html <<'BA_EOF'
{% extends "base.html" %}

{% block title %}CRM · Дашборд{% endblock %}

{% block content %}
<section class="max-w-7xl mx-auto px-4 py-8">
    <h1 class="text-3xl font-display font-bold mb-6">CRM</h1>
    <div class="p-6 bg-surface rounded-card border border-text/10">
        <p class="text-muted">Этап: {{ stage }}. Пользователь: {{ user.login }}.</p>
    </div>
</section>
{% endblock %}
BA_EOF

# =============================================================================
#  3. Патч миграции i18n: убрать зависимость от catalog.0000_initial
#     Django сам создаст 0001_initial для catalog через makemigrations;
#     FK разрешится при применении, предварительная зависимость не нужна.
# =============================================================================
patch_line \
  apps/i18n/migrations/0000_initial.py \
  'dependencies = [("accounts", "0001_initial"), ("catalog", "0000_initial")]' \
  'dependencies = [("accounts", "0001_initial")]' \
  || printf '  ! i18n.0000_initial: зависимости не найдены или уже исправлены\n'

# =============================================================================
#  4. Обновить settings/base.py: добавить context_processor каталога/CRM нет,
#     но нужно убедиться, что i18n middleware стоит ДО LocaleMiddleware
#     (это уже так в fill_01_core + fill_02_i18n_crm, повторять не будем).
# =============================================================================

# =============================================================================
printf '\nИсправление запуска web-контейнера\n'
printf '  Каталог:          %s\n' "$PWD"
printf '  Создано файлов:   %d\n' "$filled"
printf '  Патчей применено: %d\n' "$updated"
printf '  Пропущено:        %d\n' "$skipped"
if (( backed > 0 )); then printf '  Резервные копии:  %s (%d)\n' "$BACKUP_DIR" "$backed"; fi
if (( DRY )); then printf '  Режим dry-run: изменения не внесены\n'; exit 0; fi

if (( RESTART )); then
  cat <<'BA_EOF'

Перезапускаю контейнеры и применяю миграции...
BA_EOF
  docker compose -f compose.yml -f compose.dev-lite.yml --profile beat up -d --force-recreate
  sleep 5
  docker compose -f compose.yml -f compose.dev-lite.yml exec -T web python manage.py makemigrations catalog i18n theme || true
  docker compose -f compose.yml -f compose.dev-lite.yml exec -T web python manage.py migrate --noinput
  cat <<'BA_EOF'

Проверка:
  docker compose ps
  curl -k https://portal.test:8443/healthz
  curl -k https://portal.test:8443/en/
BA_EOF
else
  cat <<'BA_EOF'

Следующие шаги (выполните вручную):
  docker compose -f compose.yml -f compose.dev-lite.yml --profile beat up -d --force-recreate
  docker compose -f compose.yml -f compose.dev-lite.yml exec -T web python manage.py makemigrations catalog i18n theme
  docker compose -f compose.yml -f compose.dev-lite.yml exec -T web python manage.py migrate --noinput
  curl -k https://portal.test:8443/healthz
  curl -k https://portal.test:8443/en/

Или одной командой с автоперезапуском:
  bash fix_startup.sh --restart
BA_EOF
fi
