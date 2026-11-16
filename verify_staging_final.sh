#!/usr/bin/env bash
# verify_staging_final.sh — только read-only проверки staging (BA-PLAT §2.5).
# Без изменения конфигов, без пересборки, без удаления volumes.
set -uo pipefail   # НЕ -e: curl при connection refused выходит с кодом 7

cd "$(dirname "$0")/.."

COMPOSE=(docker compose -p ba-staging -f compose.yml -f compose.staging.yml --env-file .env.staging)
FAIL=0
step() { printf '\n==> %s\n' "$*"; }
ok()   { printf '  OK:   %s\n' "$*"; }
fail() { printf '  FAIL: %s\n' "$*"; FAIL=1; }

STAGING_PORT="$(grep -E '^STAGING_PORT=' .env.staging 2>/dev/null | cut -d= -f2-)"
STAGING_PORT="${STAGING_PORT:-8444}"
STAGING_DOMAIN="$(grep -E '^STAGING_DOMAIN=' .env.staging 2>/dev/null | cut -d= -f2-)"
STAGING_DOMAIN="${STAGING_DOMAIN:-staging.test}"

step "[1] Контейнер nginx"
if "${COMPOSE[@]}" ps nginx 2>/dev/null | grep -qE 'Up .*\(healthy\)'; then
    ok "nginx healthy"
else
    fail "nginx не healthy"; "${COMPOSE[@]}" ps nginx 2>/dev/null || true
fi

step "[2] Listener на ${STAGING_PORT}"
if ss -tln 2>/dev/null | grep -q ":${STAGING_PORT}\b"; then
    ok "LISTEN :${STAGING_PORT}"
else
    fail "порт ${STAGING_PORT} не слушается"
fi

step "[3] HTTP-проверки"
code_of() { curl -sk --max-time 5 -o /dev/null -w '%{http_code}' "$@" 2>/dev/null || echo "000"; }

[ "$(code_of "https://${STAGING_DOMAIN}:${STAGING_PORT}/robots.txt")" = "401" ] \
    && ok "/robots.txt без auth: 401" || fail "/robots.txt без auth ≠ 401"

if [ -f creds/staging_basic_auth.txt ]; then
    AU="$(awk -F: 'NR==1{print $1}' creds/staging_basic_auth.txt)"
    AP="$(awk -F: 'NR==1{print $2}' creds/staging_basic_auth.txt)"
    [ "$(code_of -u "${AU}:${AP}" "https://${STAGING_DOMAIN}:${STAGING_PORT}/healthz")" = "200" ] \
        && ok "/healthz с auth: 200" || fail "/healthz с auth ≠ 200"
    [ "$(code_of -u "${AU}:${AP}" "https://${STAGING_DOMAIN}:${STAGING_PORT}/en/")" = "200" ] \
        && ok "/en/ с auth: 200"     || fail "/en/ с auth ≠ 200"
    [ "$(code_of -u "${AU}:${AP}" "https://${STAGING_DOMAIN}:${STAGING_PORT}/robots.txt")" = "200" ] \
        && ok "/robots.txt с auth: 200" || fail "/robots.txt с auth ≠ 200"
    BODY="$(curl -sk --max-time 5 -u "${AU}:${AP}" "https://${STAGING_DOMAIN}:${STAGING_PORT}/robots.txt" 2>/dev/null || true)"
    printf '%s' "$BODY" | grep -q "Disallow: /" \
        && ok "тело robots содержит Disallow: /" || fail "тело robots без Disallow: /"
else
    fail "creds/staging_basic_auth.txt отсутствует"
fi

step "[4] Регрессия dev-lite"
if [ -x ./verify_stack.sh ]; then
    if ./verify_stack.sh >/tmp/ba-verify-stack.log 2>&1; then
        ok "dev-lite здоров (/tmp/ba-verify-stack.log)"
    else
        fail "dev-lite требует внимания (/tmp/ba-verify-stack.log)"
    fi
else
    fail "./verify_stack.sh не найден"
fi

step "[5] Итог"
if [ "$FAIL" = "0" ]; then
    printf '\n===== STAGING: OK =====\n'; exit 0
else
    printf '\n===== STAGING: ЕСТЬ ПРОБЛЕМЫ =====\n'; exit 1
fi
