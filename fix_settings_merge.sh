#!/usr/bin/env bash
# =============================================================================
#  fix_settings_merge.sh — применение пропущенных патчей блока 2 к settings и urls
#
#  Проблема: fill_02_i18n_crm.sh пропустил config/settings/base.py и config/urls.py,
#  потому что они уже существовали. Этот скрипт добавляет недостающие строки.
#
#  Запуск: bash fix_settings_merge.sh [КАТАЛОГ] [--dry-run] [--restart]
# =============================================================================
set -euo pipefail

TARGET="$PWD"; DRY=0; RESTART=0
for arg in "$@"; do
  case "$arg" in
    --dry-run)  DRY=1 ;;
    --restart)  RESTART=1 ;;
    -h|--help)  sed -n '2,8p' "$0"; exit 0 ;;
    *) TARGET="$arg" ;;
  esac
done
cd "$TARGET"

patched=0; skipped=0

# Добавить строку после якоря, если её ещё нет
add_after() {
  local file="$1" anchor="$2" line="$3"
  if [[ ! -f "$file" ]]; then
    printf '  MISS  %s\n' "$file"; return 1
  fi
  if grep -qF -- "$line" "$file"; then
    printf '  SKIP  %s (уже есть: %s)\n' "$file" "${line:0:60}..."
    skipped=$((skipped+1))
    return 0
  fi
  if (( DRY )); then
    printf '  ADD   %s → %s\n' "$file" "${line:0:60}..."
    patched=$((patched+1))
    return 0
  fi
  # Используем sed для вставки строки после якоря
  local tmp
  tmp="$(mktemp)"
  awk -v anchor="$anchor" -v line="$line" '
    { print }
    index($0, anchor) > 0 { print line }
  ' "$file" > "$tmp"
  mv -f "$tmp" "$file"
  printf '  ADD   %s → %s\n' "$file" "${line:0:60}..."
  patched=$((patched+1))
}

# Добавить строку перед якорем, если её ещё нет
add_before() {
  local file="$1" anchor="$2" line="$3"
  if [[ ! -f "$file" ]]; then
    printf '  MISS  %s\n' "$file"; return 1
  fi
  if grep -qF -- "$line" "$file"; then
    printf '  SKIP  %s (уже есть)\n' "$file"
    skipped=$((skipped+1))
    return 0
  fi
  if (( DRY )); then
    printf '  ADD   %s → %s\n' "$file" "${line:0:60}..."
    patched=$((patched+1))
    return 0
  fi
  local tmp
  tmp="$(mktemp)"
  awk -v anchor="$anchor" -v line="$line" '
    index($0, anchor) > 0 { print line }
    { print }
  ' "$file" > "$tmp"
  mv -f "$tmp" "$file"
  printf '  ADD   %s → %s\n' "$file" "${line:0:60}..."
  patched=$((patched+1))
}

# =============================================================================
#  1. config/settings/base.py
# =============================================================================
printf '\n=== config/settings/base.py ===\n'

# 1.1 django.contrib.postgres в INSTALLED_APPS
add_after \
  config/settings/base.py \
  '"django.contrib.humanize",' \
  '    "django.contrib.postgres",'

# 1.2 LanguagePrefixMiddleware в MIDDLEWARE (после LocaleMiddleware)
add_after \
  config/settings/base.py \
  '"django.middleware.locale.LocaleMiddleware",' \
  '    "apps.i18n.middleware.LanguagePrefixMiddleware",'

# 1.3 context_processors: i18n и theme
add_after \
  config/settings/base.py \
  '"apps.core.context_processors.platform",' \
  '                "apps.i18n.context_processors.i18n",'

add_after \
  config/settings/base.py \
  '"apps.i18n.context_processors.i18n",' \
  '                "apps.theme.context_processors.theme",'

# =============================================================================
#  2. config/urls.py — полная перезапись (файл слишком сложный для точечных патчей)
# =============================================================================
printf '\n=== config/urls.py ===\n'

if grep -qF 'i18n_patterns' config/urls.py; then
  printf '  SKIP  config/urls.py (уже содержит i18n_patterns)\n'
  skipped=$((skipped+1))
else
  if (( DRY )); then
    printf '  REWRITE config/urls.py\n'
    patched=$((patched+1))
  else
    cat > config/urls.py <<'BA_EOF'
"""Корневые маршруты с языковыми префиксами (§2.6)."""
from __future__ import annotations

from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.urls import include, path
from django.views.generic import RedirectView

from apps.core import health

urlpatterns = [
    # Пробы живучести без языкового префикса
    path("healthz", health.healthz, name="healthz"),
    path("readyz", health.readyz, name="readyz"),

    # Тема
    path("", include("apps.theme.urls")),

    # CRM (без языкового префикса, с защищённым префиксом)
    path("crm/", include("apps.crm.urls", namespace="crm")),
]

# Языковые префиксы для публичных страниц
urlpatterns += i18n_patterns(
    # Каталог
    path("", include("apps.catalog.urls", namespace="catalog")),
    prefix_default_language=True,
)

# Редирект корня / по Accept-Language
urlpatterns += [
    path("", RedirectView.as_view(url="/en/", permanent=False)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
BA_EOF
    printf '  REWRITE config/urls.py\n'
    patched=$((patched+1))
  fi
fi

# =============================================================================
printf '\nПатчей применено: %d\n' "$patched"
printf 'Пропущено (уже есть): %d\n' "$skipped"
if (( DRY )); then printf 'Режим dry-run\n'; exit 0; fi

if (( RESTART )); then
  cat <<'BA_EOF'

Перезапускаю контейнеры...
BA_EOF
  docker compose -f compose.yml -f compose.dev-lite.yml --profile beat up -d --force-recreate
  sleep 8
  docker compose -f compose.yml -f compose.dev-lite.yml exec -T web python manage.py check
  docker compose -f compose.yml -f compose.dev-lite.yml exec -T web python manage.py makemigrations catalog i18n theme
  docker compose -f compose.yml -f compose.dev-lite.yml exec -T web python manage.py migrate --noinput
  cat <<'BA_EOF'

Проверка:
  curl -k https://portal.test:8443/healthz
  curl -k https://portal.test:8443/en/
BA_EOF
else
  cat <<'BA_EOF'

Следующие шаги:
  docker compose -f compose.yml -f compose.dev-lite.yml --profile beat up -d --force-recreate
  docker compose -f compose.yml -f compose.dev-lite.yml exec -T web python manage.py check
  docker compose -f compose.yml -f compose.dev-lite.yml exec -T web python manage.py makemigrations
  docker compose -f compose.yml -f compose.dev-lite.yml exec -T web python manage.py migrate

Или одной командой:
  bash fix_settings_merge.sh --restart
BA_EOF
fi
