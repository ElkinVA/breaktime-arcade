# Архитектура Breaktime Arcade — фундамент

Документ описывает **фактически реализованный фундамент** и границы этапа 0.
Нормативные требования: BA-PLAT-4.2 и BA-GAME-2.2. Документ не заменяет ТЗ и
не объявляет этап 0 закрытым.

## 1. Компоненты

| Компонент | Назначение | Текущее состояние |
|---|---|---|
| Nginx | TLS, статика, проксирование портала | dev-lite: `portal.test:8443`, TLS mkcert; staging имеет отдельный конфиг |
| Django 5.2 | Портал, CRM, API | Ядро, accounts User, catalog, i18n, theme, CRM-бэкапы |
| PostgreSQL 18 | Основная БД, UUIDv7, citext | Миграции ядра/аккаунтов/каталога/i18n/theme/CRM применяются |
| Redis cache | Кеш, отдельный инстанс | `allkeys-lru`; используется i18n и health |
| Redis broker | Celery broker | `noeviction`, AOF; отдельный контейнер |
| Celery worker/beat | Фоновые задачи | Worker запущен; beat — профиль `beat`/`manual` |
| S3/CDN | Пакеты, runtime, медиа | В dev не подключены; контракт для следующих этапов |
| SDK | Единственный канал игра ↔ платформа | Контрактный baseline подготовлен; реализация — этап 3 |

## 2. Домены и изоляция

- Портал: `portal.test` в dev; production-домены — открытое решение владельца
  (BA-PLAT-4.2, Приложение I).
- Игры: `<host_label>.games.test` в dev; каждая игра — отдельный origin,
  cookies портала недоступны.
- Игровой хост не должен отдавать `X-Frame-Options`; изоляция — через
  `Content-Security-Policy: frame-ancestors` (BA-PLAT-4.2 §2.4.2).
- `technical_id` и `host_label` — immutable; `host_label` вычисляется из
  `technical_id`, а не из slug.

## 3. Путь запроса

```text
Browser
  -> Nginx (TLS, static, proxy)
  -> RequestIDMiddleware
  -> SessionMiddleware
  -> LocaleMiddleware
  -> LanguagePrefixMiddleware
  -> Common/CSRF/Auth/Message/Clickjacking
  -> SecurityHeadersMiddleware
  -> ContentSecurityPolicyMiddleware
  -> Django view/template
```

`LanguagePrefixMiddleware` проверяет обязательный `en` напрямую в БД,
получает активные языки через кеш с повторной проверкой и возвращает 503 при
ошибке конфигурации/инфраструктуры. Корневой `/` выбирает язык по
`Accept-Language` и отвечает 302 с `Vary: Accept-Language`; неизвестный
языковой префикс даёт 404 (BA-PLAT-4.2 §2.6).

## 4. Django-приложения

| Приложение | Реализовано | Не реализовано / следующая стадия |
|---|---|---|
| `core` | UUIDv7/citext, request-id, JSON-логи, CSP, healthz/readyz, storage | API permissions/contracts этапа 3 |
| `accounts` | `User` + Argon2 hasher | профили, email, recovery, 2FA, гости — этап 2 |
| `catalog` | Genre/Tag/Game/GameVersion/GameTranslation/GameAsset, миграции | импорт ZIP, полный контракт полей, M2M тегов/жанров — этапы 3/5 |
| `i18n` | Language, TranslationEntry, GameLocaleOverride, активные языки, middleware, switcher | CRM переводов — этап 6 |
| `theme` | ThemeTokenSet, SiteSettings, компилятор CSS | редактор темы в CRM — этап 7 |
| `crm` | BackupRun, backup/restore-check, базовые route-заглушки | импорт, модерация, роли/2FA — этапы 2/3/7 |
| `gameplay`, `leaderboards`, `ratings`, `pipeline`, `moderation`, `analytics`, `content` | Только каркасы/пустые модели | Следующие этапы; не считать функциональностью |

## 5. Данные и контракты

- PK — UUIDv7; на уровне БД `uuidv7()`, в Python — `apps.core.ids.uuid7()`.
- `citext`, `pg_trgm`, `unaccent` создаются миграцией `core.0001_extensions`.
- JSON Schema этапа 0:
  - `schemas/manifest.json`;
  - `schemas/catalog.json`;
  - `schemas/eventlog.json`.
