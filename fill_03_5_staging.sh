#!/usr/bin/env bash
# fill_03_5_staging.sh — этап 3.5: staging-окружение (§2.5, §2.21).
# Идемпотентен.
set -euo pipefail
cd "$(dirname "$0")"

STAMP="$(date +%Y%m%d-%H%M%S)"
BK=".backups/$STAMP"
mkdir -p "$BK"

backup_file() {
    local rel="$1"
    [ -f "$rel" ] || return 0
    mkdir -p "$BK/$(dirname -- "$rel")"
    cp -p "$rel" "$BK/$rel"
}

write_file() {
    local rel="$1" tmp
    tmp="$(mktemp)"
    cat > "$tmp"
    if [ -e "$rel" ] && cmp -s "$tmp" "$rel"; then
        printf '  SKIP  %s\n' "$rel"; rm -f "$tmp"; return
    fi
    [ -f "$rel" ] && backup_file "$rel"
    mkdir -p "$(dirname -- "$rel")"
    mv -f "$tmp" "$rel"
    chmod 644 "$rel"
    printf '  OK    %s\n' "$rel"
}

echo "============================================================"
echo "  Этап 3.5 — staging"
echo "============================================================"

# ======================================================= compose.staging.yml
write_file compose.staging.yml <<'BA_EOF'
# compose.staging.yml — staging overlay (§2.5, §2.21).
#
# Запуск ТОЛЬКО через wrapper (он добавляет project-name и env-file):
#   ./infra/scripts/staging.sh up
#   ./infra/scripts/staging.sh down
#   ./infra/scripts/staging.sh status
#
# Прямой запуск требует:
#   docker compose -p ba-staging -f compose.yml -f compose.staging.yml \
#     --env-file .env.staging up -d
#
# Отличия от production-образа — только конфигурация:
#   - DJANGO_SETTINGS_MODULE=config.settings.staging
#   - BA_NOINDEX=True, X-Robots-Tag, robots.txt disallow-all
#   - Basic auth + IP allowlist в nginx
#   - mailpit для sandbox-почты
#   - отдельные секреты (.env.staging) и отдельный PostgreSQL volume

