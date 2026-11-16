#!/usr/bin/env bash
# =============================================================================
#  fill_01_core.sh — этап 1, блок 1: инфраструктура и ядро Django (BA-PLAT-4.2)
#  Запуск: bash fill_01_core.sh [КАТАЛОГ] [--force] [--dry-run]
# =============================================================================
set -euo pipefail

TARGET="$PWD"; FORCE=0; DRY=0
for arg in "$@"; do
  case "$arg" in
    --force)   FORCE=1 ;;
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    -*) printf 'Неизвестный ключ: %s\n' "$arg" >&2; exit 2 ;;
    *) TARGET="$arg" ;;
  esac
done
cd "$TARGET"
if [[ ! -d apps || ! -d config ]]; then
  printf 'Каталог %s не содержит каркаса. Сначала выполните bootstrap_structure.sh\n' "$TARGET" >&2
  exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR=".backups/$STAMP"
filled=0; skipped=0; backed=0

write_file() {
  local rel="$1" tmp
  tmp="$(mktemp)"
  cat > "$tmp"
  if [[ -e "$rel" && -s "$rel" && $FORCE -eq 0 ]]; then
    printf '  SKIP  %s (не пустой)\n' "$rel"; skipped=$((skipped+1)); rm -f "$tmp"; return
  fi
  if (( DRY )); then
    printf '  FILL  %s\n' "$rel"; filled=$((filled+1)); rm -f "$tmp"; return
  fi
  mkdir -p -- "$(dirname -- "$rel")"
  if [[ -e "$rel" && -s "$rel" ]]; then
    mkdir -p -- "$BACKUP_DIR/$(dirname -- "$rel")"
    cp -p -- "$rel" "$BACKUP_DIR/$rel"; backed=$((backed+1))
  fi
  mv -f -- "$tmp" "$rel"
  case "$rel" in *.sh) chmod 755 "$rel" ;; *) chmod 644 "$rel" ;; esac
  printf '  OK    %s\n' "$rel"; filled=$((filled+1))
}

# =============================================================================
write_file pyproject.toml <<'BA_EOF'
[project]
name = "breaktime-arcade"
version = "0.1.0"
description = "Breaktime Arcade — портал коротких браузерных мини-игр (BA-PLAT-4.2)"
requires-python = ">=3.14,<3.15"
dependencies = [
    "django>=5.2.19,<5.3",
    "psycopg[binary,pool]==3.3.8",
    "celery==5.7.0",
    "redis>=5.2",
    "django-redis>=5.4",
    "djangorestframework>=3.16",
    "argon2-cffi>=23.1",
    "gunicorn>=23.0",
    "sentry-sdk>=2.19",
    "babel>=2.16",
    "jsonschema>=4.23",
    "pillow>=11.0",
    "pyotp>=2.9",
    "confusable-homoglyphs>=3.3",
    "boto3>=1.35",
    "django-storages[s3]>=1.14",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-django>=4.9",
    "pytest-cov>=6.0",
    "model-bakery>=1.20",
    "ruff>=0.9",
    "mypy>=1.16",
    "django-stubs[compatible-mypy]>=5.2",
    "pre-commit>=4.0",
    "playwright>=1.49",
]

# Точные версии прямых и транзитивных зависимостей фиксируются uv.lock (этап 0).
[tool.uv]
package = false
BA_EOF

write_file package.json <<'BA_EOF'
{
  "name": "breaktime-arcade-assets",
  "private": true,
  "engines": { "node": ">=22 <23" },
  "scripts": {
    "vendor": "mkdir -p static/dist/vendor && cp node_modules/htmx.org/dist/htmx.min.js static/dist/vendor/htmx.min.js",
    "build:css": "tailwindcss -i ./static/src/css/app.css -o ./static/dist/app.css --minify",
    "watch:css": "tailwindcss -i ./static/src/css/app.css -o ./static/dist/app.css --watch",
    "build": "npm run vendor && npm run build:css"
  },
  "devDependencies": {
    "@tailwindcss/cli": "^4.0.0",
    "tailwindcss": "^4.0.0",
    "htmx.org": "^2.0.4"
  }
}
BA_EOF

write_file ruff.toml <<'BA_EOF'
target-version = "py314"
line-length = 100
src = ["apps", "config"]
extend-exclude = ["**/migrations/**", "static", "node_modules", ".venv", "games-src"]

[lint]
select = ["E", "F", "W", "I", "UP", "B", "C4", "DJ", "S", "RET", "SIM", "PTH", "T20"]
ignore = ["S101"]

[lint.per-file-ignores]
"**/tests/**" = ["S105", "S106", "S108"]
"config/settings/*" = ["F403", "F405"]
"tests/**" = ["S105", "S106"]

[lint.isort]
known-first-party = ["apps", "config"]

[format]
quote-style = "double"
BA_EOF

write_file mypy.ini <<'BA_EOF'
[mypy]
python_version = 3.14
plugins = mypy_django_plugin.main
files = apps, config
exclude = (?x)(^.*/migrations/|^games-src/|^static/)
check_untyped_defs = True
disallow_any_generics = True
warn_redundant_casts = True
warn_unused_ignores = True
warn_return_any = True
no_implicit_optional = True
strict_equality = True

[mypy.plugins.django-stubs]
django_settings_module = config.settings.dev

[mypy-*.migrations.*]
ignore_errors = True

[mypy-celery.*]
ignore_missing_imports = True

[mypy-confusable_homoglyphs.*]
ignore_missing_imports = True
BA_EOF

write_file pytest.ini <<'BA_EOF'
[pytest]
DJANGO_SETTINGS_MODULE = config.settings.dev
python_files = test_*.py
testpaths = apps tests
addopts = -q --strict-markers --reuse-db
markers =
    e2e: браузерные сценарии Playwright
    load: нагрузочные сценарии S1-S4
