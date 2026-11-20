# BA-FOUNDATION-001 — отчёт о фундаменте этапа 0

**Статус: Partial / Blocked.**
Этап 0 **не закрыт**. Отчёт подготовлен для независимого аудита; формальная
приёмка остаётся за владельцем.

Дата: 2026-11-19.
Среда: локальная dev-среда, staging/production не затрагивались.

## 1. Краткое резюме

Выполнена инвентаризация этапа 0, проверены архитектура, инфраструктура,
миграции, тесты и документация. Закрыты подтверждённые дефекты, не требующие
новых нормативных решений:

- заполнены JSON Schema манифеста, каталога и eventLog;
- подготовлен частичный контракт SDK 1.1 из BA-GAME-2.2 §6 и BA-PLAT-4.2
  §2.12/Приложения F;
- DRF переведён в deny-by-default;
- nginx healthcheck переведён на проверку реального listener;
- заполнены архитектурная/API-документация и базовые runbooks;
- добавлены проверки JSON Schema;
- проверены тесты, миграции, dev-стек, backup и restore-check.

Этап 0 **не может быть закрыт**:

- `BA-SDK-1.1` и `BA-ENV-1.1` отсутствуют;
- в нормативном тексте конфликтуют `sessionId` и `session_id`;
- message schemas и полный SDK contract не финализированы;
- схема БД покрывает только часть §2.22/Приложения J;
- production-конфигурация, WAL/PITR/S3 и monitoring не готовы;
- базовые Docker-образы не зафиксированы по digest.

## 2. Исходное состояние проекта

Зафиксировано до изменений:

```text
Branch: main
HEAD: 1fc96b40b6c11b1fcb20e1e5a833a65d166c8340
Tracked modified: 45
Untracked: 34
Staged: 0
Remote: отсутствует
```

Фактически реализованы: core (UUIDv7/citext, middleware, CSP, JSON-логи,
healthz/readyz, storage), accounts.User + Argon2, catalog (модели/миграции),
i18n (6 языков, словари, middleware), theme (токены/CSS), crm (backup/
restore-check), dev-lite и staging nginx. Остальные приложения в основном
являются каркасами/пустыми файлами.

## 3. Реестр требований этапа 0

Нормативная основа: BA-PLAT-4.2 §2.3–§2.5, §2.22, §2.25, Приложения A, J, K;
BA-GAME-2.2 §5, §6, §11.

| № | Требование | Статус | Доказательство/ограничение |
|---|---|---|---|
| 0.1 | Матрица зависимостей и lock | **PARTIAL** | `uv.lock` существует; `uv lock --check` — 79 packages, OK; Python 3.14.10, Django 5.2.19, psycopg 3.3.8; Docker Engine 29.9.3, Compose 5.7.1. Базовые образы Python/Node и образы compose не зафиксированы по digest |
| 0.2 | Домены и TLS | **PARTIAL** | dev: `portal.test`, `*.games.test`, mkcert, 8443; staging имеет отдельный конфиг; production-домены/TLS — открытое решение владельца (Приложение I); `compose.prod.yml`/prod Nginx пусты |
| 0.3 | Контракт SDK 1.1 | **BLOCKED** | Подготовлен `sdk/1.1.0/README.md` как частичный baseline; `BA-SDK-1.1` отсутствует; `sdk/1.1.0/ba-sdk.js` пуст (этап 3); message schemas не финализированы |
| 0.4 | JSON Schema manifest/catalog/eventLog | **DONE** | Заполнены `schemas/manifest.json`, `catalog.json`, `eventlog.json`; Draft 2020-12; 10 тестов, включая примеры из BA-GAME-2.2 |
| 0.5 | Контракт полей (Приложение J) | **PARTIAL** | Нормативный контракт есть в BA-PLAT-4.2; модели каталога покрывают часть полей; `GameAdditionalGenre`, `GameTag`, `GameImportDraft` и полный import mapping отсутствуют |
| 0.6 | Схема БД | **PARTIAL** | Миграции core/accounts/catalog/i18n/theme/crm применяются; `makemigrations --check`/`migrate --plan` — без операций. Многие сущности §2.22 (профили, сессии, результаты, рекорды, оценки, модерация, аналитика, контент) не имеют моделей; immutability `technical_id`/`host_label`/`GameVersion` не обеспечена на уровне модели/БД |
| 0.7 | Каркас CI | **PARTIAL** | `.github/workflows/ci.yml` запускает `uv lock --check`, ruff, mypy, pytest; добавлены schema-тесты. Нет отдельного шага `manage.py check`/migration check; `release.yml` пуст |
| 0.8 | Критерий выхода: lock собирается | **DONE (config-level)** | `uv lock --check`; полный `docker build` в этой задаче не выполнялся |
| 0.9 | Критерий выхода: контракты зафиксированы | **BLOCKED** | SDK/ENV отсутствуют; message schemas не финализированы; field/DB contract частичен |
| 0.10 | Критерий выхода: схема ревью пройдена | **BLOCKED** | Владелец/архитектор ещё не проводили ревью полной схемы; текущая схема частична |

