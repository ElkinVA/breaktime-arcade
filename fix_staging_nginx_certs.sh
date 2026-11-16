#!/usr/bin/env bash
# fix_staging_nginx_certs.sh
# Идемпотентный фикс staging nginx:
#   1. chmod 644 на cert/key/htpasswd (locally-staging; в prod — секреты Docker/LE)
#   2. healthcheck в compose.staging.yml: замена nginx -t на nc -z (BA-002)
#   3. --force-recreate nginx (без пересборки образа, без удаления volumes)
#   4. фактические HTTP-проверки: /robots.txt 401, /healthz 200, /en/ 200, Disallow: /
#   5. регрессия dev-lite
# Норматив: BA-PLAT-4.2 §2.5, §2.20; баги BA-001, BA-002.
set -euo pipefail
cd "$(dirname "$0")"

COMPOSE=(docker compose -p ba-staging -f compose.yml -f compose.staging.yml --env-file .env.staging)
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR=".backups/staging-nginx-$STAMP"
FAIL=0

step() { printf '\n==> %s\n' "$*"; }
ok()   { printf '  OK:   %s\n' "$*"; }
warn() { printf '  WARN: %s\n' "$*"; }
fail() { printf '  FAIL: %s\n' "$*"; FAIL=1; }

step "[0] Проверка prereq"
[ -f compose.staging.yml ] || { echo "FAIL: compose.staging.yml отсутствует"; exit 1; }
[ -f .env.staging ]        || { echo "FAIL: .env.staging отсутствует"; exit 1; }
[ -d certs ]               || { echo "FAIL: каталог certs отсутствует"; exit 1; }
ok "все нужные файлы на месте"

step "[1] Права на сертификат, ключ и htpasswd"
for f in certs/staging.test.pem certs/staging.test-key.pem certs/htpasswd; do
    if [ ! -f "$f" ]; then
        fail "$f не существует"; continue
    fi
    perms=$(stat -c '%a' "$f")
    if [ "$perms" != "644" ]; then
        chmod 644 "$f"
        ok "$f: $perms → 644"
    else
        ok "$f: уже 644"
    fi
done

step "[2] Healthcheck в compose.staging.yml"
if grep -q '"CMD", "nginx", "-t"' compose.staging.yml 2>/dev/null; then
    mkdir -p "$BACKUP_DIR"
    cp -p compose.staging.yml "$BACKUP_DIR/compose.staging.yml"
    ok "backup: $BACKUP_DIR/compose.staging.yml"
    python3 - <<'PY'
import pathlib
p = pathlib.Path("compose.staging.yml")
text = p.read_text(encoding="utf-8")
old = '''    healthcheck:
      test: ["CMD", "nginx", "-t"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s'''
new = '''    healthcheck:
      # BA-002: реальный listener, не только синтаксис конфига
      test: ["CMD-SHELL", "nc -z -w 3 127.0.0.1 8443 || exit 1"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s'''
if old in text:
    text = text.replace(old, new, 1)
    p.write_text(text, encoding="utf-8")
    print("  OK:   healthcheck заменён")
elif 'nc -z -w 3 127.0.0.1 8443' in text:
    print("  OK:   healthcheck уже исправлен")
else:
    print("  WARN: ожидаемый блок healthcheck не найден — правьте вручную")
PY
else
    ok "healthcheck уже не использует 'nginx -t'"
fi

step "[3] Перезапуск nginx"
"${COMPOSE[@]}" up -d --force-recreate nginx

step "[4] Ожидание listener (до 60s)"
STAGING_PORT="$(grep -E '^STAGING_PORT=' .env.staging | cut -d= -f2- || true)"
STAGING_PORT="${STAGING_PORT:-8444}"
STAGING_DOMAIN="$(grep -E '^STAGING_DOMAIN=' .env.staging | cut -d= -f2- || true)"
STAGING_DOMAIN="${STAGING_DOMAIN:-staging.test}"

deadline=$(( $(date +%s) + 60 ))
ready=0
while [ "$(date +%s)" -lt "$deadline" ]; do
    code=$(curl -sk --max-time 3 -o /dev/null -w '%{http_code}' "https://127.0.0.1:${STAGING_PORT}/robots.txt" 2>/dev/null || echo "000")
    if [ "$code" != "000" ]; then
        ready=1
        ok "порт ${STAGING_PORT} отвечает (HTTP $code)"
        break
    fi
    sleep 2
done
if [ "$ready" = "0" ]; then
    fail "порт ${STAGING_PORT} не отвечает после 60s"
    "${COMPOSE[@]}" logs --tail=20 nginx 2>&1 || true
fi

step "[5] HTTP-проверки"
check_code() {
    local expected="$1" desc="$2" url="$3" auth="${4:-}"
    local code
    if [ -n "$auth" ]; then
        code=$(curl -sk --max-time 5 -u "$auth" -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || echo "000")
    else
        code=$(curl -sk --max-time 5 -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || echo "000")
    fi
    if [ "$code" = "$expected" ]; then
        ok "$desc: $code"
    else
        fail "$desc: $code (ожидалось $expected)"
    fi
}

check_code 401 "/robots.txt без auth" "https://${STAGING_DOMAIN}:${STAGING_PORT}/robots.txt"

if [ -f creds/staging_basic_auth.txt ]; then
    AUTH_USER=$(awk -F: 'NR==1{print $1}' creds/staging_basic_auth.txt)
    AUTH_PASS=$(awk -F: 'NR==1{print $2}' creds/staging_basic_auth.txt)
    AUTH="${AUTH_USER}:${AUTH_PASS}"
    check_code 200 "/healthz с auth" "https://${STAGING_DOMAIN}:${STAGING_PORT}/healthz" "$AUTH"
    check_code 200 "/en/ с auth"     "https://${STAGING_DOMAIN}:${STAGING_PORT}/en/"     "$AUTH"
    ROBOTS_BODY=$(curl -sk --max-time 5 -u "$AUTH" "https://${STAGING_DOMAIN}:${STAGING_PORT}/robots.txt" 2>/dev/null || echo "")
    if echo "$ROBOTS_BODY" | grep -q "Disallow: /"; then
        ok "/robots.txt с auth содержит Disallow: /"
    else
        fail "/robots.txt с auth не содержит Disallow: /"
    fi
else
    warn "creds/staging_basic_auth.txt отсутствует — auth-проверки пропущены"
fi

step "[6] Регрессия dev-lite"
if [ -f ./verify_stack.sh ]; then
    if ./verify_stack.sh >/tmp/ba-verify-stack.log 2>&1; then
        ok "dev-lite здоров (см. /tmp/ba-verify-stack.log)"
    else
        fail "dev-lite требует внимания (см. /tmp/ba-verify-stack.log)"
    fi
else
    warn "./verify_stack.sh не найден — ручная проверка: make backup && make restore-check"
fi

step "[7] Итог"
if [ "$FAIL" = "0" ]; then
    printf '\n===== STAGING NGINX: OK =====\n'
    [ -d "$BACKUP_DIR" ] && printf 'Backup: %s\n' "$BACKUP_DIR"
    exit 0
else
    printf '\n===== STAGING NGINX: ЕСТЬ ПРОБЛЕМЫ =====\n'
    [ -d "$BACKUP_DIR" ] && printf 'Backup: %s\n' "$BACKUP_DIR"
    printf 'Логи: docker compose -p ba-staging -f compose.yml -f compose.staging.yml logs --tail=40 nginx\n'
    exit 1
fi
