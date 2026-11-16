#!/usr/bin/env bash
# =============================================================================
#  fix_permissions.sh — исправление прав доступа для работы контейнера от UID 10001
#
#  Проблема: bind-mount директории проекта в контейнер требует, чтобы все файлы
#  были доступны для чтения "другим" пользователям (other).
#
#  Запуск: bash fix_permissions.sh [КАТАЛОГ] [--restart]
# =============================================================================
set -euo pipefail

TARGET="$PWD"; RESTART=0
for arg in "$@"; do
  case "$arg" in
    --restart)  RESTART=1 ;;
    -h|--help)  sed -n '2,8p' "$0"; exit 0 ;;
    *) TARGET="$arg" ;;
  esac
done
cd "$TARGET"

printf 'Исправление прав доступа в %s\n' "$PWD"

# Директории, которые пропускаем (принадлежат контейнеру)
SKIP_DIRS=(
  './staticfiles'
  './var'
  './media'
  './pgdata'
  './redis-data'
  './redis_cache_data'
  './redis_broker_data'
)

# Функция проверки, нужно ли пропустить путь
should_skip() {
  local path="$1"
  for skip in "${SKIP_DIRS[@]}"; do
    if [[ "$path" == "$skip"* ]]; then
      return 0
    fi
  done
  return 1
}

# Файлы: 644 (rw-r--r--)
printf 'Обработка файлов...\n'
find . -type f \
  -not -path './.git/*' \
  -not -path './node_modules/*' \
  -not -path './.venv/*' \
  -not -path './venv/*' \
  -not -path './__pycache__/*' \
  -not -path './.pytest_cache/*' \
  -not -path './.mypy_cache/*' \
  -not -path './.ruff_cache/*' \
  -not -path './staticfiles/*' \
  -not -path './media/*' \
  -not -path './pgdata/*' \
  -not -path './redis-data/*' \
  -not -path './backups/*' \
  -not -path './.backups/*' \
  -not -path './var/*' \
  2>/dev/null | while IFS= read -r file; do
    if ! should_skip "$file"; then
      chmod 644 "$file" 2>/dev/null || true
    fi
  done

# Скрипты: 755 (rwxr-xr-x)
printf 'Обработка скриптов...\n'
find . -type f -name '*.sh' \
  -not -path './.git/*' \
  2>/dev/null | while IFS= read -r file; do
    if ! should_skip "$file"; then
      chmod 755 "$file" 2>/dev/null || true
    fi
  done

# Директории: 755 (rwxr-xr-x)
printf 'Обработка директорий...\n'
find . -type d \
  -not -path './.git/*' \
  -not -path './node_modules/*' \
  -not -path './.venv/*' \
  -not -path './venv/*' \
  -not -path './__pycache__/*' \
  -not -path './.pytest_cache/*' \
  -not -path './.mypy_cache/*' \
  -not -path './.ruff_cache/*' \
  -not -path './staticfiles/*' \
  -not -path './media/*' \
  -not -path './pgdata/*' \
  -not -path './redis-data/*' \
  -not -path './backups/*' \
  -not -path './.backups/*' \
  -not -path './var/*' \
  2>/dev/null | while IFS= read -r dir; do
    if ! should_skip "$dir"; then
      chmod 755 "$dir" 2>/dev/null || true
    fi
  done

printf 'Права исправлены:\n'
printf '  Файлы:      644 (rw-r--r--)\n'
printf '  Скрипты:    755 (rwxr-xr-x)\n'
printf '  Директории: 755 (rwxr-xr-x)\n'
printf '  Пропущены:  staticfiles, var, media (принадлежат контейнеру)\n'

if (( RESTART )); then
  printf '\nПерезапускаю контейнеры...\n'
  docker compose -f compose.yml -f compose.dev-lite.yml --profile beat up -d --force-recreate
  sleep 8

  printf '\nПроверка запуска Django:\n'
  if docker compose -f compose.yml -f compose.dev-lite.yml exec -T web python manage.py check 2>&1; then
    printf '\n✓ Контейнеры запущены успешно!\n'
    printf '\nПроверка:\n'
    printf '  curl -k https://portal.test:8443/healthz\n'
    printf '  curl -k https://portal.test:8443/en/\n'
  else
    printf '\n✗ Ошибка запуска. Проверьте логи:\n'
    printf '  docker compose -f compose.yml -f compose.dev-lite.yml logs web\n'
    exit 1
  fi
else
  cat <<'BA_EOF'

Следующие шаги:
  docker compose -f compose.yml -f compose.dev-lite.yml --profile beat up -d --force-recreate
  sleep 8
  docker compose -f compose.yml -f compose.dev-lite.yml exec -T web python manage.py check

Или одной командой:
  bash fix_permissions.sh --restart
BA_EOF
fi