## 4. BA-SDK-1.1 и BA-ENV-1.1

### 4.1. Происхождение и наличие

- `BA-SDK-1.1` — контракт SDK, на который ссылаются BA-PLAT-4.2 (преамбула,
  §2.14.3, §2.25) и BA-GAME-2.2 (преамбула, §6).
- `BA-ENV-1.1` — документ об окружении; BA-PLAT-4.2 ссылается на него в
  преамбуле и §2.5 (BA-ENV §4.6, резерв Python 3.13).
- В BA, AI Dev, docs/ и истории Git оригиналов нет. AI Dev
  `docs/project-reference/README.md` также фиксирует их отсутствие.
- `sdk/1.1.0/ba-sdk.js`, `schemas/messages/*.json`, `games-src/neon_snake/*`
  до задачи были пустыми.

### 4.2. Что подготовлено

- `sdk/1.1.0/README.md`: только явно выводимый контракт интерфейса,
  сообщений, таймаутов, гостевого отказа, ретраев и хранилища.
- `schemas/manifest.json`, `schemas/catalog.json`, `schemas/eventlog.json`:
  машинные контракты, не требующие BA-SDK-1.1.
- Полный `BA-SDK-1.1`/`BA-ENV-1.1` не создавался: это было бы выдумыванием
  нормативного документа.

### 4.3. Блокирующие вопросы

1. **`sessionId` vs `session_id`.** BA-PLAT-4.2 §2.12.2 использует
   `session_id`, Приложение F — `sessionId`. Канонический вариант должен
   утвердить владелец. JSON Schema сообщений не фиксируются до решения.
2. **Payload-схемы.** Полные payload-формы `ba:hello`, `ba:storage`,
   `ba:result` и других сообщений в доступных ТЗ не описаны. Нужен
   BA-SDK-1.1 или отдельное решение владельца.
3. **BA-ENV-1.1.** Отсутствует; требования окружения можно брать только из
   BA-PLAT §2.3/§2.5/Приложения A. Полный документ не восстановлен.

## 5. Выполненные изменения

| Файл | Изменение |
|---|---|
| `schemas/manifest.json` | JSON Schema 2020-12 манифеста по BA-GAME-2.2 §5 |
| `schemas/catalog.json` | JSON Schema каталога по BA-GAME-2.2 §11 |
| `schemas/eventlog.json` | JSON Schema eventLog по BA-PLAT-4.2 §2.12.7 |
| `sdk/1.1.0/README.md` | Частичный SDK contract baseline; ограничения и открытые вопросы |
| `config/settings/base.py` | DRF `DEFAULT_PERMISSION_CLASSES` → `IsAuthenticated` (deny-by-default) |
| `compose.yml` | nginx healthcheck → `nc -z` реального listener 8443 (AD-001) |
| `docs/architecture.md` | Фактическая архитектура, компоненты, границы этапа 0 |
| `docs/api.md` | Реализованные маршруты; плановый `/api/v1/` явно не реализован |
| `docs/runbook/install.md` | Установка dev-окружения |
| `docs/runbook/testing.md` | Команды тестов/миграций/проверок |
| `docs/runbook/backup.md` | BackupRun, pg_dump, retention |
| `docs/runbook/restore.md` | restore-check и ограничения полного restore |
| `docs/runbook/incident.md` | Первичная диагностика dev |
| `tests/unit/test_contract_schemas.py` | 10 тестов JSON Schema и DRF permission |
| `BA-FOUNDATION-001_REPORT.md` | Этот отчёт |

