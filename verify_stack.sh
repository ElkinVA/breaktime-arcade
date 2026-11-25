#!/usr/bin/env bash
# verify_stack.sh — проверка готовности стека с ожиданием healthcheck.
# Идемпотентен. Используется вместо ручного набора curl.
set -euo pipefail
cd "$(dirname "$0")"

COMPOSE=(docker compose -f compose.yml -f compose.dev-lite.yml)
WAIT_SECS="${WAIT_SECS:-90}"

echo "==> Ожидание healthy: web, db, redis-cache, redis-broker, redis-throttle, redis-zip (до ${WAIT_SECS}s)"
deadline=$(( $(date +%s) + WAIT_SECS ))
all_healthy=0
while [ "$(date +%s)" -lt "$deadline" ]; do
    status="$("${COMPOSE[@]}" ps --format json 2>/dev/null \
        | python3 -c '
import sys, json
ok_services = {"web","db","redis-cache","redis-broker","redis-throttle","redis-zip"}
ready = set()
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try: svc = json.loads(line)
    except Exception: continue
    name = svc.get("Service","")
    health = (svc.get("Health") or svc.get("Status") or "").lower()
    state = (svc.get("State") or "").lower()
    if name in ok_services:
        if "healthy" in health or (state == "running" and health in ("", "starting") and "healthy" not in health):
            # если healthcheck нет вообще — считаем healthy по state=running
            if "unhealthy" in health: continue
            if health.startswith("starting"): continue
            ready.add(name)
print(",".join(sorted(ready)))
' || echo "")"
    if [ "$status" = "db,redis-broker,redis-cache,redis-throttle,redis-zip,web" ]; then
        echo "  OK: все healthy"
        all_healthy=1
        break
    fi
    printf '  ждём... ready=[%s]\n' "$status"
    sleep 4
done

if [ "$all_healthy" -ne 1 ]; then
    echo "ОШИБКА: не все обязательные сервисы стали healthy за ${WAIT_SECS}s" >&2
    "${COMPOSE[@]}" ps --format 'table {{.Name}}\t{{.Status}}'
    exit 1
fi

echo
echo "==> Проверка HTTPS"
H="$(curl -sk --max-time 5 https://portal.test:8443/healthz || true)"
EN="$(curl -sk --max-time 5 -o /dev/null -w '%{http_code}' https://portal.test:8443/en/ || echo 000)"
CRM="$(curl -sk --max-time 5 -o /dev/null -w '%{http_code}' https://portal.test:8443/crm/ || echo 000)"
CSS="$(curl -sk --max-time 5 -o /dev/null -w '%{http_code}' https://portal.test:8443/static/dist/app.css || echo 000)"
JSF="$(curl -sk --max-time 5 -o /dev/null -w '%{http_code}' https://portal.test:8443/static/staticfiles.json || echo 000)"
GAME="$(curl -sk --max-time 5 -o /dev/null -w '%{http_code}' https://demo.games.test:8443/ || echo 000)"

echo "  /healthz                 -> ${H:-(нет ответа)}"
echo "  /en/                     -> $EN"
echo "  /crm/                    -> $CRM   (302 ожидаемо)"
echo "  /static/dist/app.css     -> $CSS"
echo "  /static/staticfiles.json -> $JSF"
echo "  games.host (demo.*)      -> $GAME  (404 ожидаемо)"

echo
echo "==> Статус контейнеров"
"${COMPOSE[@]}" ps --format 'table {{.Name}}\t{{.Status}}'

if [ "$EN" = "200" ] && [ "$CSS" = "200" ] && [ "$JSF" = "200" ]; then
    echo
    echo "============================================================"
    echo "  СТЕК ЗДОРОВ"
    echo "============================================================"
    exit 0
fi
echo
echo "============================================================"
echo "  ЕСТЬ ПРОБЛЕМЫ — см. вывод выше"
echo "============================================================"
exit 1