- Контракт SDK 1.1: `sdk/1.1.0/README.md` — частичный baseline; полный
  `BA-SDK-1.1` отсутствует.
- Контракт полей импорта — **Приложение J BA-PLAT-4.2**. Полная реализация
  импорта относится к этапу 3; текущие модели не покрывают все поля.
- `BA-ENV-1.1` отсутствует; требования к окружению берутся из BA-PLAT-4.2
  §2.3/§2.5 и Приложения A.

## 6. Окружения

| Окружение | Запуск | Особенности |
|---|---|---|
| dev-lite | `compose.yml` + `compose.dev-lite.yml` | runserver, два Redis, mailpit, TLS 8443 |
| staging | `compose.staging.yml` | отдельные секреты/тома, Basic Auth, IP allowlist, noindex; не затрагивался |
| production | `compose.prod.yml` | **не заполнен**; production-конфигурация — следующий этап/решение владельца |

Секреты — только в `.env*`, `certs/`, `creds/` вне Git. Значения не выводятся
в документацию и логи. `SECRET_KEY` должен задаваться окружением;
production-настройки требуют отдельного аудита.

## 7. Безопасность

- DRF: deny-by-default (`IsAuthenticated`); публичные endpoint'ы должны
  явно объявлять `AllowAny` (BA-PLAT-4.2 §2.20, §2.23).
- CSRF включён; cookies `Secure`, `HttpOnly`, `SameSite=Lax`, host-only.
- CSP и security headers выставляются middleware; dev не включает HSTS.
- CRM: только staff, 2FA/роли — этап 2; текущий login — каркас.
- Game origin: отдельный домен, CSP `frame-ancestors`, без cookies.
- ZIP-пайплайн и SDK runtime — этап 3; в текущем фундаменте не исполняются.

## 8. Известные ограничения фундамента

1. `BA-SDK-1.1` и `BA-ENV-1.1` отсутствуют; message schemas и полный SDK
   contract не могут быть финализированы.
2. `schemas/messages/*.json` заполнены draft-схемами App F; канонический
   внешний `sessionId` утверждён владельцем, внутренний `session_id`
   используется в Python/БД. Нормативные примеры с `session_id` остаются
   расхождением (см. `docs/contracts/SESSION_ID_PROTOCOL.md`).
3. Многие сущности §2.22 (профили, сессии, результаты, рекорды, импорт,
   аналитика, модерация, контент) ещё не имеют моделей — это следующие этапы,
   не «реализованный фундамент».
4. `compose.prod.yml`, production Nginx и monitoring пусты; production не
   готов.
5. Базовые Docker-образы не зафиксированы по digest; это нужно закрыть до
   production/приёмки.
6. `docs/spec/` пуст, а README/CLAUDE ссылаются на него; нормативные копии
   находятся в `technical_specification/` и untracked.

## 9. Контракты BA-FOUNDATION-002

DRAFT-документы (не нормативные):

- `docs/contracts/BA-SDK-1.1_DRAFT.md` — предлагаемый контракт SDK;
- `docs/contracts/BA-ENV-1.1_DRAFT.md` — предлагаемый документ окружения;
- `docs/contracts/SESSION_ID_PROTOCOL.md` — внешний `sessionId` / внутренний
  `session_id`;
- `docs/contracts/MESSAGE_PROTOCOL.md` — протокол App F;
- `docs/contracts/CONTRADICTIONS.md` — нормативные расхождения;
- `docs/audits/BA-GAME-2.2_COMPARISON.md` — сравнение вариантов BA-GAME-2.2;
- `docs/foundation/DB_SCHEMA.md`, `docs/foundation/ERD.md`,
  `docs/foundation/ba_schema.sql` — проектная схема БД;
- `docs/contracts/APP_J_FIELD_MAPPING.md` — полный mapping App J.

`schemas/messages/*.json` — draft JSON Schema всех типов Приложения F;
`schemas/manifest.json`, `catalog.json`, `eventlog.json` дополняются
семантическими проверками `apps/core/contracts.py`.