Не изменялись: BA-PLAT-4.2, BA-GAME-2.2, `CLAUDE.md`, `README.md`,
`.claude/`, `.env*`, `certs/`, `creds/`, AI Dev, staging/production.

## 6. Архитектурные и инфраструктурные результаты

### 6.1. Сильные стороны

- Разделение портала/CRM/API и игровых origin заложено правильно.
- UUIDv7/citext/pg_trgm/unaccent создаются миграцией `core.0001_extensions`.
- Настройки разделены на base/dev/prod/staging; секреты не хардкодятся.
- i18n имеет строгую обработку `en`, 406/404/503, `Vary`, root redirect.
- BackupRun, pg_dump, sha256, retention и restore-check реализованы и
  проверены в dev.
- healthz/readyz работают; readyz проверяет db/cache/broker/i18n/backup.

### 6.2. Исправленные дефекты

- **API deny-by-default.** `AllowAny` заменён на `IsAuthenticated`; публичные
  endpoint'ы должны явно открываться. API-views сейчас пусты, поэтому
  регрессии нет.
- **nginx healthcheck.** Проверка `nginx -t` заменена на `nc -z` listener;
  контейнер пересоздан, статус healthy.
- **JSON Schema.** Три обязательных контракта этапа 0 заполнены и проверены.
- **Документация.** Заполнены architecture/api и пять foundation-runbooks.

### 6.3. Остающиеся архитектурные ограничения

- `/api/v1/` отсутствует: `config/api.py` и API-views пусты.
- CRM login/dashboard — каркас; 2FA/роли/аудит не реализованы.
- Каталог: публичные detail/leaderboard/play — JSON-заглушки.
- Многие приложения (`gameplay`, `leaderboards`, `ratings`, `pipeline`,
  `moderation`, `analytics`, `content`) — пустые каркасы.
- Полная схема §2.22 не реализована; текущие модели — фундамент/каталог.
- `compose.prod.yml`, `infra/nginx/prod.conf.j2`, `infra/monitoring/*` и
  `infra/scripts/restore.sh` пусты.
- Docker-образы зафиксированы тегами, не digest; базовые Python/Node-образы
  по digest не закреплены.
- `docs/spec/` пуст; README/CLAUDE ссылаются на отсутствующие там
  BA-SDK/BA-ENV. Нормативные копии лежат в `technical_specification/` и
  untracked.
- `schemas/messages/*.json` и `sdk/1.1.0/ba-sdk.js` остаются пустыми по
  причинам из §4.3.

## 7. Тестирование

### 7.1. Выполненные команды

```text
make check
  ruff check: All checks passed
  ruff format --check: 309 files already formatted
  mypy: Success: no issues found in 301 source files
  pytest: 130 passed

manage.py check: System check identified no issues (0 silenced)
makemigrations --check --dry-run: No changes detected
migrate --plan: No planned migration operations
uv lock --check: Resolved 79 packages
docker compose ... config --quiet: OK
```

### 7.2. Инфраструктура

```text
./verify_stack.sh
  web/db/redis-cache/redis-broker: healthy
  https://portal.test:8443/healthz -> 200
  /en/ -> 200
  /crm/ -> 302
  /static/dist/app.css -> 200
  /static/staticfiles.json -> 200
  demo.games.test -> 404 (ожидаемо)

curl /readyz -> 200
checks: backup=ok, broker=ok, cache=ok, db=ok, i18n=ok
```

### 7.3. Backup и restore-check

```text
make backup:
  run=01a1f331-f228-719c-8e57-2f0724db8c72
  size=81414
  sha256=848e8878dcb7ad7bcc436cf5ae6b77a3835283da37db99cdf38bc8c6e31cedba

make restore-check:
  OK verified_at=2026-11-19 09:45:12.612270+00:00
```

`restore-check` создаёт и удаляет только отдельную БД `ba_restore_check`;
основная БД не перезаписывалась.

### 7.4. Покрытие

`pytest --cov=apps --cov-report=term-missing`: **130 passed, total 75%**.
Покрытие неравномерно; пустые модули учитываются как 100% и завышают total.
Примеры: `apps/i18n/services/coverage.py` — 36%, `apps/theme/views.py` — 40%.
E2E/Playwright-набор не реализован.

