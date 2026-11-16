#!/usr/bin/env bash
# Исправление прав на именованных томах static_data, media_data, app_var.
# Идемпотентен: безопасен при повторном запуске.
set -euo pipefail
cd "$(dirname "$0")"

COMPOSE=(docker compose -f compose.yml -f compose.dev-lite.yml)

echo "==> 1. Остановка стека"
"${COMPOSE[@]}" down

echo "==> 2. Исправление прав на томах (root → 10001:10001)"
"${COMPOSE[@]}" run --rm --no-deps --user root --entrypoint sh web -c '
  for d in /app/staticfiles /app/media /app/var; do
    if [ -d "$d" ]; then
      chown -R 10001:10001 "$d"
      chmod -R u+rwX "$d"
      echo "  fixed: $d"
    else
      echo "  skip:  $d (отсутствует)"
    fi
  done
'

echo "==> 3. Пересборка образа web без кэша (на случай устаревших слоёв)"
"${COMPOSE[@]}" build --no-cache web

echo "==> 4. Запуск стека"
"${COMPOSE[@]}" --profile beat up -d --force-recreate

echo "==> 5. Ожидание 20 секунд"
sleep 20

echo "==> 6. Статус контейнеров"
"${COMPOSE[@]}" ps

echo "==> 7. Проверка healthz"
curl -sk https://portal.test:8443/healthz && echo || echo "healthz не отвечает"

echo "==> 8. Последние 30 строк логов web"
"${COMPOSE[@]}" logs --tail=30 web
