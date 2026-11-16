#!/usr/bin/env bash
# =============================================================================
#  fix_views_final.sh — финальное исправление проблемы views
#
#  Корневая причина: compose.dev-lite.yml использует bind-mount .:/app,
#  контейнер читает файлы с хоста. Файл apps/crm/views.py пуст или неполон.
#
#  Запуск: bash fix_views_final.sh [КАТАЛОГ]
# =============================================================================
set -euo pipefail

TARGET="${1:-.}"
cd "$TARGET"

printf '\n=== ФИНАЛЬНОЕ ИСПРАВЛЕНИЕ VIEWS ===\n\n'

# =============================================================================
#  1. Прямая проверка файлов на хосте
# =============================================================================
printf '== 1. Содержимое apps/crm/views.py на хосте ==\n\n'
if [[ -f apps/crm/views.py ]]; then
  printf 'Размер: %s байт\n' "$(wc -c < apps/crm/views.py)"
  printf 'Строк: %s\n' "$(wc -l < apps/crm/views.py)"
  printf '\nСодержимое:\n'
  cat apps/crm/views.py
  printf '\n'

  if grep -q 'def dashboard' apps/crm/views.py; then
    printf '✓ Функция dashboard найдена\n\n'
  else
    printf '✗ Функция dashboard НЕ найдена — перезаписываю\n\n'
  fi
else
  printf '✗ Файл не существует\n\n'
fi

# =============================================================================
#  2. Принудительная перезапись views.py
# =============================================================================
printf '== 2. Перезапись apps/crm/views.py ==\n\n'

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
printf '✓ Файл перезаписан\n'
printf 'Размер: %s байт\n' "$(wc -c < apps/crm/views.py)"
printf 'Функция dashboard: %s\n\n' "$(grep -c 'def dashboard' apps/crm/views.py)"

# =============================================================================
#  3. Перезапись apps/catalog/views.py
# =============================================================================
printf '== 3. Перезапись apps/catalog/views.py ==\n\n'

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
printf '✓ Файл перезаписан\n'
printf 'Размер: %s байт\n\n' "$(wc -c < apps/catalog/views.py)"

# =============================================================================
#  4. Проверка .dockerignore
# =============================================================================
printf '== 4. Проверка .dockerignore ==\n\n'
if [[ -f .dockerignore ]]; then
  if grep -E '^apps|^/apps' .dockerignore; then
    printf '✗ ВНИМАНИЕ: .dockerignore исключает apps!\n'
    printf 'Удаляю эти строки...\n'
    sed -i '/^apps\|^\/apps/d' .dockerignore
    printf '✓ Исправлено\n\n'
  else
    printf '✓ apps не исключён\n\n'
  fi
else
  printf '.dockerignore не найден\n\n'
fi

# =============================================================================
#  5. Остановка контейнеров и очистка кэша Python
# =============================================================================
printf '== 5. Остановка контейнеров ==\n\n'
docker compose -f compose.yml -f compose.dev-lite.yml down
printf '✓ Контейнеры остановлены\n\n'

# =============================================================================
#  6. Проверка импорта Python напрямую
# =============================================================================
printf '== 6. Проверка импорта Python напрямую ==\n\n'

# Создаём временный скрипт для проверки
cat > /tmp/check_views.py <<'PYEOF'
import sys
sys.path.insert(0, '/home/elkinva/projects/ba')

try:
    from apps.crm import views
    print(f"✓ Модуль apps.crm.views импортирован")
    print(f"  Атрибуты: {[attr for attr in dir(views) if not attr.startswith('_')]}")

    if hasattr(views, 'dashboard'):
        print(f"  ✓ Функция dashboard найдена")
    else:
        print(f"  ✗ Функция dashboard НЕ найдена")

    if hasattr(views, 'login_view'):
        print(f"  ✓ Функция login_view найдена")
    else:
        print(f"  ✗ Функция login_view НЕ найдена")

except Exception as e:
    print(f"✗ Ошибка импорта: {e}")
    import traceback
    traceback.print_exc()
PYEOF

python3 /tmp/check_views.py
printf '\n'

# =============================================================================
#  7. Запуск контейнеров
# =============================================================================
printf '== 7. Запуск контейнеров ==\n\n'
docker compose -f compose.yml -f compose.dev-lite.yml --profile beat up -d --force-recreate
printf '✓ Контейнеры запущены\n\n'

# =============================================================================
#  8. Ожидание и проверка
# =============================================================================
printf '== 8. Ожидание запуска (30 секунд) ==\n\n'
sleep 30

printf '== 9. Статус контейнеров ==\n\n'
docker compose -f compose.yml -f compose.dev-lite.yml ps
printf '\n'

printf '== 10. Проверка healthz ==\n\n'
if curl -sk https://portal.test:8443/healthz 2>/dev/null; then
  printf '\n✓ healthz отвечает\n\n'
else
  printf '\n✗ healthz не отвечает\n\n'
fi

printf '== 11. Последние логи web ==\n\n'
docker compose -f compose.yml -f compose.dev-lite.yml logs --tail=30 web
printf '\n'

# =============================================================================
#  12. Проверка доступа к файлам внутри контейнера
# =============================================================================
printf '== 12. Проверка файла внутри контейнера ==\n\n'
if docker compose -f compose.yml -f compose.dev-lite.yml exec web test -f /app/apps/crm/views.py 2>/dev/null; then
  printf '✓ Файл /app/apps/crm/views.py существует в контейнере\n'
  printf 'Содержимое (первые 20 строк):\n'
  docker compose -f compose.yml -f compose.dev-lite.yml exec web head -20 /app/apps/crm/views.py 2>/dev/null || true
  printf '\n'

  printf 'Проверка функции dashboard внутри контейнера:\n'
  if docker compose -f compose.yml -f compose.dev-lite.yml exec web grep -q 'def dashboard' /app/apps/crm/views.py 2>/dev/null; then
    printf '✓ Функция dashboard найдена в контейнере\n\n'
  else
    printf '✗ Функция dashboard НЕ найдена в контейнере\n'
    printf 'Это означает проблему с bind-mount или правами доступа\n\n'
  fi
else
  printf '✗ Файл не существует в контейнере\n\n'
fi

printf '=== ГОТОВО ===\n\n'
printf 'Если web всё ещё unhealthy, пришлите вывод:\n'
printf '  docker compose -f compose.yml -f compose.dev-lite.yml logs --tail=60 web\n'