services:
  web:
    env_file: [.env.staging]
    environment:
      DJANGO_SETTINGS_MODULE: config.settings.staging
    # порт 8000 не публикуется (доступ только через nginx)

  worker:
    env_file: [.env.staging]
    environment:
      DJANGO_SETTINGS_MODULE: config.settings.staging
    depends_on:
      web: { condition: service_healthy }

  beat:
    env_file: [.env.staging]
    environment:
      DJANGO_SETTINGS_MODULE: config.settings.staging

  backup:
    env_file: [.env.staging]

  restore-check:
    env_file: [.env.staging]

  db:
    env_file: [.env.staging]
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-ba_staging}
      POSTGRES_USER: ${POSTGRES_USER:-ba}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?задайте POSTGRES_PASSWORD в .env.staging}

  nginx:
    env_file: [.env.staging]
    depends_on:
      web: { condition: service_healthy }
    ports:
      - "${STAGING_PORT:-8444}:8443"
    volumes:
      - ./infra/nginx/staging.conf:/etc/nginx/nginx.conf:ro
      - ./certs:/etc/nginx/certs:ro
      - ./certs/htpasswd:/etc/nginx/htpasswd:ro
      - static_data:/app/staticfiles:ro
      - media_data:/app/media:ro
    healthcheck:
      test: ["CMD", "nginx", "-t"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s

  mailpit:
    image: axllent/mailpit:latest
    restart: unless-stopped
    networks: [internal, edge]
    ports:
      - "127.0.0.1:8026:8025"
    environment:
      MP_MAX_MESSAGES: "5000"
    deploy:
      resources:
        limits: { cpus: "0.25", memory: 128M }
BA_EOF

# ================================================== infra/nginx/staging.conf.j2
write_file infra/nginx/staging.conf.j2 <<'BA_EOF'
# staging.conf.j2 — nginx staging template (§2.5, §2.20, §2.21).
# Рендерится в infra/nginx/staging.conf через envsubst
# (см. infra/scripts/staging.sh) — только ${VAR}-переменные из списка.
# Переменные nginx ($time_iso8601, $request_id и т.д.) остаются нетронутыми.

worker_processes auto;
pid /tmp/nginx.pid;
events { worker_connections 1024; }

http {
    include /etc/nginx/mime.types;
    types { text/javascript mjs; }
    default_type application/octet-stream;
    server_tokens off;
    sendfile on;
    tcp_nopush on;
    keepalive_timeout 65;
    client_max_body_size 30m;

    # Временные каталоги — в /tmp, т.к. контейнер работает non-root
    client_body_temp_path /tmp/client_temp;
    proxy_temp_path /tmp/proxy_temp;
    fastcgi_temp_path /tmp/fastcgi_temp;
    uwsgi_temp_path /tmp/uwsgi_temp;
    scgi_temp_path /tmp/scgi_temp;

    gzip on;
    gzip_min_length 1024;
    gzip_types text/css text/javascript application/javascript application/json image/svg+xml;

    log_format ba_json escape=json '{"time":"$time_iso8601","request_id":"$request_id",'
        '"host":"$host","method":"$request_method","uri":"$uri","status":$status,'
        '"bytes":$body_bytes_sent,"rt":$request_time,"upstream":"$upstream_addr"}';
    access_log /dev/stdout ba_json;
    error_log /dev/stderr warn;

    upstream django { server web:8000; keepalive 16; }

    server {
        listen 8443 ssl default_server;
        server_name ${STAGING_DOMAIN};

        ssl_certificate     ${SSL_CERT};
        ssl_certificate_key ${SSL_KEY};
        ssl_protocols TLSv1.2 TLSv1.3;

        # Basic auth — весь staging закрыт (§2.5)
        auth_basic "Breaktime Arcade Staging";
        auth_basic_user_file /etc/nginx/htpasswd;

        # IP allowlist (§2.5)
        allow ${STAGING_ALLOW_IP};
        deny all;

        # noindex (§2.5, §2.21) — X-Robots-Tag + robots.txt disallow-all
        add_header X-Robots-Tag "noindex, nofollow" always;
        add_header X-Staging "true" always;

        # Служебный robots.txt — disallow-all
        location = /robots.txt {
            default_type text/plain;
            return 200 "User-agent: *\nDisallow: /\n";
        }

        location /static/ {
            alias /app/staticfiles/;
            access_log off;
            expires 1h;
            add_header X-Content-Type-Options nosniff always;
            add_header X-Robots-Tag "noindex, nofollow" always;
        }

        location /media/ {
            alias /app/media/;
            access_log off;
            expires 1h;
            add_header X-Content-Type-Options nosniff always;
            add_header X-Robots-Tag "noindex, nofollow" always;
        }

        location / {
            proxy_pass http://django;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-Proto https;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Request-ID $request_id;
            proxy_set_header Connection "";
            proxy_redirect off;
        }
    }
}
BA_EOF

# ================================================== infra/scripts/staging.sh
write_file infra/scripts/staging.sh <<'BA_EOF'
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
BA_EOF
chmod 755 infra/scripts/staging.sh

# ============================================== infra/scripts/gen_staging_env.sh
write_file infra/scripts/gen_staging_env.sh <<'BA_EOF'
#!/usr/bin/env bash
# gen_staging_env.sh — генерирует .env.staging и creds/staging_basic_auth.txt
# с рандомными секретами (§2.5). Идемпотентен: если .env.staging уже есть — пропуск.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

ENV_FILE=".env.staging"
CREDS_FILE="creds/staging_basic_auth.txt"

if [ -f "$ENV_FILE" ]; then
    echo "==> $ENV_FILE уже существует — пропускаю"
    exit 0
fi

mkdir -p creds

# rand <len>
rand() {
    openssl rand -base64 64 | tr -d '\n=+/' | cut -c1-"$1"
}

# htpasswd: openssl passwd -apr1 (MD5-crypt, совместим с nginx)
BASIC_USER="${STAGING_USER:-staging}"
BASIC_PASS="$(rand 24)"
HTPASSWD_HASH="$(openssl passwd -apr1 "$BASIC_PASS")"
echo "${BASIC_USER}:${BASIC_PASS}" > "$CREDS_FILE"
chmod 600 "$CREDS_FILE"

cat > certs/htpasswd <<EOF
${BASIC_USER}:${HTPASSWD_HASH}
EOF
chmod 640 certs/htpasswd

POSTGRES_PASSWORD="$(rand 32)"
SECRET_KEY="$(rand 48)"
ANON_KEY="$(rand 48)"
NICK_KEY="$(rand 48)"
SESS_KEY="$(rand 48)"
BKP_PASS="$(rand 32)"

cat > "$ENV_FILE" <<EOF
# Staging — сгенерировано $(date '+%F %T %z') (§2.5).
# Файл содержит секреты, в Git не хранится.

# --- Django ---
DJANGO_SECRET_KEY=${SECRET_KEY}
DJANGO_SETTINGS_MODULE=config.settings.staging
DJANGO_ALLOWED_HOSTS=${STAGING_DOMAIN:-staging.test},localhost,127.0.0.1,web
DEBUG=False
BA_NOINDEX=True
ADMIN_URL_PREFIX=crm-$(openssl rand -hex 6)/
PORTAL_ORIGIN=https://${STAGING_DOMAIN:-staging.test}:${STAGING_PORT:-8444}
GAMES_DOMAIN=${STAGING_GAMES_DOMAIN:-games.staging.test}
BA_GAMES_FRAME_SRC=https://*.${STAGING_GAMES_DOMAIN:-games.staging.test}:${STAGING_PORT:-8444}

# --- Staging domain / port / basic-auth ---
STAGING_DOMAIN=${STAGING_DOMAIN:-staging.test}
STAGING_PORT=${STAGING_PORT:-8444}
STAGING_ALLOW_IP=${STAGING_ALLOW_IP:-127.0.0.1}
SSL_CERT=/etc/nginx/certs/${STAGING_DOMAIN:-staging.test}.pem
SSL_KEY=/etc/nginx/certs/${STAGING_DOMAIN:-staging.test}-key.pem

# --- Данные ---
POSTGRES_DB=ba_staging
POSTGRES_USER=ba
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
DATABASE_URL=postgres://ba:${POSTGRES_PASSWORD}@db:5432/ba_staging
DB_POOL_ENABLED=True
DB_POOL_MIN=2
DB_POOL_MAX=6
REDIS_CACHE_URL=redis://redis-cache:6379/1
REDIS_BROKER_URL=redis://redis-broker:6379/2
CELERY_BROKER_URL=redis://redis-broker:6379/2

# --- Почта (sandbox mailpit) ---
EMAIL_HOST=mailpit
EMAIL_PORT=1025
EMAIL_USER=
EMAIL_PASSWORD=
EMAIL_USE_TLS=False
DEFAULT_FROM_EMAIL=no-reply@staging.test

# --- Хранилище и CDN ---
S3_ENDPOINT=
S3_BUCKET=
S3_ACCESS_KEY=
S3_SECRET_KEY=
S3_REGION=
S3_PACKAGES_BUCKET=
S3_RUNTIME_BUCKET=
CDN_BASE_URL=

# --- Наблюдаемость ---
SENTRY_DSN=
SENTRY_ENV=staging
HIBP_ENABLED=False

# --- Секреты прикладного уровня ---
ANON_SIGNING_KEY=${ANON_KEY}
NICKNAME_HMAC_KEY=${NICK_KEY}
SESSION_BINDING_KEY=${SESS_KEY}
TOTP_ISSUER=BreaktimeArcade-Staging

# --- Бэкапы ---
BACKUP_DIR=/app/var/backups
BACKUP_RETENTION_DAYS=14
BA_BACKUP_CHECK_ENABLED=True
BA_BACKUP_STALE_HOURS=48
BACKUP_TARGET_URI=
BACKUP_PASSPHRASE=${BKP_PASS}

# --- Веб-сервер и пайплайн ---
GUNICORN_WORKERS=4
BA_SDK_DEFAULT_VERSION=1.1.0
ZIP_MAX_BYTES=26214400
CRITICAL_PATH_WARN_BYTES=2097152
CRITICAL_PATH_MAX_BYTES=4194304

# --- Сборка образов ---
IMAGE_TAG=staging
PYTHON_IMAGE=python:3.14-slim-bookworm
NODE_IMAGE=node:22-bookworm-slim
UV_VERSION=$(uv --version 2>/dev/null | awk '{print $2}' || echo "0.13.7")
EOF
chmod 600 "$ENV_FILE"

cat <<EOF
==> Сгенерировано:
    ${ENV_FILE}               (секреты, chmod 600)
    certs/htpasswd            (chmod 640)
    ${CREDS_FILE}   (chmod 600)

==> Basic auth: ${BASIC_USER} / ${BASIC_PASS}
   (сохранено в ${CREDS_FILE}; не выводить в CI)

Следующий шаг:
    ./infra/scripts/staging.sh up
EOF
BA_EOF
chmod 755 infra/scripts/gen_staging_env.sh

# ==================================================== .env.staging.example
write_file .env.staging.example <<'BA_EOF'
# .env.staging.example — шаблон staging-окружения (§2.5).
# НЕ содержит реальных значений; копия генерируется через:
#   ./infra/scripts/gen_staging_env.sh
# Для реального staging-сервера замените:
#   STAGING_DOMAIN=staging.example.com
#   STAGING_PORT=443
#   SSL_CERT=/etc/nginx/certs/fullchain.pem
#   SSL_KEY=/etc/nginx/certs/privkey.pem
#   STAGING_ALLOW_IP=<office-ip>
# и используйте сертификат от Let's Encrypt (DNS-01).

DJANGO_SETTINGS_MODULE=config.settings.staging
DEBUG=False
BA_NOINDEX=True
STAGING_DOMAIN=staging.test
STAGING_PORT=8444
STAGING_ALLOW_IP=127.0.0.1
SSL_CERT=/etc/nginx/certs/staging.test.pem
SSL_KEY=/etc/nginx/certs/staging.test-key.pem

POSTGRES_DB=ba_staging
POSTGRES_USER=ba
POSTGRES_PASSWORD=<generate>

EMAIL_HOST=mailpit
EMAIL_PORT=1025
SENTRY_ENV=staging
BA_BACKUP_CHECK_ENABLED=True
BA_BACKUP_STALE_HOURS=48
BACKUP_DIR=/app/var/backups
BACKUP_RETENTION_DAYS=14
BA_EOF

# ==================================================== .gitignore
echo
echo "==> .gitignore"
if grep -q '^.env.staging$' .gitignore 2>/dev/null; then
    echo "  SKIP  уже содержит .env.staging"
else
    backup_file .gitignore
    cat >> .gitignore <<'EOF'

# Staging secrets (§2.5)
.env.staging
creds/staging_basic_auth.txt
certs/htpasswd
infra/nginx/staging.conf
EOF
    echo "  OK    добавлены .env.staging, creds/, certs/htpasswd, staging.conf"
fi

# ==================================================== Makefile
echo
echo "==> Makefile"
if grep -q '^staging-up:' Makefile 2>/dev/null; then
    echo "  SKIP  таргеты уже есть"
else
    backup_file Makefile
    python3 - <<'PY'
import pathlib
p = pathlib.Path("Makefile")
text = p.read_text(encoding="utf-8")
anchor = "\ndump:\n"
insert = (
    "staging-up:\n"
    "> @./infra/scripts/staging.sh up\n"
    "\n"
    "staging-down:\n"
    "> @./infra/scripts/staging.sh down\n"
    "\n"
    "staging-reset:\n"
    "> @./infra/scripts/staging.sh reset\n"
    "\n"
    "staging-status:\n"
    "> @./infra/scripts/staging.sh status\n"
    "\n"
    "staging-logs:\n"
    "> @./infra/scripts/staging.sh logs\n"
    "\n"
)
if anchor in text and "staging-up:\n" not in text:
    text = text.replace(anchor, "\n" + insert + "dump:\n", 1)
    text = text.replace(
        "help env certs", "help env certs staging-up staging-down staging-reset staging-status staging-logs", 1)
    p.write_text(text, encoding="utf-8")
    print("  OK    Makefile патчен")
PY
fi

# ==================================================== Итог
echo
echo "============================================================"
echo "  Установка 3.5 завершена"
echo "  Бэкап: $BK"
echo "============================================================"
cat <<'BA_EOF'

Следующие шаги:

  1. Сгенерировать .env.staging и creds/staging_basic_auth.txt:
       ./infra/scripts/gen_staging_env.sh

  2. Добавить staging.test в /etc/hosts (один раз):
       echo '127.0.0.1 staging.test' | sudo tee -a /etc/hosts

  3. Поднять staging:
       ./infra/scripts/staging.sh up

  4. Проверить:
       - URL и credentials печатает ./infra/scripts/staging.sh url
       - ./infra/scripts/staging.sh creds
       - Открыть URL в браузере (ввести логин/пароль)
       - http://127.0.0.1:8026/ — почтовый sandbox

  5. Проверить, что dev-lite не сломан:
       ./verify_stack.sh
BA_EOF
