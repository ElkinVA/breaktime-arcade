# BA-ENV-1.1 — DRAFT

# DRAFT — НЕ УТВЕРЖДЕНО ВЛАДЕЛЬЦЕМ

**Статус:** проект документа окружения для BA-FOUNDATION-002. Оригинал
`BA-ENV-1.1` отсутствует; документ не является нормативным и не должен
подключаться как окончательный контракт.

Дата: 2026-11-19.

Источники: BA-PLAT-4.2 §2.3, §2.4, §2.5, Приложения A/B/I; фактические
`Dockerfile`, `compose.yml`, `compose.dev-lite.yml`, `pyproject.toml`,
`uv.lock`. Маркировка: `[TZ]` — прямое требование, `[FACT]` — фактическое
состояние проекта, `[PROP]` — предложение, `[OPEN]` — требует решения.

## 1. Поддерживаемые ОС

| Компонент | Требование | Источник |
|---|---|---|
| Production | Ubuntu Server 24.04 LTS | `[TZ]` §2.3 |
| Dev | Ubuntu 22.04 WSL2 или совместимое Linux-окружение | `[TZ]` §2.3 |
| Контейнеры | Docker Engine 29.9.3 + Compose 5.7.1 | `[TZ]` §2.3; проверено `[FACT]` |

## 2. Python, uv и Django

| Компонент | Значение | Источник |
|---|---|---|
| Python production | 3.14.10 | `[TZ]` §2.3; `[FACT]` 3.14.10 в web-контейнере |
| Python package manager | uv, lock `uv.lock` | `[TZ]`; `[FACT]` `uv lock --check` |
| Django | 5.2 LTS, ≥5.2.19 | `[TZ]`; `[FACT]` 5.2.19 |
| DRF | Django REST Framework | `[TZ]` |
| psycopg | 3.3.8 `[binary,pool]`, psycopg2 запрещён | `[TZ]`; `[FACT]` 3.3.8 |
| Celery | 5.7.0 + Beat | `[TZ]`; `[FACT]` 5.7.0 в pyproject/uv.lock |
| Node.js | 22 LTS только для сборки assets | `[TZ]` |
| Python на хосте | не использовать для запуска приложения | `[TZ]` |

`[PROP]` Python 3.13 — только резерв при доказанной несовместимости с
письменной фиксацией; сейчас не применяется.

## 3. PostgreSQL и Redis

| Сервис | Требование | Источник |
|---|---|---|
| PostgreSQL | 18.x; образ `postgres:18`; том `/var/lib/postgresql` (не `/data`) | `[TZ]` §2.3/§2.5 |
| Pool | psycopg pool; `CONN_MAX_AGE=0` при pool; иначе `60` + health checks | `[TZ]` §2.5; `[FACT]` settings |
| Redis cache | отдельный инстанс; `allkeys-lru`; без AOF | `[TZ]` §2.3/§2.5 |
| Redis broker | отдельный инстанс; `noeviction`; AOF | `[TZ]` |
| Cache/broker | объединять запрещено даже в dev | `[TZ]` §2.5 |

## 4. Docker и Compose

| Компонент | Фактическое состояние | Источник |
|---|---|---|
| Dockerfile | multi-stage Python 3.14 + Node 22 build; runtime non-root UID 10001 | `[FACT]` |
| Base Python image | `python:3.14-slim-bookworm` по тегу; digest не закреплён | `[FACT]`; `[OPEN]` |
| Base Node image | `node:22-bookworm-slim` по тегу; digest не закреплён | `[FACT]`; `[OPEN]` |
| PostgreSQL image | `postgres:18`; локальный digest доступен | `[FACT]`; см. §8 |
| Redis image | `redis:8-alpine`; локальный digest доступен | `[FACT]`; см. §8 |
| Nginx image | `nginxinc/nginx-unprivileged:1.29-alpine`; локальный digest доступен | `[FACT]`; см. §8 |
| Mailpit | `axllent/mailpit:latest`; dev only | `[FACT]`; `[OPEN]` digest |
| Production Compose | `compose.prod.yml` пуст | `[FACT]`; `[OPEN]` |
| Staging | отдельный compose/секреты; в этой задаче не затрагивался | `[FACT]` |

`[PROP]` Все образы, участвующие в воспроизводимой сборке, должны быть
зафиксированы по digest. Для базовых Python/Node digest не получен:
registry `docker manifest inspect` завершился таймаутом. Это незакрытое
требование, а не разрешение использовать плавающие теги в production.

## 5. Nginx, TLS и домены

| Требование | Значение | Источник |
|---|---|---|
| Dev portal | `portal.test:8443`, TLS mkcert | `[TZ]` §2.4/§2.20 |
| Dev games | `<host_label>.games.test:8443` | `[TZ]` |
| Production | реальные домены, Let's Encrypt DNS-01 wildcard | `[TZ]` §2.4/§2.5 |
| HSTS dev | выключен | `[TZ]` |
| HSTS prod | 63072000, includeSubDomains, preload | `[TZ]` Приложение B |
| Game host | отдельный origin; cookies запрещены; `X-Frame-Options` отсутствует | `[TZ]` §2.4.2 |
| Staging | Basic Auth + IP allowlist + noindex | `[TZ]` |

