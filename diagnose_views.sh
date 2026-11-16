#!/usr/bin/env bash
# =============================================================================
#  diagnose_views.sh — полная диагностика проблемы views
#
#  Запуск: bash diagnose_views.sh [КАТАЛОГ]
# =============================================================================
set -euo pipefail

TARGET="${1:-.}"
cd "$TARGET"

printf '\n=== ДИАГНОСТИКА ПРОБЛЕМЫ VIEWS ===\n\n'

# =============================================================================
#  1. Проверка файлов на хосте
# =============================================================================
printf '== 1. Файлы apps/crm/views.py и apps/catalog/views.py на хосте ==\n\n'

for f in apps/crm/views.py apps/catalog/views.py; do
  printf '--- %s ---\n' "$f"
  if [[ ! -f "$f" ]]; then
    printf '  ОШИБКА: файл не существует\n\n'
  elif [[ ! -s "$f" ]]; then
    printf '  ОШИБКА: файл пустой\n\n'
  else
    printf '  Размер: %s байт\n' "$(wc -c < "$f")"
    printf '  Строк: %s\n' "$(wc -l < "$f")"
    printf '  Права: %s\n' "$(stat -c '%a' "$f")"
    printf '  Владелец: %s\n' "$(stat -c '%U:%G' "$f")"
    printf '\n  Содержимое (первые 20 строк):\n'
    head -20 "$f" | sed 's/^/    /'
    printf '\n'

    # Проверка наличия функций
    if grep -q 'def dashboard' "$f"; then
      printf '  ✓ Функция dashboard найдена\n'
    else
      printf '  ✗ ФУНКЦИЯ dashboard НЕ НАЙДЕНА\n'
    fi

    if [[ "$f" == "apps/crm/views.py" ]]; then
      if grep -q 'def login_view' "$f"; then
        printf '  ✓ Функция login_view найдена\n'
      else
        printf '  ✗ Функция login_view НЕ найдена\n'
      fi
    fi
    printf '\n'
  fi
done

# =============================================================================
#  2. Проверка .dockerignore
# =============================================================================
printf '== 2. Проверка .dockerignore ==\n\n'
if [[ -f .dockerignore ]]; then
  printf 'Содержимое .dockerignore:\n'
  sed 's/^/  /' .dockerignore
  printf '\n'

  if grep -q '^apps' .dockerignore || grep -q '^/apps' .dockerignore; then
    printf '  ✗ ВНИМАНИЕ: .dockerignore исключает директорию apps!\n'
    printf '  Это может быть причиной проблемы.\n\n'
  else
    printf '  ✓ apps не исключён в .dockerignore\n\n'
  fi
else
  printf '  .dockerignore не найден\n\n'
fi

# =============================================================================
#  3. Проверка Dockerfile
# =============================================================================
printf '== 3. Проверка Dockerfile ==\n\n'
if [[ -f Dockerfile ]]; then
  printf 'Строки COPY для apps:\n'
  grep -n 'COPY.*apps' Dockerfile | sed 's/^/  /' || printf '  Не найдено\n'
  printf '\n'
else
  printf '  Dockerfile не найден\n\n'
fi

# =============================================================================
#  4. Проверка образа ba/app:dev
# =============================================================================
printf '== 4. Проверка содержимого образа ba/app:dev ==\n\n'

if docker image inspect ba/app:dev >/dev/null 2>&1; then
  printf 'Образ существует. Проверяем содержимое apps/crm/views.py:\n\n'

  # Запускаем временный контейнер и читаем файл
  if docker run --rm ba/app:dev test -f /app/apps/crm/views.py; then
    printf 'Файл /app/apps/crm/views.py существует в образе\n'
    printf '\nСодержимое (первые 20 строк):\n'
    docker run --rm ba/app:dev head -20 /app/apps/crm/views.py | sed 's/^/  /'
    printf '\n'

    printf 'Проверка функции dashboard:\n'
    if docker run --rm ba/app:dev grep -q 'def dashboard' /app/apps/crm/views.py; then
      printf '  ✓ Функция dashboard найдена в образе\n\n'
    else
      printf '  ✗ ФУНКЦИЯ dashboard НЕ НАЙДЕНА в образе\n'
      printf '  Это означает, что образ содержит старую версию файла.\n\n'
    fi
  else
    printf '  ✗ Файл /app/apps/crm/views.py НЕ существует в образе\n\n'
  fi
else
  printf '  Образ ba/app:dev не существует\n\n'
fi

# =============================================================================
#  5. Проверка Docker build cache
# =============================================================================
printf '== 5. Проверка Docker build cache ==\n\n'
printf 'История сборки образа ba/app:dev:\n'
docker history ba/app:dev 2>/dev/null | head -20 | sed 's/^/  /' || printf '  Не удалось получить историю\n'
printf '\n'

