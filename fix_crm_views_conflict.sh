#!/usr/bin/env bash
# =============================================================================
#  fix_crm_views_conflict.sh — устранение конфликта модуля и пакета
#
#  Корень проблемы: в каталоге apps/crm/ одновременно существуют
#    - файл   apps/crm/views.py      (с функцией dashboard)
#    - пакет  apps/crm/views/        (с пустым __init__.py)
#  Python при `from apps.crm import views` выбирает пакет, где нет
#  атрибута dashboard -> AttributeError.
#
#  Скрипт удаляет конфликтующий пакет apps/crm/views/ (в бэкап),
#  оставляя только модуль, и проверяет отсутствие подобных конфликтов
#  по всему проекту.
#
#  Запуск: bash fix_crm_views_conflict.sh [КАТАЛОГ] [--dry-run]
# =============================================================================
set -euo pipefail

TARGET="${1:-.}"
DRY=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) TARGET="$arg" ;;
  esac
done
cd "$TARGET"

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR=".backups/$STAMP"

printf '\n=== УСТРАНЕНИЕ КОНФЛИКТА apps/crm/views ===\n\n'

# 1. Ищем все конфликты "файл имя.py + директория имя/" по проекту
printf '== 1. Поиск конфликтов файл/пакет по всему проекту ==\n'
found_conflicts=0
while IFS= read -r -d '' dir; do
  parent="$(dirname "$dir")"
  name="$(basename "$dir")"
  if [[ -f "$parent/$name.py" ]]; then
    printf '  КОНФЛИКТ: %s.py  и  %s/\n' "$parent/$name" "$parent/$name"
    found_conflicts=$((found_conflicts + 1))
  fi
done < <(find apps config -type d -print0 2>/dev/null)

if (( found_conflicts == 0 )); then
  printf '  конфликтов не найдено — вероятно, уже исправлено или не воспроизводится.\n'
fi
printf '\n'

# 2. Перемещаем конфликтующий пакет в бэкап
printf '== 2. Перемещение пакета apps/crm/views/ в бэкап ==\n'
if [[ -d apps/crm/views ]]; then
  if (( DRY )); then
    printf '  DRY: переносим apps/crm/views/ -> %s/apps/crm/views/\n' "$BACKUP_DIR"
  else
    mkdir -p "$BACKUP_DIR/apps/crm"
    mv -f apps/crm/views "$BACKUP_DIR/apps/crm/views"
    printf '  OK: пакет перемещён в %s/apps/crm/views\n' "$BACKUP_DIR"
  fi
else
  printf '  SKIP: apps/crm/views/ уже отсутствует.\n'
fi
printf '\n'

# 3. Проверяем, что модуль на месте и содержит нужные функции
printf '== 3. Проверка apps/crm/views.py ==\n'
if [[ -f apps/crm/views.py ]]; then
  printf '  файл существует, %s байт.\n' "$(wc -c < apps/crm/views.py)"
  for fn in dashboard login_view logout_view; do
    if grep -q "def $fn" apps/crm/views.py; then
      printf '  ✓ def %s найдена.\n' "$fn"
    else
      printf '  ✗ def %s НЕ найдена — модуль повреждён.\n' "$fn"
    fi
  done
else
  printf '  ✗ Файл apps/crm/views.py НЕ найден. Создам минимальный модуль.\n'
  if (( DRY == 0 )); then
    cat > apps/crm/views.py <<'BA_EOF'
"""Представления CRM. Заглушки каркаса этапа 1."""
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
    printf '  OK: модуль создан.\n'
  fi
fi
printf '\n'

# 4. Проверяем, что других пакетов, маскирующих модули, не осталось
printf '== 4. Контрольная проверка конфликта после исправления ==\n'
if [[ -d apps/crm/views && -f apps/crm/views.py ]]; then
  printf '  ✗ Конфликт всё ещё присутствует!\n'
else
  printf '  ✓ Конфликт устранён: остался только модуль.\n'
fi
printf '\n'

# 5. Проверка импорта в изоляции
printf '== 5. Проверка импорта модуля ==\n'
if (( DRY == 0 )); then
  cat > /tmp/check_crm_views.py <<'PYEOF'
import sys
sys.path.insert(0, '.')
try:
    from apps.crm import views
    path = getattr(views, "__file__", "?")
    print(f"  импортирован: {path}")
    print(f"  dashboard:    {'да' if hasattr(views, 'dashboard') else 'НЕТ'}")
    print(f"  login_view:   {'да' if hasattr(views, 'login_view') else 'НЕТ'}")
    print(f"  logout_view:  {'да' if hasattr(views, 'logout_view') else 'НЕТ'}")
    if hasattr(views, "dashboard"):
        print("  ✓ модуль корректен")
    else:
        print("  ✗ модуль импортирован, но функций нет — импорт уходит в пакет")
        sys.exit(1)
except Exception as e:
    print(f"  ✗ ошибка импорта: {e}")
    sys.exit(1)
PYEOF
  python3 /tmp/check_crm_views.py
  rm -f /tmp/check_crm_views.py
else
  printf '  DRY: проверка импорта пропущена.\n'
fi

printf '\n=== ДАЛЬНЕЙШИЕ ШАГИ (после исправления) ===\n'
printf '  docker compose -f compose.yml -f compose.dev-lite.yml --profile beat up -d --force-recreate\n'
printf '  docker compose -f compose.yml -f compose.dev-lite.yml exec -T web python manage.py check\n'
printf '  docker compose -f compose.yml -f compose.dev-lite.yml exec -T web python manage.py makemigrations accounts catalog i18n theme\n'
printf '  docker compose -f compose.yml -f compose.dev-lite.yml exec -T web python manage.py migrate --noinput\n'
printf '\nЕсли контейнер всё ещё не стартует, пришлите:\n'
printf '  docker compose -f compose.yml -f compose.dev-lite.yml logs --tail=60 web\n'
