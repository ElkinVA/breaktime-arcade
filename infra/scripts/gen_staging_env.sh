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
