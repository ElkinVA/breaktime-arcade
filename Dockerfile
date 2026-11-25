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
# Dev-зависимости (pytest/ruff/mypy) ставятся только в dev-lite образе.
# Staging/production собираются с default=false и остаются без dev-пакетов.
ARG INSTALL_DEV=false
ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never
RUN test -n "${UV_VERSION}" && pip install --no-cache-dir "uv==${UV_VERSION}"
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN if [ "${INSTALL_DEV}" = "true" ]; then \
      uv sync --frozen --no-install-project; \
    else \
      uv sync --frozen --no-dev --no-install-project; \
    fi

FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings.prod
# PostgreSQL 18 client (pg_dump/pg_restore) для бэкапов (§2.5)
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
 && install -d /usr/share/postgresql-common/pgdg \
 && curl -fsS -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc \
 && . /etc/os-release \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client-18 \
 && rm -rf /var/lib/apt/lists/*

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd -g 10001 app \
 && useradd -u 10001 -g 10001 -M -s /usr/sbin/nologin app \
 && mkdir -p /app/staticfiles /app/media /app/var /var/ba/zip/uploads /var/ba/zip/artifacts \
 && chown -R app:app /app /var/ba/zip
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app . /app
COPY --from=assets --chown=app:app /build/static/dist /app/static/dist
RUN DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput \
 && chown -R app:app /app/staticfiles \
 && chmod -R a+rX /app/staticfiles /app/media
# Browser autotest for publish gating. The headless shell is enough; OS
# dependencies are installed by Playwright. Runtime user stays unprivileged.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN python -m playwright install --with-deps chromium-headless-shell \
 && chmod -R a+rX /ms-playwright
USER app
EXPOSE 8000
ENTRYPOINT ["/app/infra/scripts/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", \
     "--workers", "4", "--threads", "2", "--timeout", "60", \
     "--access-logfile", "-", "--error-logfile", "-"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1
