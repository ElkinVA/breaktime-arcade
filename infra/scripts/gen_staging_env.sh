#!/usr/bin/env bash
# gen_staging_env.sh — генерирует .env.staging и creds/staging_basic_auth.txt
# с рандомными секретами (§2.5). Идемпотентен: если .env.staging уже есть — пропуск.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

ENV_FILE=".env.staging"
CREDS_FILE="creds/staging_basic_auth.txt"

LOCK_DIR="$PWD/creds/.locks"
LOCK_FILE="$LOCK_DIR/staging.lock"

acquire_staging_lock() {
    command -v flock >/dev/null 2>&1 || {
        echo "FAIL: flock не найден" >&2
        return 1
    }
    mkdir -p "$LOCK_DIR" || return 1
    chmod 700 "$LOCK_DIR" || return 1

    # Re-entrant path: fd 9 must point to this exact lock file, and flock
    # must succeed on the inherited open file description. Never trust an
    # environment variable or an arbitrary fd as proof of lock ownership.
    if [ -e "/proc/$$/fd/9" ] && [ "/proc/$$/fd/9" -ef "$LOCK_FILE" ]; then
        if flock -n 9; then
            return 0
        fi
        echo "ERROR: другая staging-операция уже выполняется" >&2
        return 75
    fi

    if ! { exec 9>"$LOCK_FILE"; }; then
        echo "FAIL: не удалось открыть $LOCK_FILE" >&2
        return 1
    fi
    if ! flock -n 9; then
        echo "ERROR: другая staging-операция уже выполняется" >&2
        return 75
    fi
    return 0
}

if ! acquire_staging_lock; then
    exit 75
fi

if [ -f "$ENV_FILE" ]; then
    echo "==> $ENV_FILE уже существует — пропускаю"
    exit 0
fi

mkdir -p creds

# rand <len>
rand() {
    openssl rand -base64 64 | tr -d '\n=+/' | cut -c1-"$1"
}

# htpasswd: bcrypt через htpasswd -B; пароль передаётся только через stdin.
BASIC_USER="${STAGING_USER:-staging}"
command -v htpasswd >/dev/null 2>&1 || {
    echo "FAIL: htpasswd не найден (нужен пакет apache2-utils)" >&2
    exit 1
}

PASS_FILE="$(mktemp)"
trap 'rm -f "$PASS_FILE"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
chmod 600 "$PASS_FILE"
rand 40 > "$PASS_FILE"

{
    printf '%s:' "$BASIC_USER"
    cat "$PASS_FILE"
} > "$CREDS_FILE"
chmod 600 "$CREDS_FILE"

htpasswd -B -C 10 -i -c certs/htpasswd "$BASIC_USER" < "$PASS_FILE"
chmod 640 certs/htpasswd

if ! htpasswd -v -i certs/htpasswd "$BASIC_USER" < "$PASS_FILE" >/dev/null 2>&1; then
    echo "FAIL: сохранённый htpasswd не соответствует сгенерированному паролю" >&2
    exit 1
fi

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

==> Basic auth username: ${BASIC_USER}
    Пароль сохранён в ${CREDS_FILE} (chmod 600); не выводить.

Следующий шаг:
    ./infra/scripts/staging.sh up
EOF