## 6. Переменные окружения

Имена из BA-PLAT-4.2, Приложение A (значения в документе не приводятся):

```text
DJANGO_SECRET_KEY
DJANGO_SETTINGS_MODULE
DJANGO_ALLOWED_HOSTS
DEBUG
DATABASE_URL
REDIS_CACHE_URL
REDIS_BROKER_URL
CELERY_BROKER_URL
EMAIL_HOST
EMAIL_PORT
EMAIL_USER
EMAIL_PASSWORD
DEFAULT_FROM_EMAIL
S3_ENDPOINT
S3_BUCKET
S3_ACCESS_KEY
S3_SECRET_KEY
S3_REGION
S3_PACKAGES_BUCKET
S3_RUNTIME_BUCKET
CDN_BASE_URL
GAMES_DOMAIN
PORTAL_ORIGIN
SENTRY_DSN
SENTRY_ENV
HIBP_ENABLED
BACKUP_TARGET_URI
BACKUP_PASSPHRASE
ADMIN_URL_PREFIX
TOTP_ISSUER
ANON_SIGNING_KEY
NICKNAME_HMAC_KEY
SESSION_BINDING_KEY
GUNICORN_WORKERS
DB_POOL_MIN
DB_POOL_MAX
BA_SDK_DEFAULT_VERSION
ZIP_MAX_BYTES
CRITICAL_PATH_WARN_BYTES
CRITICAL_PATH_MAX_BYTES
```

Секреты хранятся только в `.env*`, Docker secrets, `certs/`, `creds/`; в Git
и документацию значения не попадают.

## 7. Сетевая архитектура и окружения

```text
Internet
  -> Nginx (TLS)
  -> Django web (same-origin portal/CRM/API)
  -> PostgreSQL, Redis cache, Redis broker
  -> Celery worker/beat
  -> S3/CDN (следующие этапы)

Game origin: <host_label>.games.test / <host_label>.example-games.net
  -> только статика runtime bundle
```

| Окружение | Django | Nginx | Redis | PostgreSQL | Секреты |
|---|---|---|---|---|---|
| dev-lite | runserver | mkcert 8443 | 2 × 64 МБ | limits 768M | `.env` |
| staging | gunicorn | Basic Auth/IP/noindex | отдельные | отдельный volume | `.env.staging` |
| production | gunicorn 4 workers | Let's Encrypt | отдельные | отдельный | secrets/`.env` |

`[TZ]` dev-lite: `shared_buffers=256MB`, `max_connections=30`, `work_mem=4MB`,
Redis по 64 МБ, Celery `--pool=solo --concurrency=1`, Beat profile manual,
Nginx TLS обязателен.

## 8. Digest-политика

Локально проверенные registry digests (из `docker image inspect`):

```text
postgres:18
  postgres@sha256:b9f6b8ff03b62f3cfd9d9ba3fe56226a9991c79d3fb46fd46536263bf02be553

redis:8-alpine
  redis@sha256:7958cfbb9d152f87dadfbc89f1b0b15938f0b81ff8982feb327476f4911935c3

nginxinc/nginx-unprivileged:1.29-alpine
  nginxinc/nginx-unprivileged@sha256:0c79d56aee561a1d81c63f00eee5fb5fe29279560cdc55e91425133104c7fbe6

axllent/mailpit:latest (dev only)
  axllent/mailpit@sha256:aef2aacc11f075ec0fb6874275ee4a421e688e11a96ebb296134d1735c7761ce
```

В `compose.dev-lite.yml` образы PostgreSQL, Redis cache/broker, Nginx и
Mailpit закреплены по локально проверенным digest. Базовый `compose.yml` и
staging сохраняют теги, потому что staging по условию задачи не изменялся;
это исключение, а не норма production.

`[OPEN]` Python и Node base images отсутствуют локально; registry
`docker manifest inspect` завершился таймаутом. Digest не выдумываются.
`[PROP]` Зафиксировать их после получения registry digest; до этого
считать требование воспроизводимости частично незакрытым.

## 9. Воспроизводимость

- `uv.lock` — единственный lock Python-зависимостей; `uv lock --check`.
- `package-lock.json` — lock Node-сборки.
- Compose-образы: digest для доступных сервисов; base images — открытый
  вопрос.
- CI должен выполнять `uv sync --frozen`, lint, types, pytest, Django check,
  migration check, schema checks и `uv lock --check`.
- Production не должен использовать плавающие теги; исключения — только
  письменно обоснованные.

## 10. Открытые вопросы

1. Digest Python/Node base images.
2. Production `compose.prod.yml`, production Nginx и monitoring.
3. Точные версии/образы S3/CDN/Sentry/почтового провайдера.
4. Параметры WAL/PITR и внешнего backup.
5. Утверждение BA-ENV-1.1 владельцем.
6. Различия dev/staging/prod по ресурсным лимитам и секретам требуют
   отдельного аудита.
