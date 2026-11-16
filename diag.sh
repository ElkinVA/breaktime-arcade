#!/usr/bin/env bash
# Безопасная диагностика BreakTime Arcade.
# Ничего не исправляет и не изменяет в исходниках/БД.
# Единственный создаваемый файл — текстовый отчёт diagnostics_*.txt.

set -uo pipefail

ROOT="$(pwd)"
COMPOSE_FILES=(-f compose.yml -f compose.dev-lite.yml)
REPORT="diagnostics_$(date +%Y%m%d_%H%M%S).txt"

if [[ ! -f "$ROOT/compose.yml" ]]; then
  echo "ОШИБКА: запустите скрипт из корня проекта (рядом с compose.yml)." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ОШИБКА: Docker не найден." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "ОШИБКА: команда docker compose недоступна." >&2
  exit 1
fi

exec > >(tee "$REPORT") 2>&1

section() {
  printf '\n\n============================================================\n'
  printf '%s\n' "$1"
  printf '============================================================\n'
}

run_check() {
  local title="$1"
  shift
  printf '\n--- %s ---\n' "$title"
  "$@"
  local rc=$?
  printf '[exit code: %s]\n' "$rc"
  return 0
}

section "BREAKTIME ARCADE — ДИАГНОСТИЧЕСКИЙ ОТЧЁТ"
printf 'Дата: %s\n' "$(date -Is 2>/dev/null || date)"
printf 'Каталог: %s\n' "$ROOT"
printf 'Compose: %s\n' "${COMPOSE_FILES[*]}"
printf 'Режим: только чтение; автоматические исправления не выполняются.\n'

section "1. СОСТОЯНИЕ GIT И ФАЙЛОВ"
if command -v git >/dev/null 2>&1 && git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  run_check "Git status" git -C "$ROOT" status --short
  run_check "Последний commit" git -C "$ROOT" log -1 --oneline
else
  echo "Git-репозиторий не обнаружен."
fi

section "2. ПРОВЕРКА DOCKER COMPOSE"
run_check "Проверка compose-конфигурации" docker compose "${COMPOSE_FILES[@]}" config -q
run_check "Список сервисов" docker compose "${COMPOSE_FILES[@]}" config --services
run_check "Состояние контейнеров" docker compose "${COMPOSE_FILES[@]}" ps -a

section "3. КОНФЛИКТЫ PYTHON-МОДУЛЕЙ VIEWS"
echo "Файлы views.py:"
find apps -type f -name 'views.py' -print 2>/dev/null | sort
echo
echo "Каталоги views/:"
find apps -type d -name 'views' -print 2>/dev/null | sort
echo
echo "Пары файл/каталог с одинаковым базовым именем:"
while IFS= read -r file; do
  dir="${file%.py}"
  if [[ -d "$dir" ]]; then
    printf 'КОНФЛИКТ: %s  <->  %s/\n' "$file" "$dir"
  fi
done < <(find apps -type f -name 'views.py' -print 2>/dev/null | sort)

section "4. ПРОВЕРКА ПОДОЗРИТЕЛЬНЫХ ИМПОРТОВ И ПУСТЫХ ФАЙЛОВ"
echo "Упоминания Callable в middleware:"
grep -RIn --include='*.py' -E 'Callable|GetResponse' apps/*/middleware.py apps/*/middleware 2>/dev/null || true

echo
echo "Пустые Python-файлы в apps (первые 200):"
find apps -type f -name '*.py' -empty -print 2>/dev/null | sort | head -200
echo
echo "Количество пустых Python-файлов:"
find apps -type f -name '*.py' -empty -print 2>/dev/null | wc -l

echo
echo "Проверка синтаксиса Python на хосте (если Python доступен):"
if command -v python3 >/dev/null 2>&1; then
  python3 - <<'PY'
import ast
from pathlib import Path

roots = [Path("apps"), Path("config")]
checked = 0
failed = []
for root in roots:
    if not root.exists():
        continue
    for path in root.rglob("*.py"):
        try:
            source = path.read_text(encoding="utf-8")
            ast.parse(source, filename=str(path))
            checked += 1
        except Exception as exc:
            failed.append((str(path), repr(exc)))

print(f"Проверено файлов: {checked}")
if failed:
    print(f"Ошибок синтаксиса/чтения: {len(failed)}")
    for name, error in failed:
        print(f"  {name}: {error}")
else:
    print("Ошибок синтаксиса не обнаружено.")
PY
else
  echo "python3 на хосте не найден; пропуск."
fi

section "5. DJANGO CHECK В ОДНОРАЗОВОМ КОНТЕЙНЕРЕ"
echo "Запускается без зависимостей Compose и без изменения БД."
run_check "python manage.py check" \
  docker compose "${COMPOSE_FILES[@]}" run --rm --no-deps web python manage.py check

section "6. РАЗРЕШЕНИЕ КЛЮЧЕВЫХ PYTHON-МОДУЛЕЙ В КОНТЕЙНЕРЕ"
run_check "Пути импортируемых модулей" \
  docker compose "${COMPOSE_FILES[@]}" run --rm --no-deps web python -c '
import importlib.util
for name in ("apps.crm.views", "apps.catalog.views", "apps.i18n.middleware"):
    try:
        spec = importlib.util.find_spec(name)
        print(f"{name}: {None if spec is None else spec.origin}")
    except Exception as exc:
        print(f"{name}: IMPORT ERROR: {type(exc).__name__}: {exc}")
'

section "7. СОСТОЯНИЕ МИГРАЦИЙ"
run_check "showmigrations" \
  docker compose "${COMPOSE_FILES[@]}" run --rm --no-deps web python manage.py showmigrations

section "8. ПОСЛЕДНИЕ ЛОГИ WEB"
run_check "docker compose logs --tail=180 web" \
  docker compose "${COMPOSE_FILES[@]}" logs --tail=180 web

section "9. СВОДКА"
echo "Диагностика завершена."
echo "Отчёт сохранён: $ROOT/$REPORT"
echo "Скрипт не запускал migrate/makemigrations, не пересобирал образы и не редактировал файлы."
echo "Если manage.py check завершился ошибкой, ориентируйтесь на самый первый traceback в разделах 5 и 8."
