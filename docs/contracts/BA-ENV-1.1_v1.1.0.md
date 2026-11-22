# BA-ENV-1.1 — окружение и эксплуатация (v1.1.0)

**Статус:** **INTERNALLY ACCEPTED (Architect, 2026-11-22; ADR-APPF-001).**
Внутренний технический контракт окружения в пределах ТЗ; это не публикация,
не внешнее/юридическое утверждение и не production deploy. DRAFT
`BA-ENV-1.1_DRAFT.md` сохраняется как история.
**Дата версии:** 2026-11-20.
**Основание:** BA-PLAT-4.2 (ред. 12.11.2026) §2.3–§2.5, §2.20, Приложения
A/B/D/G; DRAFT BA-ENV-1.1; независимый Pro-review 2026-11-20
(conforms-with-fixes); OD-AUTONOMY-006; `docs/decisions/ADR-APPF-001.md`.
Приоритет — ТЗ.

## История изменений

| Версия | Дата | Изменения |
|---|---|---|
| 1.1.0 | 2026-11-20 | Первая финальная версия на базе DRAFT: добавлены prod-sizing, backup/DR с RPO/RTO, состав prod-сервисов и healthchecks, hardening, retention, rate-limit/NAT, игровой хост, staging-раздельность, CI; digest-политика сделана обязательной для всех окружений; закрыты вопросы, определённые ТЗ; добавлен `redis-throttle` (OD-REDIS-001) |

## 1. Поддерживаемые ОС и sizing

| Компонент | Требование | Источник |
|---|---|---|
| Production | Ubuntu Server 24.04 LTS | `[TZ]` §2.3 |
| Dev | Ubuntu 22.04 WSL2 или совместимое Linux | `[TZ]` §2.3 |
| Production sizing | 4 vCPU / 8 ГБ RAM / 160 ГБ NVMe, ЕС/ЕЭЗ | `[TZ]` §2.5 |
| Хранение | S3 ~100 ГБ + CDN перед играми и медиа | `[TZ]` §2.5 |
| Контейнеры | Docker Engine 29.9.3 + Compose 5.7.1 | `[TZ]` §2.3 |

Единый production-хост — известная точка отказа v1; план масштабирования
описывается в эксплуатационной документации.

## 2. Python, uv, Django и фронтенд

| Компонент | Требование | Источник |
|---|---|---|
| Базовый образ | `python:3.14-slim-bookworm`, **по digest** | `[TZ]` §2.3 |
| Python production | 3.14.10 через uv; системный Python не используется | `[TZ]` §2.3 |
| Пакеты | `uv.lock`; `uv lock --check`; CI `uv sync --frozen` | `[TZ]` §2.3 |
| Django | 5.2 LTS ≥5.2.19; Django 6.2 LTS — в течение 3 мес. после выхода; CI с этапа 1 гоняет 6.x неблокирующе | `[TZ]` §2.3 |
| DRF | same-origin `/api/v1/`, SessionAuthentication + CSRF | `[TZ]` §2.23 |
| psycopg | 3.3.8 `[binary,pool]`; psycopg2 запрещён | `[TZ]` §2.3 |
| Celery | 5.7.0 + Beat; dev Beat — профиль `manual` | `[TZ]` §2.3/§2.5 |
| Node.js | 22 LTS только сборка assets (Tailwind v4) | `[TZ]` §2.3 |
| Python на хосте | не использовать для запуска приложения | `[TZ]` §2.3 |
| Резерв Python | 3.13 только при доказанной несовместимости с письменной фиксацией | `[TZ]` §2.3 |
| Фронтенд | Django Templates + HTMX 2.x + Vanilla JS ES2022 + Tailwind v4; React/Vue/SPA/Alpine запрещены | `[TZ]` §2.3 |
| CSP-совместимость | `htmx.config.allowEval=false`; без `hx-on:*`, inline-обработчиков, `javascript:`, inline `style`; палитра — внешний `/theme-<hash>.css` | `[TZ]` §2.3 |

## 3. PostgreSQL, Redis и Django-настройки

