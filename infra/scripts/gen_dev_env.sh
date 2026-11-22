#!/usr/bin/env bash
# Генерация локального .env из .env.example: dev-значения и случайные секреты.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
[[ -f .env ]] && { printf '.env уже существует — пропускаю\n'; exit 0; }

rand() { openssl rand -base64 48 | tr -d '\n=+/' | cut -c1-48; }
PGPASS="$(rand)"
UVV="$(uv --version 2>/dev/null | awk '{print $2}')"
[[ -n "$UVV" ]] || { printf 'uv не найден: установите uv и повторите\n' >&2; exit 1; }

cat > .env <<ENV
DJANGO_SECRET_KEY=$(rand)
DJANGO_SETTINGS_MODULE=config.settings.dev
DJANGO_ALLOWED_HOSTS=portal.test,localhost,127.0.0.1,web
DEBUG=True
ADMIN_URL_PREFIX=crm-$(openssl rand -hex 6)/
PORTAL_ORIGIN=https://portal.test:8443
GAMES_DOMAIN=games.test
BA_GAMES_FRAME_SRC=https://*.games.test:8443

POSTGRES_DB=ba
POSTGRES_USER=ba
POSTGRES_PASSWORD=${PGPASS}
DATABASE_URL=postgres://ba:${PGPASS}@db:5432/ba
DB_POOL_ENABLED=True
DB_POOL_MIN=2
DB_POOL_MAX=8
REDIS_CACHE_URL=redis://redis-cache:6379/1
REDIS_BROKER_URL=redis://redis-broker:6379/2
CELERY_BROKER_URL=redis://redis-broker:6379/2

EMAIL_HOST=mailpit
EMAIL_PORT=1025
EMAIL_USER=
EMAIL_PASSWORD=
EMAIL_USE_TLS=False
DEFAULT_FROM_EMAIL=no-reply@portal.test

S3_ENDPOINT=
S3_BUCKET=
S3_ACCESS_KEY=
S3_SECRET_KEY=
S3_REGION=
S3_PACKAGES_BUCKET=
S3_RUNTIME_BUCKET=
CDN_BASE_URL=

SENTRY_DSN=
SENTRY_ENV=dev
HIBP_ENABLED=False

ANON_SIGNING_KEY=$(rand)
NICKNAME_HMAC_KEY=$(rand)
SESSION_BINDING_KEY=$(rand)
TOTP_ISSUER=BreaktimeArcade-Dev

BACKUP_TARGET_URI=
BACKUP_PASSPHRASE=$(rand)

GUNICORN_WORKERS=4
BA_SDK_DEFAULT_VERSION=1.1.0
ZIP_MAX_BYTES=26214400
CRITICAL_PATH_WARN_BYTES=2097152
CRITICAL_PATH_MAX_BYTES=4194304
ZIP_QUOTA_STATE_ROOT=/var/ba/zip/quota
ZIP_STORAGE_QUOTA_BYTES=2147483648
ZIP_STORAGE_MIN_FREE_BYTES=157286400
ZIP_QUOTA_RESERVATION_TTL_SECONDS=3600
ZIP_STAGING_TTL_SECONDS=3600
ZIP_COMPLETED_TTL_SECONDS=86400

IMAGE_TAG=dev
PYTHON_IMAGE=python:3.14-slim-bookworm
NODE_IMAGE=node:22-bookworm-slim
UV_VERSION=${UVV}
ENV
chmod 600 .env
printf '.env создан (секреты сгенерированы, uv %s)\n' "$UVV"
