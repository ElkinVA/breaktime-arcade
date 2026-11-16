#!/usr/bin/env bash
# verify_backup.sh — пересборка, миграции, прогон бэкапа и restore-check.
set -euo pipefail
cd "$(dirname "$0")"

COMPOSE=(docker compose -f compose.yml -f compose.dev-lite.yml)

echo "============================================================"
echo "  Проверка бэкапов"
echo "============================================================"

echo
echo "==> [1] Пересборка образа (postgresql-client-18)"
"${COMPOSE[@]}" build web

echo
echo "==> [2] Миграция для BackupRun"
"${COMPOSE[@]}" run --rm \
    -e RUN_MIGRATIONS=0 -e RUN_COLLECTSTATIC=0 \
    web python manage.py makemigrations crm
"${COMPOSE[@]}" run --rm \
    -e RUN_MIGRATIONS=0 -e RUN_COLLECTSTATIC=0 \
    web python manage.py migrate --noinput

echo
echo "==> [3] Перезапуск web (нужен для проверки readyz)"
"${COMPOSE[@]}" up -d --force-recreate web
sleep 6

echo
echo "==> [4] Полный бэкап"
"${COMPOSE[@]}" --profile backup run --rm backup
echo
echo "==> [5] Проверка восстановления"
"${COMPOSE[@]}" --profile restore-check run --rm restore-check

echo
echo "==> [6] Записи BackupRun"
"${COMPOSE[@]}" exec -T web python manage.py shell -c "
from apps.crm.models import BackupRun
for r in BackupRun.objects.order_by('-started_at')[:5]:
    sha = (r.sha256[:16] + '...') if r.sha256 else ''
    print(f'{str(r.id)[:8]}  {r.type:14s}  {r.status:8s}  {r.started_at:%H:%M:%S}  size={r.size_bytes or 0}  {sha}')
"

echo
echo "==> [7] readyz должен включать backup=ok"
set +e
curl -sk --max-time 5 https://portal.test:8443/readyz | python3 -m json.tool
RC=$?
set -e

echo
echo "============================================================"
echo "  Проверка завершена"
echo "============================================================"
exit $RC