| Компонент | Требование | Источник |
|---|---|---|
| PostgreSQL | 18.x, образ `postgres:18` по digest; том `/var/lib/postgresql` (не `/data`); `shm_size: 256mb` | `[TZ]` §2.3/§2.5 |
| Расширения | `citext`, `pg_trgm`, `unaccent` создаются миграцией `core.0001` до использования | `[TZ]` §2.3 |
| Идентификаторы | PK UUIDv7 (`core.ids.uuid7()` + DB `DEFAULT uuidv7()`); событийные таблицы BIGINT identity | `[TZ]` §2.3 |
| Тесты | только PostgreSQL | `[TZ]` §2.3 |
| Pool | `OPTIONS={"pool":{"min_size":2,"max_size":8}}` при `CONN_MAX_AGE=0`; иначе `CONN_MAX_AGE=60` + `CONN_HEALTH_CHECKS=True`; оба механизма одновременно запрещены; сумма max_size ≤ max_connections − 5 | `[TZ]` §2.5 |
| Redis cache | отдельный инстанс, `allkeys-lru`, без AOF | `[TZ]` §2.3/§2.5 |
| Redis broker | отдельный инстанс, `noeviction`, AOF | `[TZ]` §2.3/§2.5 |
| Redis throttle | отдельный инстанс `redis-throttle`, `noeviction`, без AOF, без бэкапа (техническое решение OD-REDIS-001) | `[PROP/tech]` |
| Cache/broker | объединять запрещено даже в dev | `[TZ]` §2.5 |
| Django critical settings | Приложение B: `DEBUG=False`, host-only cookies, Secure/HttpOnly, SameSite=Lax, SSL redirect, proxy header, HSTS prod 63072000, Argon2id, `PASSWORD_RESET_TIMEOUT=1800`, `USE_TZ=True`, `AUTH_USER_MODEL`, upload limits 5/30 МиБ | `[TZ]` Прил. B |

## 4. Docker и Compose

| Компонент | Требование | Источник |
|---|---|---|
| Dockerfile | multi-stage Python 3.14 + Node 22 build; runtime non-root UID 10001 | `[TZ]` §2.5 |
| Образы | **все** образы всех окружений фиксируются по digest; плавающие теги в production запрещены; staging — не исключение | `[TZ]` §2.3/§2.5 |
| Сервисы | `web`, `db`, `redis-cache`, `redis-broker`, `redis-throttle`, `worker`, `beat`, `nginx`, `backup`, `restore-check` | `[TZ]` §2.5 + OD-REDIS-001 |
| Healthcheck | у каждого сервиса; `depends_on: condition: service_healthy` | `[TZ]` §2.5 |
| Restart/лимиты | `restart: unless-stopped`; лимиты CPU/RAM; непривилегированный UID | `[TZ]` §2.5 |
| Тома | постоянные; PostgreSQL volume `/var/lib/postgresql` | `[TZ]` §2.5 |
| Production Compose | `compose.prod.yml` должен содержать полный набор сервисов, healthchecks, лимиты, сети и секреты; пустой файл — дефект, а не «открытый вопрос» | `[TZ]` §2.5 |
| Mailpit | dev only; version-tag + digest, не `latest` в production | `[PROP]` |

Digest-политика: получение digest базовых Python/Node образов — техническая
задача; до её выполнения сборка не считается воспроизводимой, но плавающие
теги в production всё равно запрещены.

## 5. Nginx, TLS, домены и раздача игр