# Порог покрытия доменных модулей >=70% включается в CI с этапа 2 (BA-PLAT-4.2 §2.26).
BA_EOF

write_file .pre-commit-config.yaml <<'BA_EOF'
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: check-yaml
      - id: check-json
      - id: check-merge-conflict
      - id: check-added-large-files
        args: ["--maxkb=1024"]
      - id: detect-private-key
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.0
    hooks:
      - id: ruff
        args: ["--fix"]
      - id: ruff-format
BA_EOF

write_file Dockerfile <<'BA_EOF'
# syntax=docker/dockerfile:1.7
# Значения PYTHON_IMAGE/NODE_IMAGE фиксируются по digest на этапе 0 (§2.3).
ARG PYTHON_IMAGE=python:3.14-slim-bookworm
ARG NODE_IMAGE=node:22-bookworm-slim

FROM ${NODE_IMAGE} AS assets
WORKDIR /build
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY static/src ./static/src
COPY templates ./templates
COPY apps ./apps
RUN npm run build

FROM ${PYTHON_IMAGE} AS builder
ARG UV_VERSION
ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never
RUN test -n "${UV_VERSION}" && pip install --no-cache-dir "uv==${UV_VERSION}"
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings.prod
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd -g 10001 app \
 && useradd -u 10001 -g 10001 -M -s /usr/sbin/nologin app \
 && mkdir -p /app/staticfiles /app/media /app/var \
 && chown -R app:app /app
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app . /app
COPY --from=assets --chown=app:app /build/static/dist /app/static/dist
RUN DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput
USER app
EXPOSE 8000
ENTRYPOINT ["/app/infra/scripts/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", \
     "--workers", "4", "--threads", "2", "--timeout", "60", \
     "--access-logfile", "-", "--error-logfile", "-"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1
BA_EOF

write_file compose.yml <<'BA_EOF'
name: breaktime-arcade

x-app: &app
  image: ba/app:${IMAGE_TAG:-dev}
  build:
    context: .
    args:
      PYTHON_IMAGE: ${PYTHON_IMAGE:-python:3.14-slim-bookworm}
      NODE_IMAGE: ${NODE_IMAGE:-node:22-bookworm-slim}
      UV_VERSION: ${UV_VERSION:?задайте UV_VERSION в .env (make env)}
  restart: unless-stopped
  env_file: [.env]
  user: "10001:10001"
  security_opt: ["no-new-privileges:true"]
  cap_drop: ["ALL"]
  volumes:
    - static_data:/app/staticfiles
    - media_data:/app/media
    - app_var:/app/var
  networks: [internal, edge]
  depends_on:
    db: { condition: service_healthy }
    redis-cache: { condition: service_healthy }
    redis-broker: { condition: service_healthy }
  logging:
    driver: json-file
    options: { max-size: "10m", max-file: "3" }

services:
  web:
    <<: *app
    environment:
      RUN_MIGRATIONS: "1"
      RUN_COLLECTSTATIC: "1"
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://127.0.0.1:8000/healthz"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 40s
    deploy:
      resources:
        limits: { cpus: "1.5", memory: 1536M }

  worker:
    <<: *app
    command: ["celery", "-A", "config", "worker", "-l", "info"]
    environment:
      RUN_MIGRATIONS: "0"
    depends_on:
      db: { condition: service_healthy }
      redis-cache: { condition: service_healthy }
      redis-broker: { condition: service_healthy }
      web: { condition: service_healthy }
    healthcheck:
      test: ["CMD-SHELL", "celery -A config inspect ping -d celery@$$HOSTNAME -t 10 | grep -q pong"]
      interval: 30s
      timeout: 15s
      retries: 3
      start_period: 30s
    deploy:
      resources:
        limits: { cpus: "1.0", memory: 1024M }

  beat:
    <<: *app
    command: ["celery", "-A", "config", "beat", "-l", "info", "--schedule", "/app/var/celerybeat-schedule"]
    profiles: ["beat"]
    depends_on:
      redis-broker: { condition: service_healthy }
      web: { condition: service_healthy }
    healthcheck:
      test: ["CMD", "python", "-c", "import os,time,sys; p='/app/var/celerybeat-schedule'; sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p)<300 else 1)"]
      interval: 60s
      timeout: 10s
      retries: 3
      start_period: 60s
    deploy:
      resources:
        limits: { cpus: "0.25", memory: 256M }

  db:
    image: postgres:18
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_INITDB_ARGS: "--data-checksums"
    volumes:
      - pgdata:/var/lib/postgresql
    shm_size: 256mb
    networks: [internal]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s
    deploy:
      resources:
        limits: { cpus: "1.5", memory: 2048M }

  redis-cache:
    image: redis:8-alpine
    restart: unless-stopped
    command: ["redis-server", "--maxmemory", "256mb", "--maxmemory-policy", "allkeys-lru", "--save", "", "--appendonly", "no"]
    volumes:
      - redis_cache_data:/data
    networks: [internal]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    deploy:
      resources:
        limits: { cpus: "0.5", memory: 320M }

  redis-broker:
    image: redis:8-alpine
    restart: unless-stopped
    command: ["redis-server", "--maxmemory", "512mb", "--maxmemory-policy", "noeviction", "--appendonly", "yes", "--appendfsync", "everysec"]
    volumes:
      - redis_broker_data:/data
    networks: [internal]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    deploy:
      resources:
        limits: { cpus: "0.5", memory: 640M }

  nginx:
    image: nginxinc/nginx-unprivileged:1.29-alpine
    restart: unless-stopped
    networks: [edge, internal]
    depends_on:
      web: { condition: service_healthy }
    volumes:
      - static_data:/app/staticfiles:ro
      - media_data:/app/media:ro
    healthcheck:
      test: ["CMD", "nginx", "-t"]
      interval: 30s
      timeout: 5s
      retries: 3
    deploy:
      resources:
        limits: { cpus: "0.5", memory: 192M }

networks:
  internal:
    internal: true
  edge:

volumes:
  pgdata:
  redis_cache_data:
  redis_broker_data:
  static_data:
  media_data:
  app_var:
BA_EOF

write_file compose.dev-lite.yml <<'BA_EOF'
# Профиль разработки dev-lite: пик ≈2.4 ГБ, лимит 3.8 GiB (§2.5).
services:
  web:
    command: ["python", "manage.py", "runserver", "0.0.0.0:8000"]
    environment:
      DJANGO_SETTINGS_MODULE: config.settings.dev
      RUN_MIGRATIONS: "1"
      RUN_COLLECTSTATIC: "1"
    volumes:
      - .:/app
      - static_data:/app/staticfiles
      - media_data:/app/media
      - app_var:/app/var
    ports:
      - "127.0.0.1:8000:8000"
    deploy:
      resources:
        limits: { cpus: "1.0", memory: 1024M }

  worker:
    command: ["celery", "-A", "config", "worker", "-l", "info", "--pool=solo", "--concurrency=1"]
    environment:
      DJANGO_SETTINGS_MODULE: config.settings.dev
    volumes:
      - .:/app
      - media_data:/app/media
      - app_var:/app/var
    deploy:
      resources:
        limits: { cpus: "0.5", memory: 512M }

  beat:
    profiles: ["manual"]
    environment:
      DJANGO_SETTINGS_MODULE: config.settings.dev
    volumes:
      - .:/app
      - app_var:/app/var
    deploy:
      resources:
        limits: { cpus: "0.25", memory: 192M }

  db:
    command: ["postgres", "-c", "shared_buffers=256MB", "-c", "max_connections=30", "-c", "work_mem=4MB"]
    deploy:
      resources:
        limits: { cpus: "1.0", memory: 768M }

  redis-cache:
    command: ["redis-server", "--maxmemory", "64mb", "--maxmemory-policy", "allkeys-lru", "--save", "", "--appendonly", "no"]
    deploy:
      resources:
        limits: { cpus: "0.25", memory: 128M }

  redis-broker:
    command: ["redis-server", "--maxmemory", "64mb", "--maxmemory-policy", "noeviction", "--appendonly", "yes"]
    deploy:
      resources:
        limits: { cpus: "0.25", memory: 128M }

  nginx:
    ports:
      - "8443:8443"
    volumes:
      - ./infra/nginx/dev.conf:/etc/nginx/nginx.conf:ro
      - ./certs:/etc/nginx/certs:ro
      - ./var/runtime:/app/runtime:ro
      - static_data:/app/staticfiles:ro
      - media_data:/app/media:ro
    deploy:
      resources:
        limits: { cpus: "0.25", memory: 128M }

  # Только dev: почтовый sandbox. В staging/production не используется.
  mailpit:
    image: axllent/mailpit:latest
    restart: unless-stopped
    networks: [internal, edge]
    ports:
      - "127.0.0.1:8025:8025"
    environment:
      MP_MAX_MESSAGES: "5000"
    deploy:
      resources:
        limits: { cpus: "0.25", memory: 128M }
BA_EOF

write_file .env.example <<'BA_EOF'
# BA-PLAT-4.2, Приложение A. Значения не хранятся в Git.
# Локальное окружение создаётся командой: make env

# --- Django ---
DJANGO_SECRET_KEY=
DJANGO_SETTINGS_MODULE=
DJANGO_ALLOWED_HOSTS=
DEBUG=
ADMIN_URL_PREFIX=
PORTAL_ORIGIN=
GAMES_DOMAIN=
BA_GAMES_FRAME_SRC=

# --- Данные ---
POSTGRES_DB=
POSTGRES_USER=
POSTGRES_PASSWORD=
DATABASE_URL=
DB_POOL_ENABLED=
DB_POOL_MIN=
DB_POOL_MAX=
REDIS_CACHE_URL=
REDIS_BROKER_URL=
CELERY_BROKER_URL=

# --- Почта ---
EMAIL_HOST=
EMAIL_PORT=
EMAIL_USER=
EMAIL_PASSWORD=
EMAIL_USE_TLS=
DEFAULT_FROM_EMAIL=

# --- Хранилище и CDN ---
S3_ENDPOINT=
S3_BUCKET=
S3_ACCESS_KEY=
S3_SECRET_KEY=
S3_REGION=
S3_PACKAGES_BUCKET=
S3_RUNTIME_BUCKET=
CDN_BASE_URL=

# --- Наблюдаемость и внешние сервисы ---
SENTRY_DSN=
SENTRY_ENV=
HIBP_ENABLED=

# --- Секреты прикладного уровня ---
ANON_SIGNING_KEY=
NICKNAME_HMAC_KEY=
SESSION_BINDING_KEY=
TOTP_ISSUER=

# --- Бэкапы ---
BACKUP_TARGET_URI=
BACKUP_PASSPHRASE=

# --- Веб-сервер и пайплайн ---
GUNICORN_WORKERS=
BA_SDK_DEFAULT_VERSION=
ZIP_MAX_BYTES=
CRITICAL_PATH_WARN_BYTES=
CRITICAL_PATH_MAX_BYTES=

# --- Сборка образов (фиксируется на этапе 0) ---
IMAGE_TAG=
PYTHON_IMAGE=
NODE_IMAGE=
UV_VERSION=
BA_EOF

write_file infra/scripts/gen_dev_env.sh <<'BA_EOF'
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

IMAGE_TAG=dev
PYTHON_IMAGE=python:3.14-slim-bookworm
NODE_IMAGE=node:22-bookworm-slim
UV_VERSION=${UVV}
ENV
chmod 600 .env
printf '.env создан (секреты сгенерированы, uv %s)\n' "$UVV"
BA_EOF

write_file infra/scripts/mkcert.sh <<'BA_EOF'
#!/usr/bin/env bash
# Локальные TLS-сертификаты для portal.test и *.games.test (§2.4).
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
command -v mkcert >/dev/null || {
  printf 'mkcert не установлен. Ubuntu/WSL: sudo apt install libnss3-tools; ' >&2
  printf 'затем установите mkcert и выполните mkcert -install\n' >&2
  exit 1
}
mkdir -p certs
mkcert -install
mkcert -cert-file certs/portal.test.pem -key-file certs/portal.test-key.pem portal.test
mkcert -cert-file certs/games.test.pem -key-file certs/games.test-key.pem '*.games.test' games.test
chmod 644 certs/*.pem
printf 'Сертификаты готовы: certs/\n'
BA_EOF

write_file infra/scripts/entrypoint.sh <<'BA_EOF'
#!/usr/bin/env bash
set -euo pipefail
cd /app

wait_for() {
  local host="$1" port="$2" i
  for i in $(seq 1 60); do
    if python -c "import socket,sys; s=socket.socket(); s.settimeout(2); sys.exit(0 if s.connect_ex(('$host',$port))==0 else 1)"; then
      printf 'готов: %s:%s\n' "$host" "$port"
      return 0
    fi
    sleep 2
  done
  printf 'не дождались %s:%s\n' "$host" "$port" >&2
  return 1
}

wait_for db 5432
wait_for redis-cache 6379
wait_for redis-broker 6379

if [[ "${RUN_MIGRATIONS:-0}" == "1" ]]; then
  python manage.py migrate --noinput
fi
if [[ "${RUN_COLLECTSTATIC:-0}" == "1" ]]; then
  python manage.py collectstatic --noinput
fi

exec "$@"
BA_EOF

write_file infra/nginx/dev.conf <<'BA_EOF'
# Development: TLS mkcert, порт 8443 (§2.4, §2.20). HSTS выключен.
worker_processes auto;
pid /tmp/nginx.pid;
events { worker_connections 1024; }

http {
    include /etc/nginx/mime.types;
    types { text/javascript mjs; application/wasm wasm; }
    default_type application/octet-stream;
    server_tokens off;
    sendfile on;
    tcp_nopush on;
    keepalive_timeout 65;
    client_max_body_size 30m;

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

    map $uri $game_cache {
        default                     "public, max-age=31536000, immutable";
        "~*/index\.html$"           "no-cache";
    }

    upstream django { server web:8000; keepalive 16; }

    server {
        listen 8443 ssl default_server;
        ssl_certificate     /etc/nginx/certs/games.test.pem;
        ssl_certificate_key /etc/nginx/certs/games.test-key.pem;
        return 444;
    }

    server {
        listen 8443 ssl;
        http2 on;
        server_name portal.test;
        ssl_certificate     /etc/nginx/certs/portal.test.pem;
        ssl_certificate_key /etc/nginx/certs/portal.test-key.pem;
        ssl_protocols TLSv1.2 TLSv1.3;

        location /static/ {
            alias /app/staticfiles/;
            access_log off;
            expires 1h;
            add_header X-Content-Type-Options nosniff always;
        }
        location /media/ {
            alias /app/media/;
            access_log off;
            expires 1h;
            add_header X-Content-Type-Options nosniff always;
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

    # Игровой хост: только статика. X-Frame-Options отсутствует намеренно (§2.4.2).
    server {
        listen 8443 ssl;
        http2 on;
        server_name ~^(?<game_label>[a-z0-9-]+)\.games\.test$;
        ssl_certificate     /etc/nginx/certs/games.test.pem;
        ssl_certificate_key /etc/nginx/certs/games.test-key.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        root /app/runtime;

        add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:; frame-ancestors https://portal.test:8443; form-action 'none'; object-src 'none'; base-uri 'self'" always;
        add_header X-Content-Type-Options nosniff always;
        add_header Referrer-Policy no-referrer always;
        add_header X-Robots-Tag "noindex, nofollow" always;
        add_header Cross-Origin-Resource-Policy cross-origin always;
        add_header Permissions-Policy "fullscreen=(self), gamepad=(self), autoplay=(self)" always;

        location ~ ^/v/(?<vhash>[0-9a-f]{12,16})/(?<vpath>.+)$ {
            add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:; frame-ancestors https://portal.test:8443; form-action 'none'; object-src 'none'; base-uri 'self'" always;
            add_header X-Content-Type-Options nosniff always;
            add_header Referrer-Policy no-referrer always;
            add_header X-Robots-Tag "noindex, nofollow" always;
            add_header Cross-Origin-Resource-Policy cross-origin always;
            add_header Permissions-Policy "fullscreen=(self), gamepad=(self), autoplay=(self)" always;
            add_header Cache-Control $game_cache always;
            try_files /$game_label/$vhash/$vpath =404;
        }
        location / { return 404; }
    }
}
BA_EOF

write_file Makefile <<'BA_EOF'
# GNU make >= 4.0. Префикс рецептов '>' вместо табуляции.
.RECIPEPREFIX := >
.DEFAULT_GOAL := help
SHELL := /bin/bash

COMPOSE := docker compose -f compose.yml -f compose.dev-lite.yml
AS_USER := --user $(shell id -u):$(shell id -g)
PY      := $(COMPOSE) exec -T web python
PYU     := $(COMPOSE) exec -T $(AS_USER) web python

.PHONY: help env certs assets lock build up down restart ps logs migrate makemigrations \
        superuser shell psql test lint fmt types check dump clean

help:
> @grep -E '^[a-z-]+:' Makefile | sed 's/:.*//' | sort

env:
> @bash infra/scripts/gen_dev_env.sh

certs:
> @bash infra/scripts/mkcert.sh

assets:
> npm install --no-audit --no-fund
> npm run build

lock:
> uv lock

build:
> $(COMPOSE) build

up:
> $(COMPOSE) --profile beat up -d
> @echo "https://portal.test:8443/healthz"

down:
> $(COMPOSE) down

restart:
> $(COMPOSE) restart web worker

ps:
> $(COMPOSE) ps

logs:
> $(COMPOSE) logs -f --tail=100 web worker nginx

makemigrations:
> $(PYU) manage.py makemigrations

migrate:
> $(PY) manage.py migrate --noinput

superuser:
> $(COMPOSE) exec web python manage.py createsuperuser

shell:
> $(COMPOSE) exec web python manage.py shell

psql:
> $(COMPOSE) exec db psql -U ba -d ba

test:
> $(PYU) -m pytest

lint:
> $(PYU) -m ruff check apps config tests
> $(PYU) -m ruff format --check apps config tests

fmt:
> $(PYU) -m ruff check --fix apps config tests
> $(PYU) -m ruff format apps config tests

types:
> $(PYU) -m mypy

check: lint types test

dump:
> @bash scripts/collect_project.sh

clean:
> $(COMPOSE) down --remove-orphans
> rm -rf static/dist .pytest_cache .ruff_cache .mypy_cache
BA_EOF

write_file manage.py <<'BA_EOF'
#!/usr/bin/env python
"""Точка входа управления Django."""
import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
BA_EOF

write_file config/__init__.py <<'BA_EOF'
from .celery import app as celery_app

__all__ = ("celery_app",)
BA_EOF

write_file config/celery.py <<'BA_EOF'
from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("breaktime")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
BA_EOF

write_file config/wsgi.py <<'BA_EOF'
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = get_wsgi_application()
BA_EOF

write_file config/asgi.py <<'BA_EOF'
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = get_asgi_application()
BA_EOF

write_file config/settings/base.py <<'BA_EOF'
"""Базовые настройки. Норматив: BA-PLAT-4.2, Приложение B."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

BASE_DIR = Path(__file__).resolve().parents[2]


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    return env(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(env(name, str(default)))
    except ValueError:
        return default


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env_bool("DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "rest_framework",
    "apps.core",
    "apps.accounts",
    "apps.catalog",
    "apps.gameplay",
    "apps.leaderboards",
    "apps.ratings",
    "apps.pipeline",
    "apps.i18n",
    "apps.crm",
    "apps.moderation",
    "apps.analytics",
    "apps.content",
    "apps.theme",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.core.middleware.RequestIDMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
    "apps.core.middleware.ContentSecurityPolicyMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.i18n",
                "apps.core.context_processors.platform",
            ],
        },
    },
]

# --- Данные -------------------------------------------------------------
_db = urlparse(env("DATABASE_URL", "postgres://ba:ba@db:5432/ba"))
DB_POOL_ENABLED = env_bool("DB_POOL_ENABLED", True)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(_db.path.lstrip("/")) or "ba",
        "USER": unquote(_db.username or "ba"),
        "PASSWORD": unquote(_db.password or ""),
        "HOST": _db.hostname or "db",
        "PORT": str(_db.port or 5432),
        # Пул и CONN_MAX_AGE взаимоисключающи (§2.5).
        "CONN_MAX_AGE": 0 if DB_POOL_ENABLED else 60,
        "CONN_HEALTH_CHECKS": not DB_POOL_ENABLED,
        "OPTIONS": (
            {"pool": {"min_size": env_int("DB_POOL_MIN", 2), "max_size": env_int("DB_POOL_MAX", 8)}}
            if DB_POOL_ENABLED
            else {}
        ),
        "ATOMIC_REQUESTS": False,
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("REDIS_CACHE_URL", "redis://redis-cache:6379/1"),
        "KEY_PREFIX": "ba",
        "TIMEOUT": 300,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    },
}

# --- Аутентификация -----------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
PASSWORD_HASHERS = [
    "apps.accounts.hashers.BAArgon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_RESET_TIMEOUT = 1800
SESSION_ENGINE = "django.contrib.sessions.backends.db"

# --- Безопасность -------------------------------------------------------
SESSION_COOKIE_DOMAIN = None
CSRF_COOKIE_DOMAIN = None
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", env("PORTAL_ORIGIN", "https://portal.test:8443"))

PORTAL_ORIGIN = env("PORTAL_ORIGIN", "https://portal.test:8443")
GAMES_DOMAIN = env("GAMES_DOMAIN", "games.test")
BA_CSP_DIRECTIVES = {
    "default-src": "'self'",
    "script-src": "'self'",
    "style-src": "'self'",
    "img-src": "'self' data:",
    "font-src": "'self'",
    "connect-src": "'self'",
    "frame-src": env("BA_GAMES_FRAME_SRC", f"https://*.{GAMES_DOMAIN}:8443"),
    "frame-ancestors": "'none'",
    "base-uri": "'self'",
    "form-action": "'self'",
    "object-src": "'none'",
}
BA_PERMISSIONS_POLICY = "geolocation=(), microphone=(), camera=(), payment=()"

# --- Интернационализация ------------------------------------------------
LANGUAGE_CODE = "en"
LANGUAGES = [
    ("en", "English"), ("de", "Deutsch"), ("nl", "Nederlands"),
    ("ru", "Русский"), ("fr", "Français"), ("es", "Español"),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True
USE_TZ = True
TIME_ZONE = "UTC"

# --- Статика и загрузки -------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024
FILE_UPLOAD_PERMISSIONS = 0o640
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o750

# --- Celery -------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", env("REDIS_BROKER_URL", "redis://redis-broker:6379/2"))
CELERY_RESULT_BACKEND = None
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TIMEZONE = "UTC"
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BEAT_SCHEDULE: dict[str, dict[str, object]] = {}

# --- DRF ----------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "sessions": "30/hour",
        "results": "60/hour",
        "heartbeat": "3/min",
        "storage": "600/hour",
    },
    "UNAUTHENTICATED_USER": "django.contrib.auth.models.AnonymousUser",
}

# --- Константы пайплайна (§2.14.2) --------------------------------------
BA_SDK_DEFAULT_VERSION = env("BA_SDK_DEFAULT_VERSION", "1.1.0")
ZIP_MAX_BYTES = env_int("ZIP_MAX_BYTES", 26_214_400)
CRITICAL_PATH_WARN_BYTES = env_int("CRITICAL_PATH_WARN_BYTES", 2_097_152)
CRITICAL_PATH_MAX_BYTES = env_int("CRITICAL_PATH_MAX_BYTES", 4_194_304)
ADMIN_URL_PREFIX = env("ADMIN_URL_PREFIX", "crm/")

# --- Журналирование (JSON + request-id, §2.24) --------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "apps.core.logging.JsonFormatter"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "json"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "django.db.backends": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "apps": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "celery": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
BA_EOF

write_file config/settings/dev.py <<'BA_EOF'
"""Development: portal.test:8443, HSTS выключен (§2.20)."""
from __future__ import annotations

from .base import *  # noqa: F403
from .base import env, env_list

DEBUG = True
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "portal.test,localhost,127.0.0.1,web")
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_PRELOAD = False
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_SSL_REDIRECT = False

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", "mailpit")
EMAIL_PORT = int(env("EMAIL_PORT", "1025"))
EMAIL_USE_TLS = False
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "no-reply@portal.test")

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]
BA_EOF

write_file config/settings/prod.py <<'BA_EOF'
"""Production (§2.20, Приложение B)."""
from __future__ import annotations

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration

from .base import *  # noqa: F403
from .base import env, env_bool, env_list

DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 63_072_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

STORAGES["staticfiles"]["BACKEND"] = (  # noqa: F405
    "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
)

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_PASSWORD")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")

BA_CSP_DIRECTIVES["img-src"] = f"'self' data: {env('CDN_BASE_URL')}".strip()  # noqa: F405

SENTRY_DSN = env("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=env("SENTRY_ENV", "production"),
        integrations=[DjangoIntegration(), CeleryIntegration()],
        send_default_pii=False,
        traces_sample_rate=0.05,
    )
BA_EOF

write_file config/settings/staging.py <<'BA_EOF'
"""Staging: обезличенные данные, noindex, отдельные секреты (§2.5)."""
from __future__ import annotations

from .prod import *  # noqa: F403
from .base import env

SENTRY_ENV = env("SENTRY_ENV", "staging")
BA_NOINDEX = True
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
BA_EOF

write_file config/urls.py <<'BA_EOF'
"""Корневые маршруты. Языковые префиксы и CRM добавляются блоком 2."""
from __future__ import annotations

from django.conf import settings
from django.conf.urls.static import static
from django.urls import path

from apps.core import health, views

urlpatterns = [
    path("", views.index, name="index"),
    path("healthz", health.healthz, name="healthz"),
    path("readyz", health.readyz, name="readyz"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
BA_EOF

write_file apps/core/apps.py <<'BA_EOF'
from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"
    verbose_name = "Ядро платформы"
BA_EOF

write_file apps/core/ids.py <<'BA_EOF'
"""UUIDv7 на чистом Python (§2.3). Монотонность в пределах процесса."""
from __future__ import annotations

import secrets
import threading
import time
import uuid

_lock = threading.Lock()
_last_ms = 0
_seq = 0


def uuid7() -> uuid.UUID:
    global _last_ms, _seq
    with _lock:
        ms = time.time_ns() // 1_000_000
        if ms <= _last_ms:
            ms = _last_ms
            _seq = (_seq + 1) & 0xFFF
            if _seq == 0:
                ms += 1
                _last_ms = ms
        else:
            _last_ms = ms
            _seq = secrets.randbits(12)
        rand_a = _seq
    rand_b = secrets.randbits(62)
    value = (ms & 0xFFFFFFFFFFFF) << 80
    value |= 0x7 << 76
    value |= rand_a << 64
    value |= 0b10 << 62
    value |= rand_b
    return uuid.UUID(int=value)
BA_EOF

write_file apps/core/fields.py <<'BA_EOF'
"""Типы БД: citext и серверный генератор uuidv7() (PostgreSQL 18)."""
from __future__ import annotations

from typing import Any

from django.db import models
from django.db.models import Func


class CitextField(models.CharField):
    """Регистронезависимый текст; требует расширения citext."""

    def db_type(self, connection: Any) -> str:
        return "citext"

    def deconstruct(self) -> tuple[str, str, list[Any], dict[str, Any]]:
        name, _path, args, kwargs = super().deconstruct()
        return name, "apps.core.fields.CitextField", args, kwargs


class UUID7(Func):
    """DEFAULT uuidv7() на уровне БД."""

    function = "uuidv7"
    output_field = models.UUIDField()

    def __init__(self) -> None:
        super().__init__()
BA_EOF

write_file apps/core/models/base.py <<'BA_EOF'
from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7
from apps.core.ids import uuid7


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(UUIDModel):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
BA_EOF

write_file apps/core/models/__init__.py <<'BA_EOF'
from .base import TimeStampedModel, UUIDModel

__all__ = ["TimeStampedModel", "UUIDModel"]
BA_EOF

write_file apps/core/migrations/0001_extensions.py <<'BA_EOF'
from django.contrib.postgres.operations import CreateExtension
from django.db import migrations


class Migration(migrations.Migration):
    initial = True
    dependencies: list[tuple[str, str]] = []
    run_before = [("accounts", "0001_initial")]
    operations = [
        CreateExtension("citext"),
        CreateExtension("pg_trgm"),
        CreateExtension("unaccent"),
    ]
BA_EOF

write_file apps/core/logging.py <<'BA_EOF'
"""JSON-логи с request-id (§2.24)."""
from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def set_request_id(value: str) -> None:
    _request_id.set(value)


def get_request_id() -> str:
    return _request_id.get()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key in ("event", "actor", "game_id", "session_id", "duration_ms"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False)
BA_EOF

write_file apps/core/middleware.py <<'BA_EOF'
"""Request-id, заголовки безопасности и CSP с nonce (§2.20)."""
from __future__ import annotations

import secrets
import uuid
from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse

from apps.core.logging import set_request_id

GetResponse = Callable[[HttpRequest], HttpResponse]


class RequestIDMiddleware:
    def __init__(self, get_response: GetResponse) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.request_id = rid  # type: ignore[attr-defined]
        set_request_id(rid)
        response = self.get_response(request)
        response["X-Request-ID"] = rid
        return response


class SecurityHeadersMiddleware:
    def __init__(self, get_response: GetResponse) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        response.setdefault("Permissions-Policy", settings.BA_PERMISSIONS_POLICY)
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if getattr(settings, "BA_NOINDEX", False):
            response.setdefault("X-Robots-Tag", "noindex, nofollow")
        return response


class ContentSecurityPolicyMiddleware:
    def __init__(self, get_response: GetResponse) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        nonce = secrets.token_urlsafe(16)
        request.csp_nonce = nonce  # type: ignore[attr-defined]
        response = self.get_response(request)
        directives = dict(settings.BA_CSP_DIRECTIVES)
        directives["script-src"] = f"{directives['script-src']} 'nonce-{nonce}'"
        response["Content-Security-Policy"] = "; ".join(
            f"{key} {value}" for key, value in directives.items()
        )
        return response
BA_EOF

write_file apps/core/context_processors.py <<'BA_EOF'
from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest


def platform(request: HttpRequest) -> dict[str, object]:
    return {
        "csp_nonce": getattr(request, "csp_nonce", ""),
        "request_id": getattr(request, "request_id", ""),
        "portal_origin": settings.PORTAL_ORIGIN,
        "games_domain": settings.GAMES_DOMAIN,
    }
BA_EOF

write_file apps/core/health.py <<'BA_EOF'
"""Пробы живучести и готовности (§2.23)."""
from __future__ import annotations

import redis
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import HttpRequest, JsonResponse


def healthz(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


def readyz(request: HttpRequest) -> JsonResponse:
    checks: dict[str, str] = {}

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["db"] = "ok"
    except Exception:
        checks["db"] = "fail"

    try:
        cache.set("ba:readyz", "1", 10)
        checks["cache"] = "ok" if cache.get("ba:readyz") == "1" else "fail"
    except Exception:
        checks["cache"] = "fail"

    try:
        client = redis.from_url(settings.CELERY_BROKER_URL, socket_timeout=3)
        checks["broker"] = "ok" if client.ping() else "fail"
    except Exception:
        checks["broker"] = "fail"

    ready = all(value == "ok" for value in checks.values())
    return JsonResponse({"status": "ready" if ready else "degraded", "checks": checks},
                        status=200 if ready else 503)
BA_EOF

write_file apps/core/views.py <<'BA_EOF'
"""Служебная страница ядра. Заменяется порталом на блоке 2."""
from __future__ import annotations

from django.http import HttpRequest, JsonResponse


def index(request: HttpRequest) -> JsonResponse:
    return JsonResponse(
        {
            "service": "breaktime-arcade",
            "spec": "BA-PLAT-4.2",
            "stage": "1/core",
            "health": "/healthz",
            "ready": "/readyz",
        }
    )
BA_EOF

write_file apps/accounts/apps.py <<'BA_EOF'
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "Аккаунты и гости"
BA_EOF

write_file apps/accounts/hashers.py <<'BA_EOF'
"""Argon2id с параметрами §2.10.2."""
from django.contrib.auth.hashers import Argon2PasswordHasher


class BAArgon2PasswordHasher(Argon2PasswordHasher):
    time_cost = 3
    memory_cost = 65536
    parallelism = 4
BA_EOF

write_file apps/accounts/models/user.py <<'BA_EOF'
from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models

from apps.core.fields import UUID7, CitextField
from apps.core.ids import uuid7

login_validator = RegexValidator(
    regex=r"^[a-z0-9_.-]{3,30}$",
    message="Логин: 3–30 символов, только a-z, 0-9, '_', '.', '-'.",
)


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def _create(self, login: str, password: str | None, **extra: Any) -> User:
        if not login:
            raise ValueError("Логин обязателен")
        login = login.strip().lower()
        user = self.model(login=login, **extra)
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(self, login: str, password: str | None = None, **extra: Any) -> User:
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(login, password, **extra)

    def create_superuser(self, login: str, password: str | None = None, **extra: Any) -> User:
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra["is_staff"] is not True or extra["is_superuser"] is not True:
            raise ValueError("Суперпользователь требует is_staff и is_superuser")
        return self._create(login, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    login = CitextField(max_length=30, unique=True, validators=[login_validator])
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    totp_confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "login"
    REQUIRED_FIELDS: list[str] = []
    EMAIL_FIELD = ""

    class Meta:
        db_table = "accounts_user"
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    def __str__(self) -> str:
        return self.login
BA_EOF

write_file apps/accounts/models/__init__.py <<'BA_EOF'
from .user import User, UserManager

__all__ = ["User", "UserManager"]
BA_EOF

write_file static/src/css/app.css <<'BA_EOF'
@import "tailwindcss";
@import "./tokens.css";

@source "../../../templates";
@source "../../../apps";

@theme inline {
  --color-bg: var(--ba-bg);
  --color-surface: var(--ba-surface);
  --color-text: var(--ba-text);
  --color-accent: var(--ba-accent);
  --radius-card: var(--ba-radius-card);
}
BA_EOF

write_file static/src/css/tokens.css <<'BA_EOF'
/* Значения по умолчанию. В production перекрываются файлом /theme-<hash>.css (§2.7). */
:root {
  --ba-bg: #0f1115;
  --ba-surface: #171a21;
  --ba-text: #e8eaf0;
  --ba-muted: #9aa3b2;
  --ba-accent: #39ff88;
  --ba-danger: #ff5c72;
  --ba-radius-card: 14px;
  --ba-space-unit: 4px;
  --ba-font-body: system-ui, "Segoe UI", Roboto, sans-serif;
  --ba-font-display: "Segoe UI", system-ui, sans-serif;
}

@media (prefers-color-scheme: light) {
  :root:not([data-theme="dark"]) {
    --ba-bg: #f6f7fb;
    --ba-surface: #ffffff;
    --ba-text: #14161c;
    --ba-muted: #5a6270;
  }
}

:root[data-theme="light"] {
  --ba-bg: #f6f7fb;
  --ba-surface: #ffffff;
  --ba-text: #14161c;
  --ba-muted: #5a6270;
}
BA_EOF

write_file static/src/js/main.js <<'BA_EOF'
// CSP-совместимость (§2.3): allowEval выключается до инициализации HTMX.
if (window.htmx) {
  window.htmx.config.allowEval = false;
}

const THEME_KEY = "ba_theme";

function applyTheme(value) {
  document.documentElement.dataset.theme = value;
  document.cookie = `ba_theme=${value}; path=/; max-age=31536000; SameSite=Lax`;
}

function readCookie(name) {
  const row = document.cookie.split("; ").find((item) => item.startsWith(`${name}=`));
  return row ? row.split("=")[1] : null;
}

export function csrfToken() {
  return readCookie("csrftoken") ?? "";
}

document.addEventListener("DOMContentLoaded", () => {
  const saved = readCookie("ba_theme");
  if (saved === "light" || saved === "dark") {
    document.documentElement.dataset.theme = saved;
  }
  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      applyTheme(next);
    });
  });
});

export { THEME_KEY, applyTheme };
BA_EOF

write_file conftest.py <<'BA_EOF'
from __future__ import annotations

import pytest
from django.test import Client


@pytest.fixture
def anon_client() -> Client:
    return Client()
BA_EOF

write_file tests/integration/test_core.py <<'BA_EOF'
from __future__ import annotations

import uuid

import pytest
from django.test import Client

from apps.core.ids import uuid7


def test_healthz(anon_client: Client) -> None:
    response = anon_client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_security_headers(anon_client: Client) -> None:
    response = anon_client.get("/healthz")
    assert "nonce-" in response["Content-Security-Policy"]
    assert response["X-Request-ID"]
    assert response["X-Frame-Options"] == "DENY"


def test_uuid7_monotonic_and_version() -> None:
    values = [uuid7() for _ in range(1000)]
    assert all(isinstance(v, uuid.UUID) and v.version == 7 for v in values)
    assert values == sorted(values)
    assert len(set(values)) == len(values)


@pytest.mark.django_db
def test_readyz(anon_client: Client) -> None:
    response = anon_client.get("/readyz")
    assert response.status_code in {200, 503}
    assert set(response.json()["checks"]) == {"db", "cache", "broker"}
BA_EOF

write_file .github/workflows/ci.yml <<'BA_EOF'
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  quality:
    runs-on: ubuntu-24.04
    services:
      db:
        image: postgres:18
        env:
          POSTGRES_DB: ba
          POSTGRES_USER: ba
          POSTGRES_PASSWORD: ba
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U ba" --health-interval 10s
          --health-timeout 5s --health-retries 10
      redis-cache:
        image: redis:8-alpine
        ports: ["6379:6379"]
        options: >-
          --health-cmd "redis-cli ping" --health-interval 10s
          --health-timeout 5s --health-retries 10
      redis-broker:
        image: redis:8-alpine
        ports: ["6380:6379"]
        options: >-
          --health-cmd "redis-cli ping" --health-interval 10s
          --health-timeout 5s --health-retries 10
    env:
      DJANGO_SETTINGS_MODULE: config.settings.dev
      DJANGO_SECRET_KEY: ci-only
      DJANGO_ALLOWED_HOSTS: localhost,127.0.0.1
      DATABASE_URL: postgres://ba:ba@127.0.0.1:5432/ba
      REDIS_CACHE_URL: redis://127.0.0.1:6379/1
      REDIS_BROKER_URL: redis://127.0.0.1:6380/2
      CELERY_BROKER_URL: redis://127.0.0.1:6380/2
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.14"
          enable-cache: true
      - run: uv sync --frozen
      - run: uv run ruff check apps config tests
      - run: uv run ruff format --check apps config tests
      - run: uv run mypy
      - run: uv run pytest --cov=apps --cov-report=term-missing

  django-next:
    runs-on: ubuntu-24.04
    continue-on-error: true
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.14"
      - run: uv sync --frozen
      - run: uv pip install --pre "django>=6.0"
      - run: uv run python manage.py check

  image:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.14"
      - run: uv lock --check
      - run: docker build --build-arg UV_VERSION=$(uv --version | awk '{print $2}') -t ba/app:ci .
BA_EOF

# =============================================================================
printf '\nЭтап 1, блок 1\n'
printf '  Каталог:   %s\n' "$PWD"
printf '  Заполнено: %d\n' "$filled"
printf '  Пропущено: %d (не пустые; --force для перезаписи)\n' "$skipped"
if (( backed > 0 )); then printf '  Резервные копии: %s (%d)\n' "$BACKUP_DIR" "$backed"; fi
if (( DRY )); then printf '  Режим dry-run: изменения не внесены\n'; exit 0; fi

cat <<'BA_EOF'

Порядок запуска (Ubuntu / WSL):
  make env            # .env с секретами и версией uv
  make certs          # mkcert: portal.test и *.games.test
  sudo sh -c 'echo "127.0.0.1 portal.test neon-snake.games.test" >> /etc/hosts'
  make assets         # Tailwind v4 + вендорный HTMX
  make lock build     # uv.lock и образы
  make up
  make makemigrations # accounts.User и остальные приложения
  make migrate
  make superuser
  make check          # ruff + mypy + pytest (в контейнере, PostgreSQL)
  curl -k https://portal.test:8443/healthz
BA_EOF
