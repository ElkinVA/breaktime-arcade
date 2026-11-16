#!/usr/bin/env bash
# staging.sh — управление staging-окружением (§2.5).
# Использование:
#   ./infra/scripts/staging.sh up       # поднять, дождаться healthy, тест
#   ./infra/scripts/staging.sh down     # остановить (тома сохраняются)
#   ./infra/scripts/staging.sh reset    # остановить + удалить тома
#   ./infra/scripts/staging.sh status   # статус контейнеров
#   ./infra/scripts/staging.sh logs     # логи web+nginx
#   ./infra/scripts/staging.sh url      # показать URL и логин/пароль
#   ./infra/scripts/staging.sh creds    # показать логин/пароль basic auth
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

PROJECT="ba-staging"
ENV_FILE=".env.staging"
COMPOSE=(docker compose -p "$PROJECT" -f compose.yml -f compose.staging.yml --env-file "$ENV_FILE")

# ---- Проверки и подготовка -------------------------------------------------
require_env() {
    if [ ! -f "$ENV_FILE" ]; then
        echo "FAIL: $ENV_FILE отсутствует. Запустите:" >&2
        echo "  ./infra/scripts/gen_staging_env.sh" >&2
        exit 1
    fi
}

# Загрузить env staging в текущий shell (нужен для рендеринга nginx)
load_env() {
    require_env
    set -a
    # shellcheck disable=SC1090
    . "./$ENV_FILE"
    set +a
}

# Убедиться, что сертификат существует (mkcert)
ensure_cert() {
    local domain="${STAGING_DOMAIN:-staging.test}"
    local cert="certs/${domain}.pem"
    local key="certs/${domain}-key.pem"
    if [ -f "$cert" ] && [ -f "$key" ]; then
        return 0
    fi
    if ! command -v mkcert >/dev/null 2>&1; then
        echo "FAIL: mkcert не установлен — установите и повторите" >&2
        echo "  sudo apt install libnss3-tools" >&2
        exit 1
    fi
    mkcert -install >/dev/null 2>&1 || true
    mkcert -cert-file "$cert" -key-file "$key" "$domain" >/dev/null
    echo "  сертификат создан: $cert"
}

# Отрендерить staging.conf из .j2
render_nginx() {
    local template="infra/nginx/staging.conf.j2"
    local out="infra/nginx/staging.conf"
    [ -f "$template" ] || { echo "FAIL: $template отсутствует" >&2; exit 1; }
    envsubst '${STAGING_DOMAIN} ${STAGING_ALLOW_IP} ${SSL_CERT} ${SSL_KEY}' \
        < "$template" > "$out"
    chmod 644 "$out"
    echo "  nginx: $out"
}

# Проверить /etc/hosts
check_hosts() {
    local domain="${STAGING_DOMAIN:-staging.test}"
    if ! grep -qE "(^|[[:space:]])${domain}([[:space:]]|$)" /etc/hosts 2>/dev/null; then
        echo
        echo "  ВНИМАНИЕ: $domain не в /etc/hosts." >&2
        echo "  Добавьте (требуется sudo):" >&2
        echo "    echo '127.0.0.1 ${domain}' | sudo tee -a /etc/hosts" >&2
        echo
    fi
}

# ---- Субкоманды -----------------------------------------------------------
cmd_up() {
    load_env
    ensure_cert
    check_hosts
    echo "==> Рендеринг nginx-конфига"
    render_nginx

    echo
    echo "==> Запуск staging"
    "${COMPOSE[@]}" up -d

    echo
    echo "==> Ожидание healthy (до 120s)"
    local deadline=$(( $(date +%s) + 120 ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        local st
        st="$("${COMPOSE[@]}" ps --format json 2>/dev/null \
            | python3 -c '
import sys, json
need = {"web","db","redis-cache","redis-broker"}
ready = set()
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try: s = json.loads(line)
    except Exception: continue
    n = s.get("Service",""); h = (s.get("Health") or "").lower(); st = (s.get("State") or "").lower()
    if n in need and st == "running":
        if "unhealthy" in h: continue
        if h.startswith("starting"): continue
        ready.add(n)
print(",".join(sorted(ready)))
')"
        if [ "$st" = "db,redis-broker,redis-cache,web" ]; then
            echo "  OK: все healthy"
            break
        fi
        printf '  ждём... ready=[%s]\n' "$st"
        sleep 4
    done

    echo
    echo "==> Проверка"
    local port="${STAGING_PORT:-8444}"
    local domain="${STAGING_DOMAIN:-staging.test}"
    local user pass
    if [ -f creds/staging_basic_auth.txt ]; then
        user="$(awk -F: '{print $1}' creds/staging_basic_auth.txt)"
        pass="$(awk -F: '{print $2}' creds/staging_basic_auth.txt)"
        echo "  Basic auth: $user / $pass"
        curl -sk -u "$user:$pass" --max-time 5 "https://${domain}:${port}/healthz" \
            && echo "  <- healthz OK" || echo "  healthz: нет ответа"
        echo -n "  /en/: "
        curl -sk -u "$user:$pass" --max-time 5 -o /dev/null -w '%{http_code}\n' \
            "https://${domain}:${port}/en/" || echo "000"
    else
        echo "  WARN: creds/staging_basic_auth.txt отсутствует"
    fi
    echo -n "  /robots.txt (без auth — должен быть 401): "
    curl -sk --max-time 5 -o /dev/null -w '%{http_code}\n' \
        "https://${domain}:${port}/robots.txt" || echo "000"

    echo
    echo "============================================================"
    echo "  Staging готов"
    echo "  URL:   https://${domain}:${port}/"
    echo "  Mail:  http://127.0.0.1:8026/"
    echo "============================================================"
}

cmd_down() {
    load_env
    "${COMPOSE[@]}" down
    echo "==> Staging остановлен (тома сохранены)"
}

cmd_reset() {
    require_env
    echo "==> Удаляем ВСЁ: контейнеры, тома staging, БД"
    read -r -p "Подтвердить? [y/N] " ans
    [ "$ans" = "y" ] || exit 0
    "${COMPOSE[@]}" down -v
    echo "==> Reset выполнен"
}

cmd_status() {
    require_env
    "${COMPOSE[@]}" ps
    echo
    echo "URL: https://${STAGING_DOMAIN:-staging.test}:${STAGING_PORT:-8444}/"
}

cmd_logs() {
    require_env
    "${COMPOSE[@]}" logs -f --tail=100 web nginx worker
}

cmd_url() {
    require_env
    echo "https://${STAGING_DOMAIN:-staging.test}:${STAGING_PORT:-8444}/"
}

cmd_creds() {
    if [ -f creds/staging_basic_auth.txt ]; then
        echo "Basic auth:"
        cat creds/staging_basic_auth.txt
    else
        echo "creds/staging_basic_auth.txt отсутствует" >&2
        exit 1
    fi
}

# ---- Диспетчер ------------------------------------------------------------
case "${1:-}" in
    up)      cmd_up ;;
    down)    cmd_down ;;
    reset)   cmd_reset ;;
    status)  cmd_status ;;
    logs)    cmd_logs ;;
    url)     cmd_url ;;
    creds)   cmd_creds ;;
    *)
        cat <<'USAGE'
Использование: ./infra/scripts/staging.sh <команда>

Команды:
  up       поднять staging, дождаться healthy, проверить
  down     остановить (тома сохраняются)
  reset    остановить + удалить тома staging (с подтверждением)
  status   статус контейнеров
  logs     логи web / nginx / worker
  url      URL staging
  creds    логин/пароль basic auth
USAGE
        exit 2
        ;;
esac
