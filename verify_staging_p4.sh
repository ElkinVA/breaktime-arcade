#!/usr/bin/env bash
# verify_staging_p4.sh — read-only staging checks for ARCADE-P4 A4/R-042.
# Requires a real .env.staging. Never prints secrets; never starts/stops/removes
# containers or volumes; never runs an import outside the documented manual step.
set -uo pipefail

cd "$(dirname "$0")"
FAIL=0
step() { printf '\n==> %s\n' "$*"; }
ok()   { printf '  OK:   %s\n' "$*"; }
fail() { printf '  FAIL: %s\n' "$*"; FAIL=1; }

if [ ! -f .env.staging ]; then
    printf 'BLOCKED: .env.staging отсутствует; live staging NOT TESTED.\n'
    exit 3
fi

COMPOSE=(docker compose -p ba-staging -f compose.yml -f compose.staging.yml --env-file .env.staging)

step "[1] Compose config"
if "${COMPOSE[@]}" config --quiet >/dev/null 2>/tmp/ba-staging-config.err; then
    ok "compose config валиден"
else
    fail "compose config ошибка (см. /tmp/ba-staging-config.err)"
fi

step "[2] Сервисы"
if "${COMPOSE[@]}" ps --format '{{.Service}} {{.State}}' 2>/dev/null | grep -q '^zip-worker running'; then
    ok "zip-worker running"
else
    fail "zip-worker не running"
fi

step "[3] Ownership общих томов"
for svc in web zip-worker; do
    if "${COMPOSE[@]}" exec -T "$svc" sh -lc \
        'stat -c "%u:%g %a %n" /var/ba/zip/quota' 2>/dev/null | grep -q '^10001:10001 '; then
        ok "$svc: zip_quota uid 10001"
    else
        fail "$svc: zip_quota не uid 10001/недоступен"
    fi
done
if "${COMPOSE[@]}" exec -T web sh -lc \
    'stat -c "%u:%g %a %n" /app/runtime' 2>/dev/null | grep -q '^10001:10001 '; then
    ok "web: runtime uid 10001"
else
    fail "web: runtime не uid 10001"
fi

step "[4] ZIP worker isolation"
ID="$("${COMPOSE[@]}" ps -q zip-worker 2>/dev/null || true)"
if [ -n "$ID" ]; then
    READONLY="$(docker inspect "$ID" --format '{{.HostConfig.ReadonlyRootfs}}')"
    NET="$(docker inspect "$ID" --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}')"
    CAP="$(docker inspect "$ID" --format '{{json .HostConfig.CapDrop}}')"
    [ "$READONLY" = "true" ] && ok "read_only=true" || fail "read_only=$READONLY"
    printf '%s' "$NET" | grep -q 'zipnet' && ok "network zipnet" || fail "zipnet отсутствует: $NET"
    printf '%s' "$CAP" | grep -qi 'ALL' && ok "cap_drop ALL" || fail "cap_drop=$CAP"
else
    fail "zip-worker контейнер не найден"
fi

step "[5] ZIP artifact write / uploads read-only"
"${COMPOSE[@]}" exec -T zip-worker sh -lc \
    'touch /var/ba/zip/artifacts/.p4_probe && rm /var/ba/zip/artifacts/.p4_probe' >/dev/null 2>&1 \
    && ok "artifacts writable" || fail "artifacts не writable"
if "${COMPOSE[@]}" exec -T zip-worker sh -lc \
    'touch /var/ba/zip/uploads/.p4_probe' >/dev/null 2>&1; then
    fail "uploads writable для zip-worker (ожидалось read-only)"
    "${COMPOSE[@]}" exec -T zip-worker sh -lc 'rm -f /var/ba/zip/uploads/.p4_probe' >/dev/null 2>&1 || true
else
    ok "uploads read-only для zip-worker"
fi

step "[6] Backup/restore-check"
if make restore-check >/tmp/ba-staging-restore-check.log 2>&1; then
    ok "restore-check успешен"
else
    fail "restore-check ошибка (см. /tmp/ba-staging-restore-check.log)"
fi

step "[7] Итог"
if [ "$FAIL" = "0" ]; then
    printf '\n===== STAGING P4: OK =====\n'
    printf 'Дальше вручную: импорт/публикация реального ZIP через CRM и проверка iframe/SDK.\n'
    exit 0
else
    printf '\n===== STAGING P4: ЕСТЬ ПРОБЛЕМЫ =====\n'
    exit 1
fi