| Требование | Значение | Источник |
|---|---|---|
| Dev portal | `portal.test:8443`, mkcert; Django 8000 | `[TZ]` §2.4 |
| Dev games | `<host_label>.games.test:8443` | `[TZ]` §2.4 |
| Production | реальные домены, Let's Encrypt DNS-01 wildcard | `[TZ]` §2.4/§2.5 |
| Staging | Basic Auth + IP allowlist + `noindex`, отдельные секреты, mail sandbox | `[TZ]` §2.4/§2.5 |
| HSTS | dev выключен; prod `max-age=63072000` + `includeSubDomains` + `preload` по Приложению B; preload активируется только после реальных доменов/TLS (временное ограничение, ADR-APPF-001 D3) | `[TZ]` Прил. B |
| Game host | отдельный origin; cookies запрещены; `X-Frame-Options` отсутствует; изоляция только CSP `frame-ancestors` | `[TZ]` §2.4.2 |
| Game headers | `X-Robots-Tag: noindex, nofollow`; `Referrer-Policy: no-referrer`; CSP по capabilities | `[TZ]` §2.4.2/§2.20 |
| Version path | `/v/<runtime_hash[:12]>/`, неизменяем; `index.html` — `no-cache`; ассеты — `immutable` | `[TZ]` §2.4.2 |
| Storage | исходные ZIP — приватный S3; runtime — публичный CDN/Nginx; S3 website-endpoint запрещён | `[TZ]` §2.4.2 |
| ACME | порт 80 доступен для HTTP-01/DNS-01 по политике | `[TZ]` §2.5 |

## 6. Переменные окружения

Имена по Приложению A и фактические настройки проекта. Значения секретов в
документацию и Git не попадают; `.env.example` — без значений.

`DJANGO_SECRET_KEY`, `DJANGO_SETTINGS_MODULE`, `DJANGO_ALLOWED_HOSTS`,
`DEBUG=False`, `DATABASE_URL`, `REDIS_CACHE_URL`, `REDIS_BROKER_URL`,
`REDIS_THROTTLE_URL` (`[PROP/tech]`), `CELERY_BROKER_URL`,
`EMAIL_HOST/PORT/USER/PASSWORD`, `DEFAULT_FROM_EMAIL`,
`S3_ENDPOINT/BUCKET/ACCESS_KEY/SECRET_KEY/REGION`, `S3_PACKAGES_BUCKET`
(приватный), `S3_RUNTIME_BUCKET` (публичный), `CDN_BASE_URL`, `GAMES_DOMAIN`,
`PORTAL_ORIGIN`, `SENTRY_DSN`, `SENTRY_ENV`, `HIBP_ENABLED`,
`BACKUP_TARGET_URI`, `BACKUP_PASSPHRASE`, `ADMIN_URL_PREFIX`, `TOTP_ISSUER`,
`ANON_SIGNING_KEY`, `NICKNAME_HMAC_KEY`, `SESSION_BINDING_KEY`,
`GUNICORN_WORKERS=4`, `DB_POOL_MIN=2`, `DB_POOL_MAX=8`,
`BA_SDK_DEFAULT_VERSION=1.1.0`, `ZIP_MAX_BYTES=26214400`,
`CRITICAL_PATH_WARN_BYTES=2097152`, `CRITICAL_PATH_MAX_BYTES=4194304`.

Обязательность: без `DJANGO_SECRET_KEY`, `DATABASE_URL`, `PORTAL_ORIGIN`,
`GAMES_DOMAIN`, ключей подписи и S3/backup-параметров production не
запускается. Dev-lite использует безопасные локальные значения.

## 7. Окружения, сеть и безопасность

### dev-lite (3.8 GiB RAM)

PostgreSQL `shared_buffers=256MB`, `max_connections=30`, `work_mem=4MB`;
два Redis по 64 МБ (cache LRU + broker noeviction); `redis-throttle` 64 МБ
noeviction; Django `runserver`; Celery `--pool=solo --concurrency=1`; Beat
`manual`; Nginx TLS 8443; Playwright `--workers=1`; CDN/Sentry/счётчик
выключены; бэкапы по требованию. Пиковое потребление ≈2.4 ГБ.

### staging

Отдельные compose project, сети, тома, БД и секреты (`.env.staging`);
Basic Auth + IP allowlist; `noindex`; mail sandbox; запрещены реальные ПДн;
restore-check ежемесячно.

### production

Gunicorn 4 воркера (диапазон 3–6 по S1–S4); отдельные Redis; S3/CDN/Sentry
(ЕС); WAL/PITR; мониторинг и алерты; реальные домены; HSTS 63072000.

