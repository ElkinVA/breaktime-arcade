#!/usr/bin/env bash
# fix_staging_robots_ip.sh
# Идемпотентный фикс staging nginx (после BA-001):
#   1. /robots.txt: return 200 -> отдача реального файла (auth_basic теперь применяется)
#   2. allowlist: + 172.16.0.0/12 (Docker bridge), иначе с хоста 403 раньше auth
#   3. перерендер staging.conf, пересоздание nginx (без пересборки образа)
#   4. фактические проверки: /robots.txt 401 без auth, 200 + Disallow: / с auth;
#      /healthz 200, /en/ 200; listener на 8444
#   5. регрессия dev-lite + backup/restore-check
# Норматив: BA-PLAT-4.2 §2.5, §2.20. Баги: BA-001 (закрыт), BA-002.
set -euo pipefail
cd "$(dirname "$0")"

COMPOSE=(docker compose -p ba-staging -f compose.yml -f compose.staging.yml --env-file .env.staging)
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR=".backups/staging-robots-$STAMP"
FAIL=0

step() { printf '\n==> %s\n' "$*"; }
ok()   { printf '  OK:   %s\n' "$*"; }
warn() { printf '  WARN: %s\n' "$*"; }
fail() { printf '  FAIL: %s\n' "$*"; FAIL=1; }

# ---------- 0. prereq ----------
step "[0] Проверка prereq"
for f in compose.staging.yml infra/nginx/staging.conf.j2 .env.staging; do
    [ -f "$f" ] || { echo "FAIL: $f отсутствует"; exit 1; }
done
# Проверить, что BA-001 закрыт: ключ читается (файл существует и права позволяют чтение)
[ -r certs/staging.test-key.pem ] || { echo "FAIL: certs/staging.test-key.pem недоступен для чтения (BA-001 не закрыт?)"; exit 1; }
ok "prereq в порядке, ключ читается"

# ---------- 1. backup ----------
step "[1] Backup изменяемых файлов"
mkdir -p "$BACKUP_DIR/infra/nginx"
cp -p compose.staging.yml "$BACKUP_DIR/compose.staging.yml"
cp -p infra/nginx/staging.conf.j2 "$BACKUP_DIR/infra/nginx/staging.conf.j2"
[ -f infra/nginx/staging.conf ] && cp -p infra/nginx/staging.conf "$BACKUP_DIR/infra/nginx/staging.conf"
ok "backup: $BACKUP_DIR"

# ---------- 2. robots.txt file ----------
step "[2] Файл infra/nginx/staging-robots.txt"
if [ ! -f infra/nginx/staging-robots.txt ]; then
    printf 'User-agent: *\nDisallow: /\n' > infra/nginx/staging-robots.txt
    ok "создан"
else
    ok "уже существует"
fi
chmod 644 infra/nginx/staging-robots.txt

# ---------- 3. patch .j2 ----------
step "[3] Патч infra/nginx/staging.conf.j2"
python3 - <<'PY'
import pathlib
p = pathlib.Path("infra/nginx/staging.conf.j2")
text = p.read_text(encoding="utf-8")
changes = []

# 3a. allowlist: + Docker bridge range
old_allow = "        allow ${STAGING_ALLOW_IP};\n        deny all;"
new_allow = ("        allow ${STAGING_ALLOW_IP};\n"
             "        allow 172.16.0.0/12;  # Docker bridge (source IP при host->container)\n"
             "        deny all;")
if old_allow in text:
    text = text.replace(old_allow, new_allow, 1)
    changes.append("allowlist: + 172.16.0.0/12")
elif "allow 172.16.0.0/12" in text:
    changes.append("allowlist: уже содержит 172.16.0.0/12")
else:
    changes.append("WARN: блок allowlist не найден — правьте вручную")

# 3b. robots: return 200 -> root (access phase применяется до content phase)
old_robots = (
    "        location = /robots.txt {\n"
    "            default_type text/plain;\n"
    '            return 200 "User-agent: *\\nDisallow: /\\n";\n'
    "        }"
)
new_robots = (
    "        location = /robots.txt {\n"
    "            default_type text/plain;\n"
    "            root /etc/nginx/static;\n"
    "        }"
)
if old_robots in text:
    text = text.replace(old_robots, new_robots, 1)
    changes.append("robots: return 200 -> root /etc/nginx/static (auth_basic применяется)")
elif "root /etc/nginx/static;" in text:
    changes.append("robots: уже использует root /etc/nginx/static")
else:
    changes.append("WARN: location = /robots.txt не найден — правьте вручную")

p.write_text(text, encoding="utf-8")
for c in changes:
    print("  " + c)
PY

# ---------- 4. patch compose.staging.yml: mount robots.txt ----------
step "[4] Патч compose.staging.yml (mount robots.txt)"
python3 - <<'PY'
import pathlib
p = pathlib.Path("compose.staging.yml")
text = p.read_text(encoding="utf-8")
if "staging-robots.txt" in text:
    print("  OK:   volume mount уже присутствует")
else:
    anchor = "      - ./infra/nginx/staging.conf:/etc/nginx/nginx.conf:ro\n"
    mount  = "      - ./infra/nginx/staging-robots.txt:/etc/nginx/static/robots.txt:ro\n"
    if anchor in text:
        text = text.replace(anchor, anchor + mount, 1)
        p.write_text(text, encoding="utf-8")
        print("  OK:   volume mount добавлен")
    else:
        print("  WARN: якорь nginx.conf не найден — добавьте вручную:")
        print("        " + mount.strip())