## 8. Git

### 8.1. До

```text
HEAD: 1fc96b40b6c11b1fcb20e1e5a833a65d166c8340
Tracked modified: 45
Untracked: 34
Staged: 0
```

### 8.2. После

```text
HEAD: 1fc96b40b6c11b1fcb20e1e5a833a65d166c8340
Tracked modified: 57
Untracked: 36
Staged: 0
```

`git add`, commit, reset, clean, checkout, rebase, push не выполнялись.
Исходные пользовательские изменения сохранены. Изменены 12 ранее чистых
tracked-файлов (compose, architecture/api, пять runbooks, три JSON Schema,
`sdk/1.1.0/README.md`); в уже модифицированном до задачи
`config/settings/base.py` изменена только permission-строка. Добавлены два
untracked-файла: отчёт и `tests/unit/test_contract_schemas.py`.

Защищённые файлы не изменялись: `CLAUDE.md`, `README.md`, BA-PLAT-4.2,
BA-GAME-2.2, `.claude/`, `.env*`, `certs/`, `creds/`, AI Dev.
Staging/production не затрагивались.

## 9. Оставшиеся риски

1. **Blocked:** отсутствие BA-SDK-1.1/BA-ENV-1.1 и конфликт `sessionId`/
   `session_id` не позволяют финализировать SDK/message contracts.
2. **Partial:** схема БД не покрывает §2.22/Приложение J; отсутствуют
   модели профилей, сессий, результатов, рекордов, импорта, модерации,
   аналитики и контента.
3. **Partial:** `/api/v1/`, CRM, игровые приложения — каркасы; не считать их
   функциональностью.
4. **Blocked:** production compose/Nginx/monitoring/WAL/PITR/S3 не готовы.
5. **Partial:** Docker-образы не digest-pinned; dependency matrix не
   завершена.
6. **Documentation:** `docs/spec/` пуст, README/CLAUDE содержат устаревшие
   ссылки; `compose.prod.yml`, production Nginx, monitoring и часть runbooks
   пусты.
7. **Residual:** R-003/R-004/R-005/R-006/R-007 из `RISK_REGISTER.md`
   остаются; R-002 требует подтверждения первоисточником; тесты D-006 не
   доказывают rollback/nested atomic/многопоточность/Redis.

## 10. Решения, необходимые от владельца

1. Предоставить `BA-SDK-1.1`/`BA-ENV-1.1` или разрешить отдельный
   утверждённый contract baseline; решить `sessionId`/`session_id`.
2. Выбрать эталонный вариант BA-GAME-2.2 (два варианта не взаимозаменяемы).
3. Определить границу схемы БД этапа 0: только текущий фундамент или полная
   §2.22 с моделями следующих этапов.
4. Разрешить/отклонить фиксацию Docker-образов по digest и определить
   production-конфигурацию.
5. Решить, где хранить канонические ТЗ (`docs/spec/` пуст; копии в
   `technical_specification/` untracked).
6. Утвердить DR-план: S3/WAL/PITR, внешний backup, monitoring.
7. Подтвердить, что deny-by-default DRF и listener-healthcheck nginx
   являются принятыми изменениями фундамента.

## 11. Итоговая рекомендация

**Не готов к формальному закрытию этапа 0.**
**Готов к независимому аудиту как Partial/Blocked-отчёт** с перечнем
блокеров. Формальная приёмка и закрытие этапа 0 остаются за владельцем.

## 12. Утверждения, подтверждённые только анализом кода

Следующие утверждения не проверены работающей системой в полном объёме:

- полнота моделей §2.22/Приложения J — проверена чтением моделей и миграций,
  не ревью полной схемы БД;
- immutability `technical_id`/`host_label`/`GameVersion` — по коду не
  обеспечена; это вывод анализа, не результат атаки/теста;
- отсутствие `/api/v1/` — по пустым views/urls; endpoint'ы не вызывались;
- message schemas и SDK implementation — по пустым файлам/контракту, не по
  работающему SDK;
- Docker digest pinning — по Dockerfile/compose, полный build не выполнялся;
- production/monitoring/WAL/PITR — по пустым файлам/скриптам, production не
  запускался;
- покрытие доменных модулей — по pytest-cov, не по независимому аудиту.