# =============================================================================
#  6. Проверка compose.dev-lite.yml
# =============================================================================
printf '== 6. Проверка compose.dev-lite.yml ==\n\n'
if [[ -f compose.dev-lite.yml ]]; then
  printf 'Настройка volumes для сервиса web:\n'
  awk '/web:/,/^[^ ]/ { if (/volumes:/) found=1; if (found && /^  [^ ]/) exit; if (found) print }' compose.dev-lite.yml | sed 's/^/  /'
  printf '\n'
else
  printf '  compose.dev-lite.yml не найден\n\n'
fi

# =============================================================================
#  7. Рекомендации
# =============================================================================
printf '== 7. РЕКОМЕНДАЦИИ ==\n\n'

printf 'Если функция dashboard НЕ найдена на хосте:\n'
printf '  1. Запустите: bash fix_views_force.sh\n'
printf '  2. Проверьте, что файлы не пусты\n'
printf '  3. Повторите пересборку\n\n'

printf 'Если функция dashboard найдена на хосте, но НЕ в образе:\n'
printf '  1. Очистите Docker build cache:\n'
printf '     docker builder prune -a -f\n'
printf '  2. Пересоберите образ с флагом --no-cache:\n'
printf '     docker compose -f compose.yml -f compose.dev-lite.yml build --no-cache\n'
printf '  3. Запустите makemigrations\n\n'

printf 'Если .dockerignore исключает apps:\n'
printf '  1. Откройте .dockerignore\n'
printf '  2. Удалите строки, начинающиеся с apps или /apps\n'
printf '  3. Пересоберите образ\n\n'

printf 'Если права доступа неправильные:\n'
printf '  1. Запустите: bash fix_permissions.sh\n'
printf '  2. Пересоберите образ\n\n'

# =============================================================================
#  8. Автоматическое исправление (опционально)
# =============================================================================
printf '== 8. Автоматическое исправление ==\n\n'
printf 'Выполнить следующие команды автоматически? (y/n): '
read -r response

if [[ "$response" =~ ^[Yy]$ ]]; then
  printf '\n== Применение исправлений ==\n\n'

  # 1. Перезаписать views.py
  printf '1. Перезапись apps/crm/views.py...\n'
  cat > apps/crm/views.py <<'BA_EOF'
"""Заглушки представлений CRM."""
from __future__ import annotations

from django.http import HttpRequest, HttpResponseRedirect
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
  printf '  ✓ Готово\n\n'

  printf '2. Перезапись apps/catalog/views.py...\n'
  cat > apps/catalog/views.py <<'BA_EOF'
"""Заглушки представлений каталога."""
from __future__ import annotations

from django.http import HttpRequest, JsonResponse
from django.template.response import TemplateResponse


def home(request: HttpRequest) -> TemplateResponse:
    return TemplateResponse(request, "catalog/home.html", {"title": "Breaktime Arcade"})


def game_list(request: HttpRequest) -> TemplateResponse:
    return TemplateResponse(request, "catalog/game_list.html", {"title": "Каталог"})


def game_detail(request: HttpRequest, slug: str) -> JsonResponse:
    return JsonResponse({"status": "stub", "slug": slug})


def game_play(request: HttpRequest, slug: str) -> JsonResponse:
    return JsonResponse({"status": "stub", "slug": slug})


def game_leaderboard(request: HttpRequest, slug: str) -> JsonResponse:
    return JsonResponse({"status": "stub", "slug": slug})


def genre_detail(request: HttpRequest, slug: str) -> JsonResponse:
    return JsonResponse({"status": "stub", "slug": slug})
BA_EOF
  chmod 644 apps/catalog/views.py
  printf '  ✓ Готово\n\n'

  printf '3. Очистка Docker build cache...\n'
  docker builder prune -a -f
  printf '  ✓ Готово\n\n'

  printf '4. Пересборка образа...\n'
  docker compose -f compose.yml -f compose.dev-lite.yml build --no-cache
  printf '  ✓ Готово\n\n'

  printf '5. Запуск makemigrations...\n'
  docker compose -f compose.yml -f compose.dev-lite.yml run --rm \
      -e RUN_MIGRATIONS=0 -e RUN_COLLECTSTATIC=0 \
      web python manage.py makemigrations --noinput accounts catalog i18n theme
  printf '  ✓ Готово\n\n'

  printf '6. Применение миграций...\n'
  docker compose -f compose.yml -f compose.dev-lite.yml run --rm \
      -e RUN_MIGRATIONS=0 -e RUN_COLLECTSTATIC=0 \
      web python manage.py migrate --noinput
  printf '  ✓ Готово\n\n'

  printf '7. Подъём стека...\n'
  docker compose -f compose.yml -f compose.dev-lite.yml --profile beat up -d --force-recreate
  printf '  ✓ Готово\n\n'

  sleep 20

  printf '== Проверка ==\n\n'
  docker compose -f compose.yml -f compose.dev-lite.yml ps
  printf '\nhealthz: '
  curl -sk https://portal.test:8443/healthz || printf '(нет ответа)'
  printf '\n'
else
  printf '\nАвтоматическое исправление отменено.\n'
fi