### Сеть и hardening

- UFW: 22/80/443; БД и Redis — только внутренняя сеть; публикация портов
  БД/Redis запрещена.
- SSH только по ключам; fail2ban; автообновления безопасности.
- Секреты — env/Docker secrets; ротация в runbook; Sentry без PII; логи без
  секретов.
- Rate limiting: первичный ключ — субъект; IP — вторичный с повышенными
  порогами; IPv6 агрегируется по /64; после IP-порога — прогрессивный
  challenge (механизм — решение владельца, O4), не жёсткая блокировка NAT.
- Нагрузка: S1–S4 (Прил. G); пороги TTFB/p95/ошибок; 0 потерянных рекордов,
  0 дедлоков; очередь Celery не растёт.

## 8. Резервное копирование и DR

| Параметр | Требование |
|---|---|
| Полная копия PostgreSQL | ежедневно 03:00 UTC |
| WAL-архивирование | непрерывно, PITR |
| RPO / RTO | ≤15 минут / ≤4 часа |
| Хранение | 30 дней, отдельный провайдер/регион, immutable |
| Медиа и пакеты | ежедневная синхронизация S3, versioning бакетов |
| Проверка восстановления | автоматически ежемесячно на staging + ручные учения раз в квартал |
| Контроль | алерт при сбое, статус в CRM |

Сервисы `backup` и `restore-check` входят в compose; `restore-check`
read-only и не изменяет production-данные.

## 9. Сроки хранения

Сроки — Приложение D: сырые события 90 дней (агрегаты бессрочно);
`GameSession` 30 дней; `GameImportDraft` 7 дней; `GamePlayCredit` 90 дней;
гостевое `GameStorage` 90 дней с последнего доступа; `AnonymousIdentity`
90 дней; результаты/рекорды — до удаления аккаунта; исходные пакеты и
бандлы — бессрочно, пока существует игра; `NicknameReservation` 24 мес.;
`SecurityEvent` 12 мес.; `AdminAuditLog` 24 мес.; почтовые логи 30 дней;
бэкапы 30 дней; согласия — срок действия + 12 мес.

Типы без срока в ТЗ и юридические вопросы —
`docs/decisions/RETENTION_PROPOSAL.md`; до решения владельца деструктивные
задачи не включаются.

## 10. Воспроизводимость и CI

- `uv.lock` — единственный lock Python; `package-lock.json` — lock Node.
- Все образы — по digest; production не использует плавающие теги.
- CI: `uv sync --frozen`, `uv lock --check`, ruff, mypy, pytest (PostgreSQL),
  Django check, `makemigrations --check`, schema checks, Playwright E2E.
- Обновления зависимостей — Renovate; скан уязвимостей в CI.
- Документация: Dockerfile, compose-файлы, `.env.example`, lock-файлы,
  инструкции установки/обновления/отката/бэкапа/восстановления/добавления и
  обновления игры/языка/ротации секретов/инцидентов.

## 11. Вопросы, утверждаемые вместе с документом

1. Механизм прогрессивного challenge после IP-порога: выбран **proof-of-work
   платформы** без внешнего платного провайдера (ADR-APPF-001 D3); до
   реализации действует временный `429`.
2. HSTS: production-значения — по Приложению B (`includeSubDomains`,
   `preload`); preload активируется после реальных доменов/TLS (временное
   ограничение, ADR-APPF-001 D3).
3. Конкретные провайдеры S3/CDN/Sentry/mail и их версии/образы — технические
   задачи внедрения, не контракт.
4. `REDIS_THROTTLE_URL` и отдельный инстанс — техническое решение
   OD-REDIS-001; включено в контракт как обязательное для предсказуемости
   throttle.

## 12. Открытые технические работы (не нормативные)

Создание `compose.prod.yml` и production Nginx; получение digest базовых
образов; настройка WAL/PITR и внешнего backup; выбор мониторинга; реальные
значения провайдеров; проверка restore-check; реализация challenge.