PY

# ---------- 5. re-render staging.conf ----------
step "[5] Перерендер infra/nginx/staging.conf"
set -a
# shellcheck disable=SC1091
. ./.env.staging
set +a
envsubst '${STAGING_DOMAIN} ${STAGING_ALLOW_IP} ${SSL_CERT} ${SSL_KEY}' \
    < infra/nginx/staging.conf.j2 > infra/nginx/staging.conf
chmod 644 infra/nginx/staging.conf
grep -nE 'allow 127|allow 172|root /etc/nginx/static' infra/nginx/staging.conf | sed 's/^/  /' || true
ok "staging.conf перерендерен"

# ---------- 6. recreate nginx ----------
step "[6] Пересоздание nginx (без пересборки образа)"
"${COMPOSE[@]}" up -d --force-recreate nginx

# ---------- 7. wait listener ----------
step "[7] Ожидание listener (до 60s)"
STAGING_PORT="$(grep -E '^STAGING_PORT=' .env.staging | cut -d= -f2- || true)"
STAGING_PORT="${STAGING_PORT:-8444}"
STAGING_DOMAIN="$(grep -E '^STAGING_DOMAIN=' .env.staging | cut -d= -f2- || true)"
STAGING_DOMAIN="${STAGING_DOMAIN:-staging.test}"

deadline=$(( $(date +%s) + 60 ))
ready=0
while [ "$(date +%s)" -lt "$deadline" ]; do
    code="$(curl -sk --max-time 3 -o /dev/null -w '%{http_code}' "https://127.0.0.1:${STAGING_PORT}/robots.txt" 2>/dev/null)"
    code="${code:-000}"
    if [ "$code" != "000" ] && [ "$code" != "000000" ]; then
        ready=1
        ok "порт ${STAGING_PORT} отвечает (HTTP $code)"
        break
    fi
    sleep 2
done
[ "$ready" = "1" ] || fail "порт ${STAGING_PORT} не отвечает после 60s"

# ---------- 8. HTTP checks ----------
step "[8] HTTP-проверки"
check_code() {
    local expected="$1" desc="$2" url="$3" auth="${4:-}"
    local code
    if [ -n "$auth" ]; then
        code="$(curl -sk --max-time 5 -u "$auth" -o /dev/null -w '%{http_code}' "$url" 2>/dev/null)"
    else
        code="$(curl -sk --max-time 5 -o /dev/null -w '%{http_code}' "$url" 2>/dev/null)"
    fi
    code="${code:-000}"
    if [ "$code" = "$expected" ]; then
        ok "$desc: $code"
    else
        fail "$desc: $code (ожидалось $expected)"
    fi
}

check_code 401 "/robots.txt без auth" "https://${STAGING_DOMAIN}:${STAGING_PORT}/robots.txt"

if [ -f creds/staging_basic_auth.txt ]; then
    AUTH_USER="$(awk -F: 'NR==1{print $1}' creds/staging_basic_auth.txt)"
    AUTH_PASS="$(awk -F: 'NR==1{print $2}' creds/staging_basic_auth.txt)"
    AUTH="${AUTH_USER}:${AUTH_PASS}"
    check_code 200 "/robots.txt с auth" "https://${STAGING_DOMAIN}:${STAGING_PORT}/robots.txt" "$AUTH"
    check_code 200 "/healthz с auth"    "https://${STAGING_DOMAIN}:${STAGING_PORT}/healthz"    "$AUTH"
    check_code 200 "/en/ с auth"        "https://${STAGING_DOMAIN}:${STAGING_PORT}/en/"        "$AUTH"
    ROBOTS_BODY="$(curl -sk --max-time 5 -u "$AUTH" "https://${STAGING_DOMAIN}:${STAGING_PORT}/robots.txt" 2>/dev/null || true)"
    if printf '%s' "$ROBOTS_BODY" | grep -q "Disallow: /"; then
        ok "/robots.txt с auth содержит Disallow: /"
    else
        fail "/robots.txt с auth не содержит Disallow: /"
    fi
else
    warn "creds/staging_basic_auth.txt отсутствует — auth-проверки пропущены"
fi

# ---------- 9. regression dev-lite ----------
step "[9] Регрессия dev-lite"
if [ -x ./verify_stack.sh ]; then
    if ./verify_stack.sh >/tmp/ba-verify-stack.log 2>&1; then
        ok "dev-lite здоров (/tmp/ba-verify-stack.log)"
    else
        fail "dev-lite требует внимания (/tmp/ba-verify-stack.log)"
    fi
else
    warn "./verify_stack.sh не найден — проверьте вручную: make backup && make restore-check"
fi

# ---------- 10. итог ----------
step "[10] Итог"
if [ "$FAIL" = "0" ]; then
    printf '\n===== STAGING NGINX: OK =====\n'
    printf 'Backup: %s\n' "$BACKUP_DIR"
    exit 0
else
    printf '\n===== STAGING NGINX: ЕСТЬ ПРОБЛЕМЫ =====\n'
    printf 'Backup: %s\n' "$BACKUP_DIR"
    printf 'Логи: %s logs --tail=40 nginx\n' "${COMPOSE[*]}"
    exit 1
fi
