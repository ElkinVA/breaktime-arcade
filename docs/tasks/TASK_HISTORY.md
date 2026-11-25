# TASK_HISTORY — Breaktime Arcade

**Дата актуализации:** 2026-11-20 (BA-ZIP-PREFLIGHT-001).
Хронология подтверждённых работ и аудитов. Запись не является приёмкой.
Точные даты ранних работ в постоянных файлах не зафиксированы; ниже указано
«дата не зафиксирована», а не выдуманная дата. Статусы: `COMPLETED`,
`ACCEPTED`, `PARTIAL`, `BLOCKED`, `REJECTED`, `NOT_STARTED`, `SUPERSEDED`,
`NOT_ACCEPTED`.

## 1. Записи работ

### ARCADE-P5-ARCHER-001 — Archer game

- **ID:** ARCADE-P5-ARCHER-001.
- **Назначение:** полноценная 60-секундная аркада «Лучник» и публикация.
- **Результат:** `games-src/archer` v1.3.3; fixed timestep, 4 цели, combo,
  6 языков, SDK, assets, pack.py; live CRM/worker/publish/iframe/result/
  leaderboard/update/rollback; Neon регрессия.
- **Статус:** **IMPLEMENTED / PRO REVIEW ACCEPT**; product/staging/prod —
  owner. Исходный `index4(1).html` отсутствовал.
- **Дата:** 2026-11-23.
- **Отчёт:** `ARCHER_ACCEPTANCE_REPORT.md`, `ARCHER_PROGRESS.md`.
### ARCADE-P4 — operational hardening + Neon Snake

- **ID:** ARCADE-P4 (A1–A6, B).
- **Назначение:** system-wide ZIP quota/retention, sync-wait analysis,
  staging preparation, resilience, review evidence, first real game.
- **Результат:** `0ba8bfe`, `16fb095` (quota/retention), A3/A4/A6 docs,
  Neon Snake `d1ebc41`, catalogue/media/CSP/mobile fixes `5f8bd2b`; live
  CRM→zip-worker→publish→iframe→SDK result/leaderboard; v1.1.0 update and
  rollback. Fresh **966/12**, E2E **18**.
- **Статус:** **IMPLEMENTED / TECHNICAL REVIEW**; product/staging/legal
  owner-level. Hard FS quota/load NOT TESTED.
- **Дата:** 2026-11-22.
- **Отчёт:** `docs/foundation/ARCADE_P4_ACCEPTANCE_REPORT.md`,
  `ARCADE_P4_PROGRESS.md`, `ARCADE_P4_OWNER_ACTION_LIST.md`.

### BA-AUDIT-001 — исходный независимый аудит

- **ID:** BA-AUDIT-001.
- **Назначение:** проверить BA-STAGE-1.1 и checkpoint.
- **Результат:** A-001–A-007: `Content-Language`, Accept-Language, `fields.pyi`,
  внутренний API Django, unknown prefix, fallback без `en`, смешанный diff.
- **Статус:** **COMPLETED** (аудит); привёл к BA-FIX-001; приёмки
  BA-STAGE-1.1 не было.
- **Дата:** не зафиксирована; постоянный отчёт в файлах не найден.
- **Отчёт/источник:** `AUDIT_REGISTER.md`, `TASK_HISTORY.md`; отдельный
  первичный файл отсутствует.
- **Остаток/зависимости:** BA-FIX-001 остаётся открытой; A-007 — процессный
  вопрос.

### BA-STAGE-1.1 — ограниченный срез этапа 1

- **ID:** BA-STAGE-1.1.
- **Назначение:** публичная шестиязычная оболочка, выбор языка, переключатель,
  базовые i18n-маршруты.
- **Результат:** реализация в dev, интеграционные тесты, языковая семантика;
  staging не затрагивался.
- **Статус:** **NOT_ACCEPTED**. Не является самостоятельным нормативным
  этапом; этап 0 не закрыт, этап 1 не завершён.
- **Дата:** не зафиксирована.
- **Отчёт/источник:** код/тесты BA-STAGE-1.1, `PROJECT_STATUS.md`,
  `AUDIT_REGISTER.md`; отдельный итоговый отчёт не найден.
- **Остаток/зависимости:** BA-FIX-001 открыт; AUD3-001/AUD3-002 и R-006/R-007
  закрыты в BA-I18N-002; R-003/R-004/R-005 остаются; приёмка не выполнена.

### BA-FIX-001 — исправления после BA-AUDIT-001

- **ID:** BA-FIX-001.
- **Назначение:** устранить A-001/A-003/A-004, дополнить A-002 и обработать
  A-005/A-006 в утверждённых границах.
- **Результат:** исправлены middleware/`Content-Language` и часть
  Accept-Language; добавлены тесты; согласован stub; внутренний API
  документирован; зафиксированы strict 404 и active `en`.
- **Статус:** **NOT_ACCEPTED** / открыта. A-001/A-003 исправлены;
  A-002/A-005/A-006 обработаны; A-004 — техническое замечание/риск; A-007 —
  процессный вопрос. Формального закрытия владельцем нет.
- **Дата:** не зафиксирована.
- **Отчёт/источник:** `PROJECT_STATUS.md`, `AUDIT_REGISTER.md`,
  `RISK_REGISTER.md`; отдельный отчёт именно об этих i18n-исправлениях не
  найден. `reports/BA_AUDIT_20261118_162920.zip` содержит generated-отчёт
  с заголовком BA-FIX-001 о настройке AI-среды; это **другой артефакт**, его
  нельзя использовать как доказательство i18n-исправлений.
- **Остаток/зависимости:** D-001/D-006 исправлены; R-002 имеет ограниченную
  доказательную базу; R-003/R-004/R-005 остаются; R-006/R-007 и AUD3-001/
  AUD3-002 закрыты технически в BA-I18N-002.

### BA-AUDIT-002 — повторный независимый аудит

- **ID:** BA-AUDIT-002.
- **Назначение:** проверить реализацию после BA-FIX-001 и утверждённых
  решений.
- **Результат:** D-001 (blocking cache/readiness bypass), D-006
  (transaction invalidation), D-002, D-003, D-004/A-007, D-005; на момент
  отчёта BA-FIX-001 не готов к закрытию.
- **Статус:** **COMPLETED** (аудит); BA-FIX-001 остаётся **NOT_ACCEPTED**.
- **Дата:** не зафиксирована.
- **Отчёт/источник:** `AUDIT_REGISTER.md`, `TASK_HISTORY.md`; отдельный
  первичный файл BA-AUDIT-002 не найден.
- **Остаток/зависимости:** D-001/D-006 исправлены последующими работами;
  D-002/D-003/D-004/D-005 и A-007 требуют учёта; R-004/R-005 ограничивают
  доказательную базу.

### BA-FIX-002 — первоначальное исправление R-002

- **ID:** BA-FIX-002.
- **Назначение:** устранить 406 при активном `en`, если кэш активных языков
  не содержал `en` после `QuerySet.update()`/`bulk_update()`.
- **Результат:** helper обновления кэша и regression-тесты; исправление
  оказалось неполным: повторное чтение кэша могло снова вернуть список без
  `en`; инфраструктурные ошибки требовали отдельной обработки.
- **Статус:** **PARTIAL**; R-002 не считать окончательно устранённым только
  этой работой. Формальная приёмка BA-FIX-002 не зафиксирована.
- **Дата:** не зафиксирована.
- **Отчёт/источник:** `PROJECT_STATUS.md`, `TASK_HISTORY.md`,
  `RISK_REGISTER.md`; отдельный первичный отчёт BA-FIX-002 не найден.
- **Остаток/зависимости:** R-002 доработан в BA-FIX-003; R-003 остаётся
  отдельным риском; R-004/R-005 ограничивают доказательства.

### BA-FIX-003 — обработка отказа получения активных языков

- **ID:** BA-FIX-003.
- **Назначение:** доработать R-002: 503 при отсутствии `en` и при ошибках
  cache/DB; не допускать необработанных 500.
- **Результат:** повторная проверка после обновления кэша,
  `MissingFallbackLanguageError`, единая обработка в middleware/root, тесты
  cache/DB/повторного списка.
- **Статус:** **ACCEPTED** с некритичными замечаниями (решение владельца).
  Приёмка BA-STAGE-1.1 из этого не следует.
- **Дата:** не зафиксирована.
- **Отчёт/источник:** `AUDIT_REGISTER.md` (BA-AUDIT-003),
  `OWNER_DECISIONS.md` (OD-STATUS-001), `RISK_REGISTER.md`; отдельный
  первичный отчёт BA-FIX-003 не найден.
- **Остаток/зависимости:** AUD3-001/AUD3-002 и R-006/R-007 закрыты в
  BA-I18N-002; AUD3-003/AUD3-005 и R-004/R-005 остаются; R-003 остаётся.

### BA-AUDIT-003 — проверка BA-FIX-003

- **ID:** BA-AUDIT-003.
- **Назначение:** независимо проверить BA-FIX-003 и отсутствие регрессий.
- **Результат:** AUD3-001 (широкий `except Exception`), AUD3-002
  (`language_url`), AUD3-003 (mock-тесты), AUD3-004 (Git-статус `views.py`),
  AUD3-005 (изоляция); блокирующих замечаний нет.
- **Статус:** **COMPLETED** (аудит); BA-FIX-003 **ACCEPTED** с
  некритичными замечаниями; BA-STAGE-1.1 **NOT_ACCEPTED**.
- **Дата:** не зафиксирована.
- **Отчёт/источник:** `AUDIT_REGISTER.md`; отдельный первичный файл
  BA-AUDIT-003 не найден.
- **Остаток/зависимости:** AUD3-001/AUD3-002 закрыты в BA-I18N-002;
  AUD3-003/AUD3-005 и R-003/R-004/R-005 остаются.

### BA-DOC-AUDIT-001 — инвентаризация документации

- **ID:** BA-DOC-AUDIT-001.
- **Назначение:** проверить сохранение требований, решений, аудитов, рисков и
  статуса в постоянных файлах.
- **Результат:** выявлены отсутствие реестров, пустые `docs/`, untracked
  specs, устаревшие отчёты/инструкции и противоречия.
- **Статус:** **COMPLETED**; инициировал BA-DOC-001.
- **Дата:** не зафиксирована.
- **Отчёт/источник:** `AUDIT_REGISTER.md`.
- **Остаток/зависимости:** документальный контекст митигирован Block 1;
  README/CLAUDE/.claude и AI Dev-статус остаются устаревшими.

### BA-DOC-001 — восстановление постоянного контекста

- **ID:** BA-DOC-001.
- **Назначение:** создать шесть постоянных документов управления.
- **Результат:** созданы документы в `docs/status`, `docs/decisions`,
  `docs/audits`, `docs/risks`, `docs/tasks`, `docs/handoff`; код/тесты/
  конфигурация/CLAUDE/README/.claude/AI Dev не изменялись.
- **Статус:** **COMPLETED**; входит в **ACCEPTED** Documentation Block 1.
- **Дата:** не зафиксирована; документы датированы 2026-11-19.
- **Отчёт/источник:** сами шесть документов; отдельный acceptance-файл не
  найден.
- **Остаток/зависимости:** исправления FIX-01/02/03; техническая приёмка
  этапов не следует.

### BA-DOC-001-FIX-01 — корректировка документации

- **ID:** BA-DOC-001-FIX-01.
- **Назначение:** исправить OD-01–OD-04 в четырёх документах BA-DOC-001.
- **Результат:** разделены решения владельца, нормативные/технические
  требования и ограничения задач; уточнены источники тестов и статус
  BA-FIX-001.
- **Статус:** **COMPLETED**; входит в **ACCEPTED** Documentation Block 1.
- **Дата:** не зафиксирована.
- **Отчёт/источник:** `OWNER_DECISIONS.md`, `PROJECT_STATUS.md`,
  `TASK_HISTORY.md`, `CONTEXT_RECOVERY.md`.
- **Остаток/зависимости:** BA-FIX-001 остаётся открытым; BA-FIX-003 —
  ACCEPTED с замечаниями; BA-STAGE-1.1 — NOT_ACCEPTED.

### BA-DOC-001-FIX-02 — вторая корректировка документации

- **ID:** BA-DOC-001-FIX-02.
- **Назначение:** уточнить R-002/BA-FIX-002, D-001/D-006 и
  OD-HTTP-004.
- **Результат:** BA-FIX-002 обозначен как неполное первоначальное
  исправление; D-001/D-006 уточнены; OD-HTTP-004 перенесён в технические
  замечания.
- **Статус:** **COMPLETED**; входит в **ACCEPTED** Documentation Block 1.
- **Дата:** не зафиксирована.
- **Отчёт/источник:** `PROJECT_STATUS.md`, `TASK_HISTORY.md`,
  `OWNER_DECISIONS.md`.
- **Остаток/зависимости:** R-002 требует ограниченного подтверждения;
  R-003/R-004/R-005 остаются; R-006/R-007 закрыты в BA-I18N-002.

### BA-DOC-001-FIX-03 — заключительная корректировка Block 1

- **ID:** BA-DOC-001-FIX-03.
- **Назначение:** разделить `TECH-HTTP-004`, актуализировать историю FIX-02 и
  порядок BA-AUDIT-002/BA-FIX-002/BA-FIX-003.
- **Результат:** TECH-HTTP-004A/B/C; уточнены PROJECT_STATUS/TASK_HISTORY;
  проведена сквозная проверка шести документов.
- **Статус:** **COMPLETED**; входит в **ACCEPTED** Documentation Block 1.
- **Дата:** не зафиксирована.
- **Отчёт/источник:** `PROJECT_STATUS.md`, `TASK_HISTORY.md`,
  `OWNER_DECISIONS.md`, `AUDIT_REGISTER.md`, `RISK_REGISTER.md`,
  `CONTEXT_RECOVERY.md`.
- **Остаток/зависимости:** Block 1 принят; техническая приёмка этапов не
  следует.

### Documentation Block 1 — BA-DOC-001 + FIX-01/02/03

- **ID:** Documentation Block 1 (сводная запись, не отдельный этап).
- **Назначение:** постоянный контекст управления проектом.
- **Результат:** шесть документов созданы, исправлены и согласованы.
- **Статус:** **ACCEPTED** владельцем (BA-DOC-002 input; решение
  `OD-STATUS-005`). Принятие документации **не** означает принятия этапа 0,
  этапа 1 или BA-STAGE-1.1.
- **Дата:** 2026-11-19 (дата фиксации).
- **Отчёт/источник:** `OWNER_DECISIONS.md`; отдельный подписанный
  acceptance-файл не найден.
- **Остаток/зависимости:** обновлять реестры после значимых работ; README/
  CLAUDE/.claude/ AI Dev остаются устаревшими.

### BA-FOUNDATION-001 — фундамент этапа 0

- **ID:** BA-FOUNDATION-001.
- **Назначение:** инвентаризация и укрепление фундамента этапа 0: архитектура,
  инфраструктура, миграции, тесты, документация, JSON Schema, частичный SDK
  baseline.
- **Результат:** заполнены manifest/catalog/eventLog schemas; DRF
  deny-by-default; nginx listener healthcheck; обновлены architecture/API/
  runbooks; проверены тесты, миграции, dev-стек, backup и restore-check.
- **Статус:** **COMPLETED** (работа выполнена); **не ACCEPTED**. Отчёт
  имеет статус Partial/Blocked: этап 0 не закрыт; независимая проверка
  выявила ограничения; приёмка остаётся владельцу.
- **Дата:** 2026-11-19 (дата отчёта).
- **Отчёт/источник:** `BA-FOUNDATION-001_REPORT.md` в корне. Запрошенный
  `docs/foundation/BA-FOUNDATION-001_REPORT.md` **не найден**; отдельный
  отчёт независимой проверки также не найден.
- **Остаток/зависимости:** BA-SDK/ENV, sessionId conflict, неполные
  message schemas, частичная SQL-схема, production infra, Docker digest,
  `docs/spec` пуст. BA-FOUNDATION-002 продолжает контрактную/проектную часть.

### BA-FOUNDATION-002 — контракты и проектная схема этапа 0

- **ID:** BA-FOUNDATION-002.
- **Назначение:** закрыть контрактные/проектные требования этапа 0 после
  BA-FOUNDATION-001: DRAFT SDK/ENV, sessionId, App F schemas, SQL/ERD, App J,
  digest/CI.
- **Результат:** DRAFT `BA-SDK-1.1`/`BA-ENV-1.1`; внешний `sessionId`/
  внутренний `session_id`; 14 message schemas; semantic validator; SQL/ERD/
  DB_SCHEMA; App J mapping; сравнение BA-GAME; dev-lite digest; CI checks.
- **Статус:** **PARTIAL / BLOCKED**. Этап 0 не закрыт; DRAFT не утверждены;
  независимая проверка не завершена.
- **Дата:** 2026-11-19.
- **Отчёт/источник:** `docs/foundation/BA-FOUNDATION-002_REPORT.md`;
  запрошенный `reports/BA-FOUNDATION-002_REPORT.md` заблокирован guard-хуком.
- **Остаток/зависимости:** оригиналы BA-SDK/ENV, payload-схемы, BA-GAME,
  production infra, base Python/Node digest, SQL design → Django/DB
  implementation.

### BA-AUDIT-APP-F — предыдущий аудит App F

- **ID:** BA-AUDIT-APP-F (идентификатор по имени отчёта; отдельного ID в
  документе нет).
- **Назначение:** проверить фактическую реализацию postMessage, origin/source,
  sessionId/requestId, JSON Schema, rate limit, idempotency, состояния
  сессии, submit/leaderboard/storage и EventLog.
- **Результат:** runtime App F отсутствует. `apps/gameplay`, SDK, host
  protocol, player и iframe-страница пусты/0 байт. Существуют только DRAFT
  schemas, `apps/core/contracts.py` и contract-тесты; сквозной системы нет.
- **Статус:** **COMPLETED** (аудит); вывод — App F не реализован; это не
  приёмка и не создание нового аудита.
- **Дата:** 2026-11-19.
- **Отчёт/источник:** `docs/foundation/BA-AUDIT-APP-F-REPORT.md`.
- **Остаток/зависимости:** origin/source, session/request replay, states,
  rate/size, idempotency, server trust, EventLog, leaderboard/storage,
  browser/E2E не подтверждены; см. `BA-APPF-001`.

### BA-APPF-001 — подготовка проектных решений App F

- **ID:** BA-APPF-001.
- **Назначение:** подготовить целевую архитектуру, протокол, lifecycle,
  результаты/идемпотентность, leaderboard/storage, EventLog, SQL/App J,
  тесты и критерии приёмки App F.
- **Результат:** `docs/foundation/BA-APPF-001_DESIGN_DECISIONS.md`: 45
  решений, 29 Blocker, 17 вопросов владельцу; DRAFT/PREP ONLY, без
  реализации.
- **Статус:** **COMPLETED** (подготовка); **не ACCEPTED**. Ни одно
  `APPF-DEC-*` не является решением владельца.
- **Дата:** 2026-11-19.
- **Отчёт/источник:** `docs/foundation/BA-APPF-001_DESIGN_DECISIONS.md`.
- **Остаток/зависимости:** решения владельца, BA-SDK/ENV, BA-GAME, SQL
  DB-001…DB-008, `myBest`/`autotest:finish`/`ba.fail`/`ba:error`, лимиты,
  EventLog transport, preview subject.

### BA-APPF-002 — реализация App F

- **ID:** BA-APPF-002.
- **Назначение:** реализация App F по утверждённым решениям (в текущей
  истории задания на реализацию не было).
- **Результат:** **не запускалась**; отчёта и кода нет.
- **Статус:** **NOT_STARTED**.
- **Дата:** не применима.
- **Отчёт/источник:** отсутствует; не выдумывать.
- **Остаток/зависимости:** требует утверждения BA-APPF-001, BA-SDK/ENV,
  BA-GAME и SQL-исправлений.

### BA-DOC-002 — актуализация реестров и единого статуса

- **ID:** BA-DOC-002.
- **Назначение:** восстановить хронологию и согласовать шесть документов
  управления после BA-FOUNDATION-002, App F audit и BA-APPF-001.
- **Результат:** обновлены PROJECT_STATUS, TASK_HISTORY, OWNER_DECISIONS,
  AUDIT_REGISTER, RISK_REGISTER, CONTEXT_RECOVERY; код/схемы/ТЗ не менялись.
- **Статус:** **COMPLETED**; **не ACCEPTED**, ожидает проверки владельцем.
- **Дата:** 2026-11-19.
- **Отчёт/источник:** сами шесть документов; отдельного отчёта нет.
- **Остаток/зависимости:** проверка владельцем; решения по §6
  PROJECT_STATUS; BA-APPF-002 не запускать.

### BA-I18N-002 — устойчивость языкового кэша и ошибок i18n

- **ID:** BA-I18N-002.
- **Назначение:** закрыть R-006/R-007 без изменения ТЗ: падение Redis не
  должно ломать публичные страницы, `language_url` не должен отдавать 500,
  а middleware/root не должны маскировать неожиданные ошибки под 503.
- **Результат:** `apps/i18n/services/language_registry.py`; безопасный
  `language_url`; узкие `except LanguageRegistryUnavailable`; regression-тесты
  на cache read/write failure, invalid cache value, registry unavailable и
  сохранение неожиданных ошибок.
- **Статус:** **COMPLETED**; не `ACCEPTED` (техническая приёмка владельцем
  не требуется, но статус не выдаётся за owner acceptance).
- **Дата:** 2026-11-19.
- **Отчёт/источник:** `apps/i18n/services/language_registry.py`,
  `apps/i18n/middleware.py`, `apps/i18n/views.py`,
  `apps/i18n/templatetags/portal_urls.py`,
  `tests/integration/test_language_registry.py`, `tests/integration/test_core.py`;
  `make test` — 147 passed, `make lint`/`make types` — clean.
- **Остаток/зависимости:** R-003 (TTL других языков), R-004/R-005
  (transaction/Redis evidence) остаются; R-002 — ограниченно подтверждён.

### BA-STAGE-1.2-E2E — browser/E2E публичной оболочки

- **ID:** BA-STAGE-1.2-E2E.
- **Назначение:** проверить в реальном браузере то, что integration-тесты
  проверяют через Django Client: шесть языков, root redirect, 404,
  language switcher, 360px и healthz.
- **Результат:** `tests/e2e/test_portal_shell_e2e.py`; 11 E2E passed против
  dev-стека; обычный `make test` по умолчанию skip E2E (147 passed, 1 skipped).
- **Статус:** **IMPLEMENTED / AWAITING INDEPENDENT REVIEW**; не `ACCEPTED`;
  техническая приёмка владельцем не требуется, но статус не выдаётся за неё.
- **Дата:** 2026-11-19.
- **Отчёт/источник:** `tests/e2e/test_portal_shell_e2e.py`; запуск
  `BA_E2E=1 BA_E2E_BASE_URL=https://portal.test:8443 .venv/bin/pytest
  tests/e2e -m e2e`.
- **Остаток/зависимости:** CI не запускает browser E2E; Playwright/браузер
  нужен на агенте. R-003/R-004/R-005 остаются; App F не затронут.

### BA-STAGE-2.1 — регистрация, вход и профиль (§2.10)

- **ID:** BA-STAGE-2.1.
- **Назначение:** реализовать §2.10 BA-PLAT-4.2 — аккаунты, email,
  восстановление, кабинет, удаление и rate limits — в dev, без App F.
- **Результат:** миграция `accounts.0002`; модели `UserProfile`,
  `EmailAddress`, `NicknameHistory`, `NicknameReservation`,
  `AnonymousIdentity`, `AccountToken`, `UserLegalAcceptance`; Argon2id;
  регистрация/вход/выход; email verification (24 ч); password reset
  (30 мин, нейтральный ответ, hash токена); профиль/настройки; смена
  пароля с инвалидацией прочих сессий; экспорт JSON; deletion request/
  cancel с окном 7 дней; Celery-анонимизация; HIBP-hook; rate limits;
  CSRF; safe `next`.
- **Статус:** **PARTIAL**; core реализован и проверен, но приёмка §2.10
  заблокирована отсутствием утверждённых legal texts/versions, моделей
  gameplay/leaderboards для истории/cleanup, email bounce/provider,
  подключения `AnonymousIdentity` к subject-запросам и 2FA персонала
  (2FA выделена в BA-STAGE-2.2).
- **Дата:** 2026-11-19.
- **Отчёт/источник:** `docs/foundation/BA-STAGE-2.1_REPORT.md`;
  `tests/integration/test_accounts.py`; `tests/unit/test_account_services.py`;
  `apps/accounts/**`.
- **Остаток/зависимости:** решения владельца по legal/email; App F для
  subject-запросов и игровых данных; отдельный пакет 2FA/E2E.

### BA-STAGE-2.2 — 2FA персонала

- **ID:** BA-STAGE-2.2.
- **Назначение:** обязательная TOTP 2FA для персонала, recovery-коды,
  двухшаговый вход и защита staff-сессий.
- **Результат:** поля `User.totp_secret`/`totp_last_counter`; модель
  `RecoveryCode`; сервис `two_factor` (TOTP, replay-protection, 10
  одноразовых hash-кодов); `/auth/2fa/`, `/auth/2fa/recovery/`,
  `/auth/2fa/setup/`, `/auth/2fa/disable/`; staff-middleware; уведомление
  на verified email; миграция `accounts.0003`.
- **Статус:** **PARTIAL**; TOTP/enrollment/recovery/disable реализованы и
  покрыты 6 integration tests; не реализованы офлайн-код владельца,
  отдельный журнал входов/SecurityEvent, роли/CRM step-up, browser E2E.
- **Дата:** 2026-11-19.
- **Отчёт/источник:** `docs/foundation/BA-STAGE-2.2_REPORT.md`;
  `tests/integration/test_two_factor.py`; `apps/accounts/services/two_factor.py`.
- **Остаток/зависимости:** решения владельца по офлайн-recovery и журналу;
  CRM/роли; browser E2E.

### BA-STAGE-2.3 — browser E2E аккаунтов

- **ID:** BA-STAGE-2.3.
- **Назначение:** проверить в реальном браузере регистрацию, вход, профиль,
  смену пароля и deletion window; не заменять integration-тесты.
- **Результат:** `tests/e2e/test_accounts_e2e.py`; 2 E2E passed; полный
  E2E-набор — 13 passed (11 shell + 2 account). Сценарии: регистрация →
  профиль → export → logout/login → password change → login с новым
  паролем → deletion request/cancel; отказ формы без согласия.
- **Статус:** **IMPLEMENTED / AWAITING INDEPENDENT REVIEW**; не `ACCEPTED`;
  E2E создаёт уникального dev-пользователя и не удаляет его автоматически.
- **Дата:** 2026-11-19.
- **Отчёт/источник:** `tests/e2e/test_accounts_e2e.py`; запуск
  `BA_E2E=1 BA_E2E_BASE_URL=https://portal.test:8443 .venv/bin/pytest tests/e2e -m e2e`.
- **Остаток/зависимости:** E2E не входит в обычный CI; rate limit 3/day
  требует очистки dev-cache между повторными прогонами; 2FA E2E для staff
  требует создания staff-пользователя.

### BA-STAGE-2.4 — 2FA completion

- **ID:** BA-STAGE-2.4.
- **Назначение:** закрыть доступные без CRM/ролей пробелы 2FA: офлайн-код
  владельца, журнал входов, regeneration recovery-кодов.
- **Результат:** `OwnerRecoveryCode` (superuser, one-time, после
  использования обязателен повторный enrollment); `LoginEvent` без
  plaintext login/IP; события login/2FA/recovery/enable/disable;
  `/auth/2fa/owner-recovery/`, `/auth/2fa/regenerate/`; миграция
  `accounts.0004`.
- **Статус:** **PARTIAL**; 9 2FA integration tests; роли/CRM step-up,
  уведомления о смене ролей, шифрование TOTP-секрета и retention cleanup
  остаются.
- **Дата:** 2026-11-19.
- **Отчёт/источник:** `docs/foundation/BA-STAGE-2.4_REPORT.md`;
  `tests/integration/test_two_factor.py`; `apps/accounts/services/audit.py`.
- **Остаток/зависимости:** CRM/роли; retention 12 мес. для `LoginEvent`;
  encryption decision; E2E staff.

### BA-STAGE-2.5 — account retention cleanup

- **ID:** BA-STAGE-2.5.
- **Назначение:** реализовать доступные сроки §2.22 для аккаунтных
  сущностей без App F.
- **Результат:** Celery Beat `accounts.cleanup_expired_account_records`
  удаляет истёкшие `AnonymousIdentity`/`AccountToken`, `LoginEvent` старше
  365 дней и `NicknameReservation` с истёкшим сроком;
  `NICKNAME_RESERVATION_DAYS=730`; 1 integration test.
- **Статус:** **PARTIAL**; глобальные `SecurityEvent`/`GameStorage`/
  `GameSession`/mail/backup/consent сроки не покрыты.
- **Дата:** 2026-11-19.
- **Отчёт/источник:** `docs/foundation/BA-STAGE-2.5_REPORT.md`;
  `apps/accounts/tasks.py`; `tests/integration/test_account_retention.py`.
- **Остаток/зависимости:** App F/CRM/бэкапы/почтовые логи; retention
  consent и encryption TOTP-секрета.

### BA-QUALITY-001 — coverage и CI-порог

- **ID:** BA-QUALITY-001.
- **Назначение:** измерить coverage доменных модулей, зафиксировать порог
  §2.26 (≥70 %) и выявить пробелы.
- **Результат:** `make coverage`; `[tool.coverage.run]`/`[tool.coverage.report]`
  с `fail_under=70`; фактический общий coverage — **81.65 %** (2594
  statements, 476 missed) при 177 passed, 2 skipped. Низкие модули:
  `hibp.py` 39 %, `health.py` 59 %, `ba_i18n.py` 63 %, `coverage.py` 36 %,
  `theme/views.py` 40 %, `storage.py` 0 %.
- **Статус:** **IMPLEMENTED / AWAITING INDEPENDENT REVIEW**; порог по
  совокупности выполнен, отдельные модули ниже 70 %.
- **Дата:** 2026-11-19.
- **Отчёт/источник:** `docs/foundation/BA-QUALITY-001_REPORT.md`;
  `pyproject.toml`; `Makefile`; `pytest --cov=apps`.
- **Остаток/зависимости:** повысить покрытие `hibp/health/i18n coverage/
  storage/theme views`; CI уже использует `--cov=apps`.

### BA-CATALOG-001 — публичный каталог

- **ID:** BA-CATALOG-001.
- **Назначение:** заменить stub каталога реальным published-only списком,
  фильтрами, поиском и detail на существующих моделях.
- **Результат:** `apps/catalog/services/catalog.py`; list с
  genre/mobile/duration/q/sort; detail по game/translation slug с fallback
  `en`; genre page; HTMX partial; карточки на home; 5 integration tests.
- **Статус:** **PARTIAL**; нет M2M дополнительных жанров/тегов,
  FTS/`pg_trgm`, рейтингов/популярности/голосов, бейджа покрытия и
  play runtime (App F).
- **Дата:** 2026-11-19.
- **Отчёт/источник:** `docs/foundation/BA-CATALOG-001_REPORT.md`;
  `tests/integration/test_catalog_public.py`; `apps/catalog/**`.
- **Остаток/зависимости:** BA-CATALOG-002 (жанры/теги); ratings/App F;
  FTS-конфигурация и индексы.

### BA-CATALOG-002 — дополнительные жанры и теги

- **ID:** BA-CATALOG-002.
- **Назначение:** добавить отсутствующие M2M-связи и фильтры §2.8.
- **Результат:** `GameGenre`/`GameTag` через-модели; `Game.additional_genres`
  и `Game.tags`; фильтры по дополнительному жанру и мультивыбору тегов;
  tag options; миграция `catalog.0003`; 6 integration tests (включая
  published-only).
- **Статус:** **IMPLEMENTED / AWAITING INDEPENDENT REVIEW**; FTS/ratings/
  popularity/play остаются.
- **Дата:** 2026-11-19.
- **Отчёт/источник:** `docs/foundation/BA-CATALOG-002_REPORT.md`;
  `tests/integration/test_catalog_public.py`.
- **Остаток/зависимости:** FTS/`pg_trgm`; ratings/App F; индексы поиска.

### BA-CATALOG-003 — FTS и pg_trgm

- **ID:** BA-CATALOG-003.
- **Назначение:** заменить `icontains` нормативным FTS-поиском с
  конфигурацией языка и триграммной устойчивостью к опечаткам.
- **Результат:** `SearchVector`/`SearchQuery` по name/short_description/
  description, `TrigramSimilarity`, fallback `icontains`; config из
  `Language.fts_config` или `simple`; 7 integration tests.
- **Статус:** **PARTIAL**; `GameTranslation.search_vector` не заполняется,
  GIN по выражению не создан, `unaccent`/ранжирование не применены.
- **Дата:** 2026-11-19.
- **Отчёт/источник:** `docs/foundation/BA-CATALOG-003_REPORT.md`;
  `apps/catalog/services/catalog.py`; `tests/integration/test_catalog_public.py`.
- **Остаток/зависимости:** BA-CATALOG-004 (persisted vector/GIN/unaccent).

### BA-CATALOG-004 — persisted search vector

- **ID:** BA-CATALOG-004.
- **Назначение:** заполнять `GameTranslation.search_vector` и использовать
  существующий GIN-индекс, сохранив query-time fallback.
- **Результат:** post_save signal с SearchVector A/B/C (simple); data-
  migration `catalog.0004_backfill_search_vector`; stored vector + GIN в
  поиске; тест на заполнение.
- **Статус:** **PARTIAL**; нет `unaccent`, `SearchRank`, обновления при
  bulk/import и проверки плана на объёме.
- **Дата:** 2026-11-19.
- **Отчёт/источник:** `docs/foundation/BA-CATALOG-004_REPORT.md`;
  `apps/catalog/signals.py`; `catalog/0004`.
- **Остаток/зависимости:** BA-CATALOG-005 (unaccent/ranking/bulk).

### BA-CATALOG-005 — unaccent, ranking, bulk refresh

- **ID:** BA-CATALOG-005.
- **Назначение:** закрыть диакритику, ранжирование и обновление вектора
  после bulk/import.
- **Результат:** `Unaccent` Func в persisted vector и query; `SearchRank`
  при поиске; Celery Beat `catalog.refresh_catalog_search_vectors`;
  backfill `catalog.0005`; 8 integration tests.
- **Статус:** **IMPLEMENTED / AWAITING INDEPENDENT REVIEW**; benchmark/
  EXPLAIN на объёме и ratings/popularity/play не входят.
- **Дата:** 2026-11-19.
- **Отчёт/источник:** `docs/foundation/BA-CATALOG-005_REPORT.md`;
  `apps/catalog/services/search.py`; `catalog/0005`.
- **Остаток/зависимости:** BA-QUALITY-002 (benchmark); ratings/App F.

## Принятые решения владельца, отражённые в истории

| ID | Решение | Связанная работа |
|---|---|---|
| OD-STATUS-001 | BA-FIX-003 **ACCEPTED** с некритичными замечаниями | BA-FIX-003 |
| OD-STATUS-002 | BA-FIX-001 **NOT_ACCEPTED** / остаётся открытым | BA-FIX-001 |
| OD-STATUS-003 | BA-STAGE-1.1 **NOT_ACCEPTED** | BA-STAGE-1.1 |
| OD-STATUS-005 | Documentation Block 1 **ACCEPTED** | BA-DOC-001 + FIX-01/02/03 |
| OD-FOUND-001 | Внешний `sessionId`, внутренний `session_id` | BA-FOUNDATION-002 |
| OD-FOUND-002 | BA-SDK-1.1/BA-ENV-1.1 подготовлены как DRAFT, не нормативны | BA-FOUNDATION-002 |
| OD-FOUND-003 | Сравнить BA-GAME-2.2 до выбора канонического варианта | BA-FOUNDATION-002 |
| OD-FOUND-004 | Подготовить полную проектную SQL-схему/App J без немедленных Django-моделей | BA-FOUNDATION-002 |
| A.2–A.4 | Accept-Language/fallback `en` и HTTP-семантика `406/503/404` | BA-DOC-001, BA-FIX-003 |

Эти записи являются решениями владельца; `APPF-DEC-*` из BA-APPF-001 к ним
не относятся.

## 2. Исторический артефакт с коллизией имени BA-FIX-001

`reports/BA_AUDIT_20261118_162920.zip` содержит `REPORT.md` с заголовком
`BA AUDIT REPORT — BA-FIX-001` и описывает **настройку project-local
AI-среды**, `.claude/`, report generator и проверку окружения. Это **не**
отчёт о i18n-исправлениях, которые в постоянных реестрах обозначены как
BA-FIX-001. Артефакт сохранён как исторический (`SUPERSEDED` как снимок
состояния), но не используется как доказательство i18n-фиксов, BA-FIX-002/003
или приёмки BA-STAGE-1.1. Отдельный отчёт i18n BA-FIX-001 не найден.

## 3. Хронология

```text
BA-AUDIT-001 (COMPLETED, первичный файл не найден)
  -> BA-STAGE-1.1 (NOT_ACCEPTED)
  -> BA-FIX-001 (NOT_ACCEPTED / открыт)
  -> BA-AUDIT-002 (COMPLETED)
  -> BA-FIX-002 (PARTIAL)
  -> BA-FIX-003 (ACCEPTED с замечаниями)
  -> BA-AUDIT-003 (COMPLETED)
  -> BA-DOC-AUDIT-001 (COMPLETED)
  -> BA-DOC-001 + FIX-01/02/03 (COMPLETED)
  -> Documentation Block 1 (ACCEPTED)
  -> BA-FOUNDATION-001 (COMPLETED, не принят; Partial/Blocked)
  -> BA-FOUNDATION-002 (PARTIAL/BLOCKED)
  -> BA-AUDIT-APP-F (COMPLETED; App F не реализован)
  -> BA-APPF-001 (COMPLETED; PREP, не принят)
  -> BA-APPF-002 (NOT_STARTED)
  -> BA-DOC-002 (COMPLETED; не принят)
  -> BA-I18N-002 (COMPLETED; R-006/R-007 fixed)
  -> BA-STAGE-1.2-E2E (IMPLEMENTED / AWAITING INDEPENDENT REVIEW; 11 E2E passed)
  -> BA-STAGE-2.1 (PARTIAL; core §2.10 implemented; blockers recorded)
  -> BA-STAGE-2.2 (PARTIAL; TOTP 2FA implemented; journal/owner recovery remaining)
  -> BA-STAGE-2.3 (IMPLEMENTED / AWAITING INDEPENDENT REVIEW; 13 E2E passed)
  -> BA-STAGE-2.4 (PARTIAL; owner recovery, LoginEvent, regeneration)
  -> BA-STAGE-2.5 (PARTIAL; account retention cleanup)
  -> BA-QUALITY-001 (IMPLEMENTED / AWAITING INDEPENDENT REVIEW; coverage 81.65 %)
  -> BA-CATALOG-001 (PARTIAL; published list/filters/search/detail)
  -> BA-CATALOG-002 (IMPLEMENTED / AWAITING INDEPENDENT REVIEW; genres/tags M2M)
  -> BA-CATALOG-003 (PARTIAL; FTS/trigram; no persisted vector)
  -> BA-CATALOG-004 (PARTIAL; persisted vector/GIN/backfill)
  -> BA-CATALOG-005 (IMPLEMENTED / AWAITING INDEPENDENT REVIEW; unaccent/rank/bulk)
  -> BA-AUTONOMY-003 (IMPLEMENTED / AWAITING OWNER ACCEPTANCE; AI infrastructure)
```

### BA-AUTONOMY-003 — AI infrastructure

- **ID:** BA-AUTONOMY-003.
- **Назначение:** привести AI-инфраструктуру в рабочее состояние:
  Pro text-only план/review, Flash-исполнение, Bash-guard, изоляция
  `ba`/`ai-dev`, NOW/контекст, исправление указателей.
- **Результат:** `ba-plan`; обновлены skills/agents; `bash_guard.py`;
  `ai-dev/.claude` guard; `docs/handoff/NOW.md`; `CLAUDE.md`/README/
  `CONTEXT_RECOVERY` указывают на `technical_specification/`;
  `ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-v4-pro`; тесты 185 passed,
  2 skipped; lint 333; mypy 316.
- **Модели:** план — `architect`/`deepseek-v4-pro` text-only; реализация —
  Flash; review — `code-reviewer`/`security-auditor`/v4-pro text-only.
- **Статус:** **IMPLEMENTED / AWAITING OWNER ACCEPTANCE**; независимый
  Pro security-review — **accept** (2026-11-20); findings 1–8 исправлены;
  остаточный R-027 принят; приёмка владельцем pending.
- **Отчёт:** `docs/foundation/BA-AUTONOMY-003_REPORT.md`;
  план — `docs/tasks/BA-AUTONOMY-003_PLAN.md`.
- **Остаток/зависимости:** приёмка владельцем.

### APPF-SESSION-001 — серверный session/ticket срез App F

- **ID:** APPF-SESSION-001.
- **Назначение:** `GameSession`, одноразовый launch ticket, активация и
  heartbeat по BA-PLAT-4.2 §2.12.1–2.12.4 / §2.23 без SDK/ENV/BA-GAME.
- **Результат:** модель `GameSession` + миграции 0001/0002; сервисы
  `create_session`/`activate_session`/`heartbeat`; `POST /api/v1/sessions`,
  `/sessions/{id}/activate`, `/sessions/{id}/heartbeat`; CSRF для
  анонимных; throttle по живой guest-identity (IP fallback); лимит ≤3
  активных под advisory-lock при создании и активации; 24 integration
  tests, включая 3 конкурентных.
- **Дополнительно:** исправлен обход лимита активных через активацию и
  дефект миграции свежей БД (`catalog.0001` citext без зависимости от
  `core.0001_extensions`; добавлена только graph-зависимость).
- **Статус:** **ACCEPTED владельцем 2026-11-20** (OD-STATUS-007).
- **Review:** `code-reviewer` и `security-auditor` (deepseek-v4-pro,
  text-only) — **accept** (2026-11-20), после раунда исправлений
  (throttle, конкурентные тесты, None-guard); третий раунд — проверка
  полного текста тестов, accept; evidence —
  `docs/audits/APPF-SESSION-001_REVIEW_EVIDENCE.md`.
- **Дата:** 2026-11-20.
- **Отчёт:** `docs/foundation/APPF-SESSION-001_REPORT.md`; план —
  `docs/tasks/APPF-SESSION-001_PLAN.md`.
- **Остаток/зависимости:** приёмка владельцем; result/leaderboard/storage,
  SDK/iframe, GamePlaytime, preview/autotest и ZIP pipeline вне среза;
  DB-001, BA-SDK-1.1/BA-ENV-1.1, BA-GAME-2.2 остаются.

### APPF-SESSION-002 — throttle hardening

- **ID:** APPF-SESSION-002.
- **Назначение:** привести лимиты к Приложению E и закрыть мульти-identity
  обход после APPF-SESSION-001 (OD-APPF-020…026).
- **Результат:** subject 30/час + IP 600/час (/64), heartbeat 3/мин на
  сессию, structured 429, `ClientIPMiddleware` (XFF только от доверенных
  прокси), отдельный `redis-throttle` (noeviction), fail-open с
  rate-limited логом; +13 тестов.
- **Статус:** **IMPLEMENTED / AWAITING OWNER ACCEPTANCE**; review
  code-reviewer/security-auditor — блокеров нет.
- **Отчёт:** `docs/foundation/APPF-SESSION-002_REPORT.md`.

### APPF-RESULT-001 — результат и таблица рекордов

- **ID:** APPF-RESULT-001.
- **Назначение:** `POST /api/v1/sessions/{id}/result` с `Idempotency-Key`,
  `GameResult` + `LeaderboardEntry`, DB-001/002/003.
- **Результат:** миграции gameplay.0003–0005 (модели, триггеры, PROTECT);
  гость 403 без записи; preview/autotest `is_test` без лидерборда;
  идемпотентность; advisory-lock; 100-параллельный тест; 19 tests.
- **Статус:** **IMPLEMENTED / AWAITING OWNER ACCEPTANCE**; review
  code-reviewer/security-auditor — **accept**, блокеров нет.
- **Отчёт:** `docs/foundation/APPF-RESULT-001_REPORT.md`.

### APPF-LEADERBOARD-001 — публичный API рекордов

- **ID:** APPF-LEADERBOARD-001.
- **Результат:** `GET games/{id}/leaderboard?limit=10|100` и `/me/best`;
  порядок direction → achieved_at → user_id; `me`; published-only;
  read-throttle 120/min; 7 tests.
- **Статус:** **IMPLEMENTED / AWAITING OWNER ACCEPTANCE**; review — accept.
- **Отчёт:** `docs/foundation/APPF-LEADERBOARD-001_REPORT.md`.

### APPF-STORAGE-001 — хранилище игры

- **ID:** APPF-STORAGE-001.
- **Результат:** `GET/PUT games/{id}/storage`, 64 КиБ, revision/If-Match,
  TTL гостя 90 дней, активная сессия обязательна, per-session 60/min,
  DB-008 trigger `pg_column_size`; 12 tests (гонка create, cleanup).
- **Статус:** **IMPLEMENTED / AWAITING OWNER ACCEPTANCE**; review — accept.
- **Отчёт:** `docs/foundation/APPF-STORAGE-001_REPORT.md`.

### APPF-PLAYTIME-001 — подтверждённое игровое время

- **ID:** APPF-PLAYTIME-001.
- **Результат:** `UserGamePlaytime` + зачёт приращения credited_ms в
  heartbeat только для mode=user; гости/preview/autotest исключены;
  удаление при анонимизации; 40 session tests.
- **Статус:** **IMPLEMENTED / AWAITING OWNER ACCEPTANCE**; review — accept.
- **Отчёт:** `docs/foundation/APPF-PLAYTIME-001_REPORT.md`.

### APPF-RATINGS-001 — оценки игр

- **ID:** APPF-RATINGS-001.
- **Результат:** `GameRatingVote`/`GameRatingAggregate`, порог playtime,
  возраст 1 ч, 1/24 ч, 5/30 дней, 20/сутки, транзакционный агрегат,
  публичный summary; 10 tests (включая гонки).
- **Статус:** **IMPLEMENTED / AWAITING OWNER ACCEPTANCE**; review — accept;
  антифрод §2.9.6 — owner-gap.
- **Отчёт:** `docs/foundation/APPF-RATINGS-001_REPORT.md`.

### APPF-POPULARITY-001 — популярность и close

- **ID:** APPF-POPULARITY-001.
- **Результат:** `GamePlayCredit`/`GameDailyStats`, зачёт при завершении
  (≥15 с, mode user/guest, окно 30 мин), `POST /sessions/{id}/close`,
  серверная длительность для гейта; 8 tests.
- **Статус:** **IMPLEMENTED / AWAITING OWNER ACCEPTANCE**; review — accept;
  R-032 (guest identity inflation) — owner-gap.
- **Отчёт:** `docs/foundation/APPF-POPULARITY-001_REPORT.md`.

### BA-ZIP-PREFLIGHT-001 — безопасная metadata-only проверка ZIP

- **ID:** BA-ZIP-PREFLIGHT-001.
- **Результат:** `apps/pipeline/validation/codes.py` (стабильные коды,
  severity, лимиты), `structure.py` (`preflight_zip`), 16 unit tests.
  Проверяются: ZIP ≤25 МБ, распакованный ≤100 МБ, ratio ≤100:1, ≤2000
  файлов, файл ≤20 МБ; абсолютные пути/`..`/backslash/управляющие и
  bidi-символы; NFKC и канонизация путей; symlink/спецфайлы/шифрование;
  подмена размеров local vs central; дубликаты и регистро-коллизии;
  Windows-reserved/trailing dot/space/>255 байт; allowlist расширений;
  `.git`/`.DS_Store`/`__MACOSX`/`node_modules`/`*.map`; SHA-256.
  Распаковка и исполнение не выполняются (тест запрещает `extract`/
  `extractall`).
- **Проверки:** full suite — 297 passed, 2 skipped, 1 warning; ruff check/
  format, mypy — зелёные; code-reviewer/security-auditor — **accept**;
  M-1/M-2/m-1/m-3/m-6 исправлены; остаток O-1…O-5/m-4…m-7 — R-034
  (non-blocking); extraction sandbox — следующая стадия.
- **Статус:** **TECHNICALLY ACCEPTED** (agent, OD-TECH-001); продуктовая
  приёмка — владелец; не зависит от BA-SDK-1.1/BA-ENV-1.1/BA-GAME-2.2.
- **Отчёт:** `docs/foundation/BA-ZIP-PREFLIGHT-001_REPORT.md`.

### BA-ZIP-EXTRACT-001 — безопасная потоковая распаковка ZIP

- **ID:** BA-ZIP-EXTRACT-001.
- **Результат:** `apps/pipeline/services/unpack.py` (`extract_zip`),
  11 unit tests. Повторный preflight; чанки 64 КиБ; независимый счётчик
  фактических байт; лимиты 20 МБ/файл, 100 МБ/итог, 2000 файлов; CRC;
  канонические пути; запрет symlink/спецфайлов; file-vs-dir и prefix-
  конфликты; `O_EXCL|O_NOFOLLOW`; staging 0700; атомарный rename;
  очистка при ошибке. Содержимое не исполняется.
- **Проверки:** full suite — 308 passed, 2 skipped; ruff/mypy — зелёные;
  независимый security-review — **accept** (MINOR-1…6, A/B и nit
  исправлены; R-035 — durability/error taxonomy).
- **Статус:** **TECHNICALLY ACCEPTED** (agent, OD-TECH-001); продуктовая
  приёмка — владелец; OS-level CPU/RAM/time/disk/network sandbox —
  BA-ZIP-WORKER-001.
- **Отчёт:** `docs/foundation/BA-ZIP-EXTRACT-001_REPORT.md`.

### BA-ZIP-WORKER-001 — изолированный extraction worker

- **ID:** BA-ZIP-WORKER-001.
- **Результат:** отдельный Compose-сервис `zip-worker`: сеть `zipnet`
  только с `redis-broker`; prefork 1; `read_only`, cap_drop ALL,
  no-new-privileges, pids 64, mem 512m, cpus 1.0, tmpfs `/tmp` 64m;
  `zip_uploads` ro / `zip_artifacts` rw; source O_NOFOLLOW/O_NONBLOCK +
  fstat + `/proc/self/fd`; per-job flock; statvfs 150 МБ; ATTEMPTS/
  quarantine; CANCEL + `cancel_check`; JSON-аудит; cleanup.
  `unpack.py` — только аддитивный `cancel_check` (default None).
- **Проверки:** 22 new tests; full suite — 330 passed, 2 skipped;
  ruff/mypy — зелёные; `docker compose config` OK; E2E web → uploads →
  zip-worker → artifacts COMPLETED; db/cache/internet из zip-worker
  недоступны; code/security review — **accept**.
- **Остатки:** R-033 (нет жёсткой ФС-квоты; общий брокер), R-035
  (fsync/error taxonomy), R-036 (pre-existing глобальный acks_late),
  R-037 (retention `zip_uploads`); healthcheck под нагрузкой не
  стресс-тестирован; SIGTERM-cancel не реализован.
- **Статус:** **TECHNICALLY ACCEPTED** (agent, OD-TECH-001); продуктовая
  приёмка — владелец.
- **Отчёт:** `docs/foundation/BA-ZIP-WORKER-001_REPORT.md`.

### BA-DEVCONTROL-001 — Telegram Dev Control

- **ID:** BA-DEVCONTROL-001.
- **Результат:** отдельный stdlib-сервис `devcontrol/`: long polling,
  owner-only, `/status` `/report` `/progress` `/next` `/tasks` `/continue`
  `/pause` `/resume` `/stop` `/logs` `/ask`, кнопки; управление одной
  фоновой сессией через `claude --bg`/`agents --json`/`logs`/`stop`;
  state/events/inbox в `~/.local/state/ba-devcontrol`; токен в
  `creds/telegram.env` (0600); узкий permissions, hooks Stop/
  PermissionRequest/SessionEnd; systemd unit.
- **Проверки:** 31 unit tests (fakes) + sandbox runner; full 360/3 skipped; ruff/mypy;
  live `--bg` probe (id/sessionId/state/logs/stop); Stop hook записал
  `turn_done`; sandbox runner real run `test_plural.py` — 7 passed, exit 0,
  no leftovers; code/security review — **ACCEPT**.
- **Статус:** **TECHNICALLY ACCEPTED** (agent, 2026-11-21); live setup —
  токен/live Telegram + opt-in `--enable-autonomous`. Автономный `/continue`
  по умолчанию выключен; тесты — только в sandbox.
- **Отчёт:** `docs/foundation/BA-DEVCONTROL-001_REPORT.md`.

### BA-ZIP-HARDENING-001 (R-035) — durability/error taxonomy/method allowlist

- **ID:** BA-ZIP-HARDENING-001 (R-035).
- **Результат:** `unpack.py` — только stored/deflate (`X_METHOD_UNSUPPORTED`),
  fsync каждого файла и staging/destination dirs, read→`X_ARCHIVE_BAD`,
  write→`X_IO`; `worker.py` — fsync parent dir для COMPLETED/ATTEMPTS,
  audit flush+fsync + job dir; 4 новых теста.
- **Проверки:** 54 ZIP tests; full 369/3 skipped; ruff/mypy; benchmark
  2000 files — 7.7 с (<50 с).
- **Статус:** **TECHNICALLY ACCEPTED** (agent, 2026-11-21); code/security
  review — **ACCEPT**; остаток — directory fsync best-effort.
- **Отчёт:** `docs/foundation/BA-ZIP-HARDENING-001_REPORT.md`.

### BA-QUALITY-002 — search benchmark, GIN и покрытие

- **ID:** BA-QUALITY-002.
- **Результат:** dev-only `catalog_benchmark` (seed/rollback, EXPLAIN/
  ANALYZE, candidate DDL с DROP); существующий GIN `search_vector`
  подтверждён на 10k (FTS 2.4 мс); trigram GIN не выбран, `unaccent` STABLE;
  новый индекс не добавлен. Coverage 90.88 %, ни одного модуля <70 %;
  тесты hibp/health/storage/theme/i18n/pipeline/CRM backup.
- **Проверки:** full 397/3 skipped; ruff/mypy; coverage 90.88 %.
- **Статус:** **TECHNICALLY ACCEPTED** (agent, 2026-11-21); code/security
  review — **ACCEPT**; full OR 10k ~150 мс — residual (продуктовая форма
  запроса).
- **Отчёт:** `docs/foundation/BA-QUALITY-002_REPORT.md`.

### R-036 — анализ глобального `CELERY_TASK_ACKS_LATE`

- **ID:** R-036.
- **Результат:** analysis `docs/foundation/R-036_ACKS_LATE_ANALYSIS.md`:
  проверены Celery 5.7.0 defaults (`acks_late=True`,
  `acks_on_failure_or_timeout=True`, `reject_on_worker_lost=None`),
  `visibility_timeout` 3600, prefork/solo, идемпотентность задач.
  Рекомендация — гибрид F: Phase 1 observability/docstrings/tests без
  изменения поведения; Phase 2 idempotency guards + точечный reject только
  после решения владельца.
- **Статус:** **ANALYSIS COMPLETED; PHASE 1 IMPLEMENTED / TECHNICALLY
  ACCEPTED (agent); AWAITING OWNER DECISION FOR PHASE 2**; поведение
  доставки не изменялось.
- **Отчёт:** `docs/foundation/R-036_ACKS_LATE_ANALYSIS.md`.

### R-036 Phase 1 — delivery observability/docstrings/contract tests

- **ID:** R-036 Phase 1 (non-behavioral).
- **Результат:** `apps/core/celery_observability.py` — события
  `task_received`/`task_failure`/`task_retry`/`worker_process_shutdown`/
  `worker_shutdown` только с безопасными полями; `JsonFormatter` расширен;
  R-036 docstrings у CRM/accounts/catalog/pipeline задач; 5 контрактных
  тестов (матрица acks, поля, fallback `task_name`, JSON, отсутствие args).
  Живая проверка выявила и исправила `Consumer.name`-объект и потерю
  handler после `dictConfig` (fd-2 JSON handler).
- **Проверки:** full **402 passed, 3 skipped**; ruff/format/mypy clean;
  live `crm.backup_status_alert` → `celery.task.received`.
- **Review:** code-reviewer — **ACCEPT**; security-auditor — **ACCEPT**;
  minor (lock attach, partial fd write, string hostname) исправлены,
  отсутствие throttling fd-2 — принято как residual.
- **Статус:** **TECHNICALLY ACCEPTED** (agent); Phase 2 — **AWAITING OWNER
  DECISION**. Поведение доставки не изменялось.
- **Отчёт:** `docs/foundation/R-036_PHASE1_REPORT.md`.

### BA-APPF-002 / DB-001 — tombstone-анонимизация сессий при удалении

- **ID:** BA-APPF-002 / DB-001 (approved OD-DB-001; owner chose tombstone).
- **Результат:** `GameSession.SUBJECT_DELETED`; migration `gameplay.0011`
  расширяет check constraint; `anonymize_user` блокирует все сессии
  пользователя, ставит `subject_type=deleted` и случайный per-session UUID,
  created/active закрывает и очищает ticket/binding; finished/expired
  сохраняют состояние.
- **Проверки:** full **403 passed, 3 skipped**; ruff/format/mypy clean;
  migration applied, `makemigrations --check`/`migrate --plan` clean.
- **Статус:** **TECHNICALLY ACCEPTED** (agent); first review — reject,
  re-review after tombstone/lock — **ACCEPT** (blockers/majors нет);
  retention APPF-OD-030 остаётся.
- **Отчёт:** `docs/foundation/BA-APPF-002_DB001_SESSION_CLEANUP_REPORT.md`.

### BA-APPF-002 / DB-006 — immutable GameVersion

- **ID:** BA-APPF-002 / DB-006 (approved OD-DB-006).
- **Результат:** model `save()` guard + PostgreSQL trigger; content/hash/
  version immutable; `created_by`/`manual_review_by` только unchanged/→NULL;
  `ON DELETE SET NULL` проходит. Migrations `catalog.0006`/`0007`; 14 tests.
- **Проверки:** targeted 16 passed; full **419 passed, 3 skipped**; ruff/
  format/mypy clean; `makemigrations --check`/`migrate --plan` clean.
- **Статус:** **TECHNICALLY ACCEPTED** (agent; code/security review ACCEPT);
  остатки — 0006/0007 intermediate, strict `manual_review_at`, `game`
  CASCADE/DB-004 вне scope.
- **Отчёт:** `docs/foundation/BA-APPF-002_DB006_REPORT.md`.

### BA-APPF-002 / DB-005 + DB-007 — public name и mode↔subject

- **ID:** BA-APPF-002 / DB-005, DB-007 (approved OD-DB-005/007).
- **Результат:** `GameTranslation.name` 128→60 (`catalog.0008`, с precheck);
  `GameSession` CHECK `ck_gameplay_session_mode_subject` user→user,
  guest→anon, preview→user/anon, autotest→user; `deleted` tombstone allowed
  (`gameplay.0012` — единый финальный migration); 14 tests.
- **Проверки:** full **433 passed, 3 skipped**; ruff/format/mypy clean;
  migrations applied/check/plan clean.
- **Статус:** **TECHNICALLY ACCEPTED** (agent; code/security review —
  ACCEPT); остатки — tombstone в aggregates и mode immutability — отдельные
  срезы.
- **Отчёт:** `docs/foundation/BA-APPF-002_DB005_DB007_REPORT.md`.

### BA-APPF-002 / DB-004 + DB-001/DB-007 residuals

- **ID:** BA-APPF-002 / DB-004 + residual fixes.
- **Результат:** `Game` identity immutable после публикации + DELETE trigger;
  `GamePlayCredit` удаляется при удалении аккаунта; `GameSession.mode`
  immutable через model guard и trigger. Migrations `catalog.0009`/`0010`,
  `gameplay.0013`; 7 tests.
- **Проверки:** full **441 passed, 3 skipped**; ruff/format/mypy clean;
  migration checks clean.
- **Статус:** **TECHNICALLY ACCEPTED** (agent; code/security review ACCEPT).
- **Отчёт:** `docs/foundation/BA-APPF-002_DB004_RESIDUALS_REPORT.md`.

### BA-APPF-002 — App F runtime/SDK/player (срез A+B)

- **ID:** BA-APPF-002 runtime first slice.
- **Результат:** официальный `sdk/1.1.0/ba-sdk.js`, host-протокол,
  player host, `game_play` с серверным create+activate, точный runtime
  origin/full `runtime_hash`, CSRF relay, guest normalization, no-store,
  Play/Leaderboard links, eventLog validation, heuristic verifier.
  3 play + 2 leaderboard tests, 4 static SDK checks, 4 JS host tests,
  2 runtime E2E.
- **Проверки:** full **456 passed, 4 skipped**; ruff/format/mypy clean;
  `npm run check:js`/`test:js` clean.
- **Статус:** **IMPLEMENTED / TECHNICAL REVIEW** (code/security review
  incomplete: diff evidence/parentOrigin residual; probe/E2E 2 passed; BA-SDK-1.1 не утверждён).
- **Отчёт:** `docs/foundation/BA-APPF-002_RUNTIME_SDK_REPORT.md`.

### AUTONOMY-AUDIT-2026-11-23 — проверка AI Headquarters

- **ID:** AUTONOMY-AUDIT-2026-11-23.
- **Результат:** фактическая проверка `autonomy/`, `devcontrol/`, state,
  systemd/timers, background sessions и Telegram. A — PASS (код), D —
  PASS (код)/NOT TESTED live; B/C/E — FAIL/NOT TESTED; `.autonomy` и
  user units/timers отсутствуют; Telegram API timeout.
- **Проверки:** autonomy/devcontrol tests **94 passed, 1 skipped**; full
  suite 981/12; `claude agents --json` — только текущая interactive-сессия.
- **Остаток:** `AUTONOMY-CONTINUATION-001` (timer) — **BLOCKED, owner**;
  план `docs/tasks/AUTONOMY-CONTINUATION-001_PLAN.md`. Параллельная
  оркестрация не создавалась.
- **Статус:** **COMPLETED / AUDIT ONLY**; не приёмка AI HQ.

### APPF-RUNTIME-REVIEW-001 — независимое ревью App F Runtime

- **ID:** APPF-RUNTIME-REVIEW-001.
- **Результат:** проверены SDK/host/player/play, sessions/results/verifier/
  storage, leaderboards и негативные сценарии. Исправлены stale-response
  guard, best-effort close старой сессии перед newSession, per-session
  Idempotency-Key, host validation (`safe integer`, duration, eventLog
  null/array, limit 10/100), no-retry activate/close. Добавлены
  `tests/js/player.test.mjs` и negative host tests.
- **Проверки:** targeted pytest 79 passed; `npm test:js` 7 passed;
  `npm run check:js` clean; полный suite — см. отчёт.
- **Review:** code-reviewer и security-auditor (deepseek-v4-pro, text-only)
  — **ACCEPT** после delta; F1/F2/F3/F4/F5/F6 закрыты или residual.
- **Статус:** **IMPLEMENTED / INDEPENDENT REVIEW ACCEPT**; product/staging/
  production — владелец; R-036 Phase 2 не менялся; R-043/44/45 residual.
- **Отчёт:** `docs/foundation/APPF-RUNTIME-REVIEW-001_REPORT.md`.

### BA-TOKEN-OBSERVABILITY-001 — metadata-only учёт invocations

- **ID:** BA-TOKEN-OBSERVABILITY-001.
- **Результат:** `autonomy/observability.py` (InvocationMetrics,
  record/read/summarize), `RunResult` optional invocation/timestamps/
  request_count/num_turns, runner evidence fields, orchestrator `_account`
  append-only `invocations.jsonl`; 8 unit tests.
- **Проверки:** observability 8 passed; autonomy/devcontrol/vps subset
  **100 passed, 1 skipped**; ruff/format/mypy clean; full suite exit 0.
- **Review:** code-reviewer **ACCEPT**; minor fixes (corrupt marker,
  first-wins dedup, request_count_known, zero cost); `propose` concurrent
  append documented as residual.
- **Статус:** **IMPLEMENTED / INDEPENDENT REVIEW ACCEPT**; execution
  behavior не менялся. `request_count` exact provider value недоступен из
  CLI; provider fields reserved.
- **Отчёт:** `docs/audits/BA_TOKEN_OBSERVABILITY_IMPLEMENTATION_REPORT.md`.

## 4. Источники и пробелы

- `PROJECT_STATUS.md`, `OWNER_DECISIONS.md`, `AUDIT_REGISTER.md`,
  `RISK_REGISTER.md`, `CONTEXT_RECOVERY.md`;
- `BA-FOUNDATION-001_REPORT.md` (корень);
- `docs/foundation/BA-FOUNDATION-002_REPORT.md`;
- `docs/foundation/BA-AUDIT-APP-F-REPORT.md`;
- `docs/foundation/BA-APPF-001_DESIGN_DECISIONS.md`;
- `tests/e2e/test_portal_shell_e2e.py`;
- `tests/integration/test_accounts.py`, `tests/unit/test_account_services.py`;
- `docs/foundation/BA-STAGE-2.1_REPORT.md`;
- `docs/foundation/BA-STAGE-2.2_REPORT.md`;
- `tests/integration/test_two_factor.py`;
- `tests/e2e/test_accounts_e2e.py`;
- `docs/foundation/BA-STAGE-2.3_REPORT.md`;
- `docs/foundation/BA-STAGE-2.4_REPORT.md`;
- `docs/foundation/BA-STAGE-2.5_REPORT.md`;
- `tests/integration/test_account_retention.py`;
- `docs/foundation/BA-QUALITY-001_REPORT.md`;
- `docs/foundation/BA-CATALOG-001_REPORT.md`;
- `docs/foundation/BA-CATALOG-002_REPORT.md`;
- `docs/foundation/BA-CATALOG-003_REPORT.md`;
- `docs/foundation/BA-CATALOG-004_REPORT.md`;
- `docs/foundation/BA-CATALOG-005_REPORT.md`;
- `docs/foundation/APPF-SESSION-001_REPORT.md`;
- `docs/foundation/BA-ZIP-PREFLIGHT-001_REPORT.md`;
- `docs/foundation/BA-ZIP-EXTRACT-001_REPORT.md`;
- `docs/foundation/BA-ZIP-WORKER-001_REPORT.md`;
- `docs/foundation/BA-DEVCONTROL-001_REPORT.md`;
- `docs/foundation/BA-ZIP-HARDENING-001_REPORT.md`;
- `docs/foundation/BA-QUALITY-002_REPORT.md`;
- `docs/foundation/R-036_ACKS_LATE_ANALYSIS.md`;
- `docs/foundation/R-036_PHASE1_REPORT.md`;
- `docs/foundation/BA-APPF-002_DB001_SESSION_CLEANUP_REPORT.md`;
- `docs/foundation/BA-APPF-002_DB006_REPORT.md`;
- `docs/foundation/BA-APPF-002_DB005_DB007_REPORT.md`;
- `docs/foundation/BA-APPF-002_DB004_RESIDUALS_REPORT.md`;
- `docs/foundation/BA-APPF-002_RUNTIME_SDK_REPORT.md`;
- `tests/integration/test_game_play.py`;
- `tests/unit/test_sdk_runtime_contract.py`;
- `tests/integration/test_game_identity_immutability.py`;
- `tests/integration/test_game_version_immutability.py`;
- `tests/integration/test_game_session_mode_subject.py`;
- `tests/integration/test_catalog_translation_name.py`;
- `tests/unit/test_celery_delivery_contract.py`;
- `tests/integration/test_catalog_public.py`;
- `tests/integration/test_game_sessions.py`;
- `reports/BA_AUDIT_20261118_162920.zip` (исторический generated-отчёт).
- **Не найдены:** отдельные первичные отчёты BA-FIX-001 (i18n),
  BA-FIX-002, BA-FIX-003, BA-AUDIT-002, BA-AUDIT-003 и BA-STAGE-1.1;
  `docs/foundation/BA-FOUNDATION-001_REPORT.md`; отчёт независимой проверки
  BA-FOUNDATION-001; отчёт BA-APPF-002 (работа не запускалась).

Исторические отчёты не считать автоматически актуальными; «реализовано»,
«COMPLETED» и «ACCEPTED» — разные статусы.

### BA-AUTONOMY-004 — durable AI task control plane

- **Результат:** `autonomy/state.py`, `runner.py`, `orchestrator.py`;
  провайдерные Pro/Flash-вызовы с проверкой `modelUsage`; очередь, attempts,
  dependencies, recovery, COMPLETED-dedup, single-run lock, commit после QA.
- **Live evidence:** Pro Architect session `79aef134...` modelUsage Pro;
  Flash Developer/QA sessions; Pro Reviewer `36f8fac4...` accepted after
  initial reject; task `AUTONOMY-GUARD-TESTS-001` COMPLETED; next task
  `AUTONOMY-CONFIG-CONTRACT-001` claimed automatically.
- **Проверки:** `make check` 670 passed, 4 skipped; autonomy unit tests 13;
  guard tests 193; ruff/format/mypy clean.
- **Статус:** **IMPLEMENTED / TECHNICAL REVIEW**; no game/App F changes.
- **Отчёт:** `docs/foundation/AI_AUTONOMY_AUDIT.md`,
  `docs/foundation/AI_AUTONOMY_EVIDENCE.md`.


### BA-AUTONOMY-005 — bounded AI control-plane hardening package

- **Результат:** пять крупных задач: worktree lifecycle/recovery, hard budgets,
  env isolation, Telegram notifier, VPS transfer package. Все приняты
  независимым Pro review; security task прошёл через reject→fix→accept.
- **Проверки:** final `make check` **720 passed, 11 skipped**; retry limit and
  five-task package cap enforced.
- **Остатки:** OS-sandbox gap R-040; live Telegram/VPS systemd not exercised;
  worktree full-check gap documented.


### ARCADE-RATING-DETAIL-001 / ARCADE-RATING-LIST-001 — Browser Arcade rating summaries

- **Результат:** публичная карточка игры показывает агрегат рейтинга и count;
  каталог показывает compact summary без N+1; zero state явный.
- **Проверки:** полный цикл Flash Developer → Flash QA → Pro Reviewer →
  commit/merge; full **776 passed, 11 skipped**.
- **Коммиты:** `63b6137`, `3c58dcb`.
- **Статус:** **TECHNICALLY ACCEPTED** (agent review); product acceptance owner.


### ARCADE-POPULARITY-001 — catalog popularity

- 30-day popularity read with cache/DB fallback, cards/detail indicator and
  `sort=popular`; Flash Developer → Flash QA → Pro Reviewer → `f211161`.
- Full **776 passed, 11 skipped**.
- Review: accepted; minor: secondary sort should be reconciled with §2.8
  (`WR ↓, id ↑`) and UI strings need i18n. Product follow-up, not infra.


### ARCADE-CATALOG-SORTS-001 / ARCADE-POPULARITY-ORDER-001 / ARCADE-I18N-UI-001

- `ARCADE-CATALOG-SORTS-001` (`3f5b16a`) — Bayesian WR, rating/votes sorts;
  accepted with minor edge-case debt.
- `ARCADE-POPULARITY-ORDER-001` (`670923f`) — exact §2.8 secondary sort
  (`WR ↓, id ↑`); accepted.
- `ARCADE-I18N-UI-001` — initially stopped by the old TOKEN_BUDGET limit;
  owner changed policy on 2026-11-21: token/cost are accounting only and no
  longer stop work. Task resumed under the new policy.
- Full gate **776 passed, 11 skipped**.


### Browser Arcade product wave — home, i18n, profile, locale badge

- `ARCADE-I18N-UI-001` (`0c56116`) — catalog UI localization through
  `ba_t`/TranslationEntry; DE/RU coverage tests; minor plural-form debt remains.
- `ARCADE-HOME-BLOCKS-001` (`f7634b7`) — real Popular/High-rated home blocks.
- `ARCADE-PROFILE-RECORDS-001` (`d330ee0`) — personal records/playtime in profile.
- `ARCADE-LOCALE-BADGE-001` (`d3aa9f9`) — localization coverage badge.
- QA/Pro Reviewer cycles completed; full gate **776 passed, 11 skipped**.
- Token/cost are now analytics only; wall-clock, task cap, retry/fingerprint and
  worktree gates remain.


### ARCADE-SEO-SITEMAP-001 — public SEO surface

- Per-language sitemap index and robots.txt; published games/genres only,
  active-language DB enumeration, localized slugs, tests; Pro Reviewer accept.
- Commit `64f1fd9`; full gate **776 passed, 11 skipped**.


### ARCADE-CATALOG-PAGINATION-001 — public catalog pagination

- 24-card pages, filter/sort-preserving links, canonical, noindex beyond page 5,
  HTMX fragment and constant query count; `824eb28`; Pro Reviewer accept.
- Full gate **776 passed, 11 skipped**.


### ARCADE-CRM-DASHBOARD-001 — CRM operational dashboard

- Replaced the CRM stub with published games, accounts, active-30d, sessions
  today, top-popular games, rating aggregate, new votes and latest backup.
- QA caught a formatting gate; retry fixed it; `4242a98`; full gate
  **776 passed, 11 skipped**.

### BA-PRODUCT-ROADMAP-001 — сверка Browser Arcade с ТЗ

- Проведена сверка кода с BA-PLAT-4.2/BA-GAME-2.2 и реестрами.
- Текущая реализация разделена на A (можно делать), B (внешние решения) и C
  (реализовано, нужна продуктовая приёмка); NOW/PROJECT_STATUS/BACKLOG
  отмечены без изменения требований.
- STOP установлен; новых задач автоматически не запускалось.
- Отчёт: `docs/foundation/BA_PRODUCT_ROADMAP_AUDIT.md`.

### ARCADE-P0/P1/P2 — implementation wave

- `ARCADE-P0-CONTRACT-CLOSURE-001` (`7c56f93`) — ADR-APPF-001: BA-GAME A,
  BA-SDK/ENV, 64 КиБ/strict unknown/`sessionId`, DB-001…008, App F,
  retention, roles/2FA/step-up, email adapter, production requirements.
- `ARCADE-P1-RATINGS-LEADERBOARD-001` (`51a08d0`) — rating UI, TOP-100,
  pagination/current-user row; `ARCADE-P1-SEO-I18N-A11Y-001` (`a167a47`) —
  JSON-LD, CLDR plural, accessibility.
- `ARCADE-P2-PIPELINE-001` (`059b7fa`) — ZIP intake/validation/import,
  SDK runtime bundle/hashes, reports/conflicts, autotest, publish/rollback.
- `ARCADE-P2-CRM-GAMES-001` (`f938315`) — staff login/2FA, inventory,
  card/version history.
- `ARCADE-P2-CRM-WIZARD-001` (`de1c975`) — upload wizard/reports/diff,
  password+TOTP step-up.
- `ARCADE-P2-CRM-ROLES-001` (`6dd54d7`) — TZ roles, least privilege, audit,
  self/last-owner lockout.
- `ARCADE-P2-MODERATION-001` (`03061c0`) — rating hide/restore, complaints,
  aggregate recalc, audit.
- `ARCADE-P2-CONTENT-ANALYTICS-001` (`11c9805`) — translations/content,
  local analytics, safe exports.
- Models: Developer/QA `deepseek-flash[1m]`; Architect/Reviewer
  `deepseek-v4-pro`; QA/Pro review per package; full fresh gate
  **917 passed, 12 skipped**.
- Product acceptance remains owner-level; external actions not performed.

### ARCADE-P3-ZIP-WORKER-INTEGRATION-001 — isolated extraction

- `021a36c` — durable `ZipExtractionJob`, worker-only extraction, source/hash
  verification, no in-process fallback.
- `270f224`, `e9f66e2`, `9017254` — Pro-review findings: abandoned-upload
  cleanup moved to writable default worker, actual-deletion accounting,
  worker mounts preserved, base runtime volume/init for staging/prod.
- Live CRM upload → `ZipExtractionJob completed`, zip-worker log
  `zip.extract`/`zip.complete`, source removed; cleanup task live.
- Full fresh gate **930 passed, 12 skipped**; Browser E2E 18 passed.
- Pro reviewer: **accept** after delta review; product acceptance external
  blockers remain. Staging live runtime NOT TESTED (missing `.env.staging`).

### BA-TOKEN-OBSERVABILITY-002 — invocation lifecycle

- **ID:** BA-TOKEN-OBSERVABILITY-002.
- **Результат:** schema v2 `invocation_started`/`invocation_finished` в
  `.autonomy/invocations.jsonl`; runner — единственный писатель lifecycle;
  `_account` сохраняет success-only state/budget; reconciliation по owner
  pid/PID reuse/boot_id; ручной `python -m autonomy.observability reconcile`;
  unknown usage — `null` + `usage_known=false`.
- **Проверки:** observability **30 passed**; autonomy subset; ruff/format/
  mypy clean; full suite **1019 tests: 1011 passed, 8 skipped, exit 0**. Реальный control
  run: success/timeout/SIGINT/invalid-model/SIGKILL+reconcile, 5 started +
  5 finished, без двойного учёта; API-error usage сохраняется.
- **Review:** `code-reviewer` **ACCEPT** после delta; исправлены by_status
  zeros, abandoned start, SIGINT pre-spawn window, manual CLI, недостающие
  тесты, ERROR_TYPES/reasoning.
- **Остаток:** usage при timeout/cancel/interrupted неизвестен; provider
  request_count/cache/invoice не коррелируются; SIGKILL child; нет ротации.
- **Отчёт:** `docs/audits/BA_TOKEN_OBSERVABILITY_002_IMPLEMENTATION_REPORT.md`.

### BA-TOKEN-EFFICIENCY-OPTIMIZATION-001 — practical context reduction

- **ID:** BA-TOKEN-EFFICIENCY-OPTIMIZATION-001.
- **Результат:** `docs/handoff/ARCHITECT_BRIEF.md`; architect читает brief +
  точечные разделы; context discipline в autonomy developer/QA/reviewer;
  `docs/runbook/ai_session_policy.md` для интерактивных/`--bg` сессий.
- **Измерение:** обязательный bundle 168 145 → 5 011 chars (−97.0 %);
  реальная пара planning calls — input 132 148 → 59 430 (−55.0 %), cost
  1.617336 → 1.205210 USD (−25.5 %), output +48.8 %, num_turns 32→39; оба
  proposal валидны (4/3 задачи). Один запуск на фазу — индикативно.
- **Ограничения:** модели/маршрутизация/budget/stop-политика не менялись;
  интерактивные сессии по-прежнему вне journal.
- **Отчёт:** `docs/audits/BA_TOKEN_EFFICIENCY_OPTIMIZATION_REPORT.md`.


### APPF-RUNTIME-REVIEW-001 delta — stale/idempotency tests

- **Результат:** `tests/js/player_race.test.mjs` — stale submit success/error,
  leaderboard/storage responses после `newSession` не пересекают границу
  сессии; same-session `Idempotency-Key` reuse и fresh key проверены;
  `tests/integration/test_migrations_check.py` — постоянный
  `makemigrations --check` guard.
- **Проверки:** `npm run test:js` 8 entries/0 failed; `npm run check:js`
  clean; migration guard 1 passed; production-код не менялся.
- **Review:** `code-reviewer` ACCEPT после reject-итерации: deferred-ответы
  были raw payload и success-guard'ы не достигались; исправлено
  Response-shaped helper'ом.
- **Остаток:** live browser E2E/staging/prod NOT TESTED; server cross-check
  strictness NOT TESTED.
- **Отчёт:** `docs/foundation/APPF-RUNTIME-REVIEW-001_DELTA_TESTS.md`.

### ARCADE-RETENTION-001 — App F retention cleanup (AI HQ)

- **Результат:** `8e42426`; daily Celery beat: GameSession finished/expired/
  aborted >30d excluding result-linked, GamePlayCredit >90d, GameImportDraft
  >7d, guest GameStorage `expires_at < now`; idempotent per-type counts.
- **Проверки:** 8 integration tests; migration guard; targeted ruff/mypy;
  QA exit 0; independent AI HQ reviewer **accept**; full suite **1028 tests:
  1020 passed, 8 skipped, exit 0**.
- **Процесс:** attempt 1 QA fail (mypy/makemigrations NOT TESTED); добавлены
  host mypy и постоянный `tests/integration/test_migrations_check.py`,
  QA-инструкция обновлена; attempt 2 pass.
- **Остаток:** no indexes on purge timestamps; concurrent result insert →
  ProtectedError/retry; live beat NOT TESTED.
- **Commit:** `8e42426`.


### ARCADE-CATALOG-SLUG-301-001 — slug history + 301 (AI HQ)

- **Результат:** `cf0936c`; `GameSlugHistory` (catalog.0011), запись старого
  slug на save Game/GameTranslation; старый URL → 301 canonical, неизвестный
  → 404; multi-change chain разрешается в текущий slug.
- **Проверки:** 5 slug tests; migration guard; catalog public/SEO 16 tests;
  ruff/mypy clean; full suite **1033 tests: 1025 passed, 8 skipped, exit 0**;
  AI HQ reviewer accept.
- **Стоимость AI HQ (journal):** developer 2.763 + QA 0.723 + reviewer 1.362
  ≈ 4.848 USD (attempt 1).
- **Остаток:** cross-language negative redirect test absent; shared fallback
  constant duplication; concurrent get_or_create race not tested.
- **Commit:** `cf0936c`.


### ARCADE-CRM-SEO-DIAGNOSTICS-001 — CRM SEO diagnostics (AI HQ)

- **Результат:** `f5474d8`; экран `/crm/seo/` + сервис диагностики:
  пустые локализованные описания, дубли title по языкам, missing alt,
  неполное покрытие переводов; per-language summary и ссылки; `GAMES_VIEW`.
- **Проверки:** 11 tests (queries/summary/screen/roles/anonymous); ruff/mypy
  clean; full suite **1044 tests: 1036 passed, 8 skipped, exit 0**;
  AI HQ reviewer accept без findings.
- **Стоимость AI HQ (journal):** $4.075 (developer+QA+reviewer, attempt 1).
- **Остаток:** large-catalog performance NOT TESTED; staging/prod NOT TESTED.
- **Commit:** `f5474d8`.


### ARCADE-SLUG-HISTORY-HARDENING-001 — slug residuals (AI HQ)

- **Результат:** `bf33191`; race-safe `get_or_create` re-fetch; общий
  `apps/catalog/constants.FALLBACK_LANGUAGE_CODE` для slug/SEO;
  cross-language negative test и concurrent-insert test.
- **Проверки:** 7 slug tests + migration guard; ruff/mypy clean; AI HQ
  reviewer accept; full suite **1046 tests: 1038 passed, 8 skipped, exit 0**.
- **Стоимость AI HQ (journal):** $1.702 (developer+QA+reviewer, attempt 1).
- **Остаток:** concurrent test мокает `get_or_create`, реальная DB-гонка
  не воспроизводилась.
- **Commit:** `bf33191`.


### ARCADE-CRM-USERS-001 — CRM customer accounts (AI HQ)

- **Результат:** `4095ed8` + security fixes; `/crm/users/` list/detail,
  search/filters, block/unblock с аудитом, delete по 7-дневному окну с
  confirm, export через `export_account_data`.
- **Security hardening:** customer scope (no staff/owner/tombstone), step-up
  для export/delete (§2.16.1), tombstone guard, current-epoch leaderboard,
  pagination 50, nosniff, CSRF-negative test.
- **Проверки:** 19 targeted tests; ruff/format/mypy clean; AI HQ code review
  accept; security-auditor conditional → delta **resolved**; full suite **1064
tests: 1056 passed, 8 skipped, exit 0**.
- **Остаток:** R-049 block не отзывает game SDK sessions; tombstone хранит
  password hash/TOTP; live HTTP/CSRF not tested.
- **Commits:** `4095ed8` + security fix commit (см. git log).


### ARCADE-CRM-TAXONOMY-001 — CRM genre/tag CRUD (AI HQ)

- **Результат:** `98b848c` + minor fixes; `/crm/genres/`, `/crm/tags/` CRUD,
  translations, delete guards, requires-translation queue, audit;
  `crm.0006` choices-only migration for new audit actions.
- **Проверки:** 9 taxonomy tests; ruff/mypy clean; AI HQ reviewer accept;
  full suite **1072 tests: 1064 passed, 8 skipped, exit 0**.
- **Minors fixed:** queue filter lowercase, genre image cleanup after commit,
  slug format validation.
- **Остаток:** rollback new image upload may orphan file; staging/prod NOT
  TESTED.
- **Commit:** `98b848c` + minor-fix commit.

### ARCADE-CRM-RATINGS-001 — ratings moderation filters (AI HQ)

- **Результат:** `c577416` + minor fixes; фильтры game/value/visibility,
  overall average и per-value distribution, hide/restore/audit сохранены.
- **Проверки:** 25 targeted tests; ruff/mypy clean; AI HQ reviewer accept;
  full suite **1075 tests: 1067 passed, 8 skipped, exit 0**.
- **Minors fixed:** пояснение области действия сводки; убрано silent
  усечение game-фильтра.
- **Остаток:** строки сверх 100 не пагинируются; staging/prod NOT TESTED.
- **Commit:** `c577416` + minor-fix commit.

### ARCADE-R049-SESSION-REVOCATION-001 — block revokes SDK sessions (AI HQ)

- **Результат:** `a9e7d2b`; `toggle_user_active` в существующей atomic-транзакции
  переводит `created`/`active` GameSession пользователя в `aborted`, обнуляет
  `ticket_hash`/`ticket_expires_at`/`binding_nonce_hash`; unblock не
  переиздаёт; audit `user.blocked`/`user.unblocked` не изменён.
- **Проверки:** 17 targeted tests (revocation, SDK activate/heartbeat/submit
  `E_SESSION_EXPIRED`, unblock no-op, concurrent submit race); migration guard;
  ruff clean; mypy — только pre-existing `referencing` stub; AI HQ reviewer
  accept; full suite **1079/1071/8**.
- **Остаток:** inverse ordering (submit до block) намеренно сохраняет finished
  result; узкая гонка create_session (advisory-lock) с revoke-сканом;
  live SDK/staging NOT TESTED.
- **Commit:** `a9e7d2b`.

### ARCADE-R049-TOMBSTONE-CREDENTIALS-001 — tombstone credential cleanup (AI HQ)

- **Результат:** `08ab9c7`; `anonymize_user` удаляет RecoveryCode/
  OwnerRecoveryCode, ставит unusable password, очищает TOTP secret/confirmed/
  counter; export payload не изменён.
- **Проверки:** 18 targeted tests, tombstone auth failures по password/TOTP/
  recovery; DB-001 session tombstone и CRM delete window; migration guard;
  ruff clean; mypy — только pre-existing stub; AI HQ reviewer accept; full
  suite **1079/1071/8**.
- **Остаток:** live HTTP/staging NOT TESTED.
- **Commit:** `08ab9c7`.

### ARCADE-ARTIFACTS-DOWNLOAD-001 — CRM artifact downloads (AI HQ)

- **Результат:** `f8c3a52` + docstring fix `91c9c0f`; staff-only скачивание
  original ZIP, runtime tree как zip, validation/autotest/import reports
  JSON/Markdown; step-up для ZIP/runtime; hash-derived пути, containment/
  symlink guards, attachment/nosniff/no-store.
- **Проверки:** 6 targeted tests (byte-exact ZIP, runtime zip, reports, 404,
  role/step-up, traversal), CRM games/wizard tests; ruff clean; mypy clean для
  нового модуля; AI HQ reviewer accept; full suite **1085/1077/8**.
- **Остаток:** R-050 TOCTOU при write-доступе к artifact root; runtime zip
  bytes не стабильны между деревьями; real nginx/volume E2E NOT TESTED.
- **Commit:** `f8c3a52`, `91c9c0f`.

### ARCADE-CRM-GAME-RECORDS-001 — CRM records/epochs tab (AI HQ)

- **Результат:** `db8a835` + docstring fix `551e73e`; read-only текущая и
  архивные таблицы рекордов в карточке игры (rank, nickname, value,
  achieved_at, trust_level), селектор эпох, пагинация 25, empty state,
  `GAMES_VIEW` guard; порядок/rank — общие с публичным leaderboard.
- **Review:** первая попытка **reject** (blocker): `achieved_at` был ISO-
  строкой, `|date` давал пустую колонку, тест проверял только context;
  retry исправил тип на datetime и добавил HTML-assert.
- **Проверки:** 5 targeted tests; ruff/mypy для изменённых модулей; AI HQ
  reviewer accept; full suite **1090/1082/8**.
- **Остаток:** live browser/staging NOT TESTED; показываются только
  `is_public=True` (осознанно).
- **Commit:** `db8a835`, `551e73e`.

### ARCADE-CATALOG-GENRE-PAGINATION-001 — genre page pagination (AI HQ)

- **Результат:** `0c4e64d`; `genre_detail` использует общий `paginate_games`/
  `pagination_query`/`canonical_url`/`should_noindex`, сохраняет sort/filters
  в ссылках, deep pages `noindex,follow`, single-page без chrome.
- **Проверки:** 5 targeted tests + catalog pagination/public regressions;
  ruff/mypy clean; AI HQ reviewer accept; full suite **1095/1087/8**.
- **Остаток:** live HTTP/nginx/staging NOT TESTED; context-key `games`
  сохранён для обратной совместимости (informational).
- **Commit:** `0c4e64d`.

### ARCADE-APPF-RACE-TESTS-001 — App F race/idempotency tests (AI HQ)

- **Результат:** `7af18bb`, test-only; 8 тестов на параллельные результаты
  (один лучший LeaderboardEntry без дублей), рейтинговые лимиты
  ≤1/24h/≤5/30d + UNIQUE(game,user), storage stale If-Match/ETag и
  конкурентный JSONB, повтор Idempotency-Key.
- **Проверки:** targeted 8/8 на main; ruff clean; миграций нет; AI HQ
  reviewer accept; full suite **1103/1095/8**.
- **Остаток:** service-level scope; HTTP/CSRF/throttle/ETag round-trip
  покрыт существующими integration-тестами; live browser/staging NOT TESTED.
- **Commit:** `7af18bb`.

### ARCADE-SESSION-RACE-001 — create_session race with block/anonymise (AI HQ)

- **Результат:** `2ac43e1`; `create_session` берёт `select_for_update` на User
  и перепроверяет `is_active` внутри транзакции; `anonymize_user` держит тот
  же User row lock. Сессия не создаётся для блокируемого/анонимизируемого
  аккаунта; R-049 закрыт в коде.
- **Review:** первая попытка вернула невалидный JSON (лишняя `]`), control
  plane корректно не принял вердикт; retry — **accept**. Reviewer отметил
  pre-existing lock-order inversion (`create_session` advisory→rows,
  `activate_session` row→advisory) — R-051, не введён этим изменением.
- **Проверки:** 2 concurrency tests (block и anonymise), 19 CRM users tests;
  full suite **1105/1097/8**.
- **Остаток:** R-051; live SDK/staging NOT TESTED.
- **Commit:** `2ac43e1`.

### ARCADE-ARTIFACTS-TOCTOU-001 — artifact download TOCTOU (AI HQ)

- **Результат:** `75d0159`; original ZIP и runtime tree открываются через
  `O_NOFOLLOW` + fstat/inode-проверку, дочерние entries — через `dir_fd`;
  symlink/path swap → `ArtifactUnavailable`; writing/reading из одного
  verified handle.
- **Проверки:** 4 новых TOCTOU-теста + 6 прежних; ruff/mypy; AI HQ reviewer
  accept; full suite **1109/1101/8**.
- **Остаток:** R-050 memory peak (файлы читаются целиком), runtime zip не
  hash-verified, real nginx/volume E2E NOT TESTED.
- **Commit:** `75d0159`.

### ARCADE-RUNTIME-JSONSCHEMA-001 — schema-driven host/SDK validation (AI HQ)

- **Результат:** `855caa1` + tooling fix `3e037c4`; per-message schema-таблицы
  и JSON-Schema-subset валидатор в `host_protocol.js`/`ba-sdk.js`,
  `E_MESSAGE_INVALID` для trusted payload-нарушений, синхронизированные
  vendored SDK; negative JS tests.
- **QA:** первая попытка fail — QA не мог запустить `npm run test:js`
  (tooling allowlist); добавлены `Bash(npm run test:js:*)` для developer/QA
  и тесты allowlist; retry — 19/19 JS tests, reviewer accept.
- **Проверки:** 19 JS tests на main; SDK contract/package tests; full suite
  **1109/1101/8**.
- **Остаток:** R-052 `myBest` mismatch, R-053 ручное зеркалирование схем,
  browser/staging E2E NOT TESTED.
- **Commit:** `855caa1`, `3e037c4`.

### ARCADE-SDK-MYBEST-001 — myBest contract fix (AI HQ)

- **Результат:** `20f379c`; host `bestOnly` отдаёт `{entries,myRank}` по
  `ba_leaderboard_data`, SDK `myBest` извлекает `{value,achievedAt}` из
  единственной entry (null при отсутствии, value=0 корректен); vendored SDK
  синхронизированы.
- **Проверки:** JS **23/23** на main (новые empty/non-empty bestOnly tests);
  full Python suite **1109/1101/8**; reviewer accept.
- **Остаток:** nickname в bestOnly entry = null (schema-legal); browser E2E
  NOT TESTED.
- **Commit:** `20f379c`.

### ARCADE-SESSION-API-CAMELCASE-001 — sessionId create response (AI HQ)

- **Результат:** `16068f4`; POST `/api/v1/sessions` отдаёт exact
  `{sessionId, ticket, expires_at}`; player.js читает только `sessionId`,
  snake_case mocks/assertions удалены; SDK уже camelCase.
- **QA/review:** QA pass после явной фиксации, что probe/Playwright E2E
  недоступен (NOT TESTED); две попытки reviewer вернули невалидный JSON
  (лишняя/пропущенная `]`), prompt ужесточён `3a91997`, задача requeued с
  attempts=0; финальный reviewer — **accept**.
- **Проверки:** JS 23/23; targeted sessions 41/41; full suite **1109/1101/8**.
- **Остаток:** probe/Playwright E2E NOT TESTED; `expires_at` snake_case и
  отсутствие alias — R-054 (осознанно).
- **Commit:** `16068f4`; tooling `3a91997`.

### ARCADE-TEST-DB-SEED-001 — reseed всех i18n seed-миграций

- **Первопричина:** после `django_db(transaction=True)` pytest-django делает
  flush; fixture `tests/conftest.py` восстанавливал только i18n 0002/0003,
  поэтому строки 0004-0012 отсутствовали в reuse-DB прогоне и публичные
  страницы падали (воспроизведено в `test_home_blocks.py`).
- **Результат:** seed-модули собираются динамически из
  `apps/i18n/migrations/[0-9]*_seed_*.py` в порядке миграций; вызывается
  `seed_languages`/`seed_strings`; reseed перед transaction-тестом и после
  teardown. Пустой glob или модуль без известной функции теперь даёт
  RuntimeError (fail-loud), а не тихий no-op.
- **Проверки:** полный suite **1214 tests: 1201 passed, 13 skipped, exit 0**
  на reuse-DB (13:00) без `--create-db`; targeted transaction+home — 4
  passed; ruff/format/mypy clean. Code-reviewer: **ACCEPT**, delta
  **ACCEPT**. Один редкий step-up флейк в moderation наблюдался однократно,
  не воспроизвёлся (10 одиночных, 3 файловых, 2 полных прогона).
- **Остатки:** прерывание сразу после flush до teardown-reseed оставляет
  reuse-DB пустой до следующего transaction-прогона; step-up флейк не
  доказан и не исправлялся; test-only.
- **Модели:** реализация — `deepseek-flash[1m]`; review —
  `code-reviewer` (`deepseek-v4-pro`, text-only).
- **Commit:** `8e5f507`, `995f5d2`.

### ARCADE-RUNTIME-ORPHAN-001 — TTL-очистка runtime без ссылок

- **Первопричина:** опубликованные runtime-каталоги не удалялись никогда;
  неудачные импорты и заменённые версии накапливались на `runtime_data`
  без ссылки `GameVersion`.
- **Результат:** `cleanup_orphan_runtimes` сканирует `<hash>/` и
  `host_label/<hash>/`, пропускает symlink, не-hash имена, каталоги моложе
  `ZIP_RUNTIME_ORPHAN_TTL_SECONDS` (default 24 ч), ошибки stat/rmtree и
  хэши, на которые ссылается `GameVersion`; логирует
  `pipeline.runtime_orphan_removed`. Beat-задача раз в сутки (acks_late,
  reject_on_worker_lost, limits 240/300). Default worker получил rw
  `runtime_data` и `ZIP_PUBLIC_RUNTIME_ROOT=/app/runtime` — без этого
  cleanup был no-op; compose-тест это фиксирует.
- **Проверки:** 4 теста (referenced/expired/fresh/symlink/flat,
  идемпотентность, beat/task, missing/symlink root); полный suite
  **1214 tests: 1201 passed, 13 skipped, exit 0** на свежей БД;
  ruff/format/mypy clean (383). Code-reviewer: **reject → delta accept**.
  Live: worker пересоздан, aged orphan удалён, событие в логе.
- **Остатки:** live beat/staging NOT TESTED; referenced-protection только
  unit-тестами (dev-БД без `GameVersion`); TTL не per-game. §5.5 закрыт.
- **Модели:** реализация — `deepseek-flash[1m]`; review —
  `code-reviewer` (`deepseek-v4-pro`, text-only).
- **Commit:** `34f237f`.

### ARCADE-ZIP-CONCURRENT-IMPORT-001 — гонка импорта одной игры

- **Первопричина:** два одновременных импорта нового `technical_id` оба
  создавали карточку; проигравший получал `IntegrityError`, который
  ошибочно классифицировался как конфликт semver; параллельная публикация
  идентичного runtime могла проиграть rename-гонку и отклонить импорт.
- **Результат:** `_persist` первым делом берёт
  `pg_advisory_xact_lock` по lowercased `technical_id`, затем повторно
  читает `Game` под `select_for_update` и при необходимости усыновляет
  карточку, созданную параллельным импортом (`created`/`updated`
  пересчитываются). `IntegrityError` с constraint
  `catalog_game_technical_id_key` репортится как `V_ID_CONFLICT`, остальные
  — `V_VERSION_DUP`. `store_runtime` при проигранной rename-гонке проверяет
  хэш существующего target и возвращает идентичный бандл, иначе оставляет
  ошибку.
- **Проверки:** реальный двухпоточный импорт (ровно одна Game/Version,
  статусы created+duplicate), spy на вызов lock, adoption-тест,
  constraint-классификация, forced rename-race и tampered-target тесты;
  полный suite **1210 tests: 1197 passed, 13 skipped, exit 0** на свежей
  БД; ruff/format/mypy clean (383). Code-reviewer: **reject → delta
  accept** после добавления реальных race-тестов.
- **Остатки:** orphan runtime закрыт в `ARCADE-RUNTIME-ORPHAN-001`
  (`34f237f`); error-code
  асимметрия rename-ветки (X_ARTIFACT_IO vs UNSAFE/CONFLICT); отчёт может
  содержать I_IMPORT_CREATED после rollback (cosmetic); threaded-тест без
  barrier (совпадает с принятым App F harness); `manifest["id"]` vs get;
  live staging NOT TESTED.
- **Модели:** реализация — `deepseek-flash[1m]`; review —
  `code-reviewer` (`deepseek-v4-pro`, text-only).
- **Commit:** `03aaf0f`.

### ARCADE-ZIP-JOB-REAPER-001 — reaper зависших extraction jobs

- **Первопричина:** падение web/worker оставляло `ZipExtractionJob` в
  RUNNING навсегда: CRM показывал вечный активный импорт, а cleanup
  продолжал защищать его файлы.
- **Результат:** `reap_stale_extraction_jobs` идемпотентно переводит
  RUNNING-задания старше `ZIP_JOB_STALE_SECONDS` (по умолчанию 600 s;
  fallback на `created_at` при пустом `started_at`) в TIMEOUT с
  `X_JOB_STALE`, `finished_at`/`updated_at`; UPDATE защищён
  `status=RUNNING`. Beat-задача `reap_stale_zip_jobs` каждые 5 минут с
  time limits 240/300; позднее завершение web-импорта остаётся
  авторитетным и перезаписывает timeout.
- **Проверки:** 3 reaper tests (stale/recent/exact-TTL/null-started,
  terminal/queued не трогаются, идемпотентность, task body, beat entry);
  полный suite **1203 tests: 1190 passed, 13 skipped, exit 0** на свежей
  БД; ruff/format/mypy clean (383). Code-reviewer: **accept** после delta.
- **Остатки:** beat работает только при включённом profile `beat`
  (операционно); нет CANCEL-маркера (bounded deadline/hard limit/cleanup);
  draft остаётся `uploaded` до 7-дневного purge; инвариант
  `ZIP_JOB_STALE_SECONDS > wait+deadline` не проверяется на старте; запрос
  использует status-индекс (OR не идеален, но RUNNING-набор мал); новый env
  не внесён в BA-ENV (owner-контракт); live beat NOT TESTED.
- **Модели:** реализация — `deepseek-flash[1m]`; review —
  `code-reviewer` (`deepseek-v4-pro`, text-only).
- **Commit:** `1687517`.

### ARCADE-EMAIL-RESET-INVALIDATION-001 — reset-токены при смене email

- **Первопричина:** password-reset токен, выданный на старый адрес, оставался
  действительным после смены/удаления email; confirm не сверял текущий
  адрес с email токена, а неактивный аккаунт мог использовать токен.
- **Результат:** смена email инвалидирует `PASSWORD_RESET` и
  `EMAIL_VERIFY` в той же транзакции, что и запись `EmailAddress`; удаление
  email делает delete+invalidate атомарно. Confirm после consume проверяет,
  что у пользователя есть verified-адрес, совпадающий с email токена
  (casefold), и что аккаунт активен; иначе нейтральный redirect без смены
  пароля. `password_reset_token_valid/user` требуют `is_active`.
- **Проверки:** 25 `test_accounts` (смена/удаление инвалидируют токен,
  старый пароль остаётся; confirm-mismatch с живым токеном; полный reset
  flow); полный suite **1200 tests: 1187 passed, 13 skipped, exit 0** на
  свежей БД; ruff/format/mypy clean (382). Security-auditor: **accept**
  после delta; submission-order race признан линеаризуемым и не
  блокирующим.
- **Остатки:** `ARCADE-EMAIL-RESET-RACE-001` (строгий submission-order
  race; фикс требует единого lock order, риск AB-BA); timing-oracle
  `password_reset_request` (pre-existing); single-address assumption;
  inactive-token остаётся unused и оживает после reactivation (consistent
  runtime gate); live staging NOT TESTED.
- **Модели:** реализация — `deepseek-flash[1m]`; review —
  `security-auditor` (`deepseek-v4-pro`, text-only).
- **Commit:** `26d8075`.

### ARCADE-RESTORE-CHECK-001 — проверка восстановления дампа

- **Первопричина:** restore-check считал только число таблиц в `public` и
  мог объявить SUCCESS для пустого/повреждённого/неполного дампа; SHA-256
  дампа и обязательные таблицы не проверялись.
- **Результат:** отклоняются отсутствующий, пустой (0 байт) и недоступный
  дамп; SHA-256 сверяется с успешным `BackupRun` до любых операций с БД и
  повторно после `pg_restore`; DROP выполняется с `WITH (FORCE)`; после
  restore проверяются непустой `public`, наличие всех `REQUIRED_TABLES`
  (`django_migrations`, accounts/catalog/gameplay/crm core) и непустая
  `django_migrations`. В `BackupRun.meta` сохраняются путь, id полного
  прогона, SHA-256, `table_count`, `required_tables`, `migration_count`;
  нечисловой ответ SQL — ошибка. Pre-flight OSError завершает run как
  failed, а не оставляет RUNNING.
- **Проверки:** 22 unit restore-check (success metadata, default selection,
  missing/mismatched hash, empty dump, missing tables/migrations,
  unparseable SQL, pre-flight OSError, dump changed during restore); полный
  suite **1197 tests: 1184 passed, 13 skipped, exit 0** на свежей БД;
  ruff/format/mypy clean (382). **Реальный restore на dev** с текущим кодом:
  `OK verified_at=2026-11-25 01:42:13`, meta 44 таблицы / 42 миграции /
  10 обязательных, temp DB удалена. Security-auditor: **accept** после
  delta (SHA before/after, OSError, DROP FORCE, runbook).
- **Остатки:** swap A→B→A вокруг pg_restore всё ещё обходит post-hash
  (staff-level FS; закрытие — передать `/proc/self/fd/N`); нет
  advisory-lock между одновременными restore-check (видимый spurious
  failure, не false SUCCESS); проверка структурная, не построчная;
  приложение работает ролью-суперюзером — owner-gated по §5.4; file-level
  noqa S608; staging/production restore NOT TESTED; cron/restore-check
  использует baked image, для нового кода нужен rebuild образа (ops).
- **Модели:** реализация — `deepseek-flash[1m]`; review —
  `security-auditor` (`deepseek-v4-pro`, text-only).
- **Commit:** `cdb567a`.

### ARCADE-CONTENT-LENGTH-001 — malformed Content-Length → 400

- **Первопричина:** `SessionResultView` парсил `CONTENT_LENGTH` через
  незащищённый `int()`, поэтому нечисловое/отрицательное значение давало
  500 вместо клиентской ошибки.
- **Результат:** `_content_length` трактует отсутствующий/пустой заголовок
  как 0, нечисловой/отрицательный — `None` → 400 `E_INVALID_REQUEST`;
  превышение лимита остаётся 413 `E_PAYLOAD_TOO_LARGE`. Except-кортеж
  parenthesized с `# fmt: skip`, чтобы форматтер не переписал его в
  PEP 758-форму.
- **Проверки:** unit-тесты границ (missing/empty/0/MAX/5000 digits,
  non-numeric, negative, oversized 413) + dispatch-level интеграционный
  тест с authenticated/CSRF запросом к реальному result-маршруту;
  полный suite **1188 tests: 1175 passed, 13 skipped, exit 0** на свежей БД;
  ruff/format/mypy clean (382). Code-reviewer: **reject → delta accept**
  (ложная syntax-находка опровергнута, dispatch-тест добавлен).
- **Остатки:** `int()` остаётся лояльным к пробелам/`+`/подчёркиваниям/
  unicode-цифрам (как Django/DRF), не 500; chunked/без Content-Length
  отклоняется DRF (pre-existing); 413 через dispatch не тестировался
  (CSRF парсит body; 413 покрыт view-level).
- **Модели:** реализация — `deepseek-flash[1m]`; review — `code-reviewer`
  (`deepseek-v4-pro`, text-only).
- **Commit:** `ab62a7d`; test-flake fix `116efbd`.

### ARCADE-RATINGS-BLOCK-001 — оценки заблокированных исключаются сразу

- **Первопричина:** агрегаты оценок фильтруют `user__is_active=True` при
  пересчёте, но block/unblock не пересчитывали затронутые игры; голос
  заблокированного оставался в денормализованном агрегате до следующего
  голоса/ночной задачи. `vote()` проверял `is_active` только вне транзакции.
- **Результат:** `recalculate_user_ratings(user)` пересчитывает все игры
  пользователя в детерминированном порядке `game_id` (advisory locks
  берутся по возрастанию, multi-game deadlock исключён); helper вызывается
  при block/unblock, staff activation/deactivation и удалении аккаунта.
  `vote()` внутри транзакции берёт User row lock и повторно проверяет
  `is_active` до advisory lock, поэтому block, закоммиченный после быстрой
  проверки, всё равно отклоняет голос. Голоса остаются в БД и возвращаются
  при unblock.
- **Проверки:** 5 `test_ratings_block` (немедленное исключение/восстановление,
  детерминированный порядок на non-monotonic UUID, stale-active отказ,
  unblock не-голосовавшего, recalculate-фильтр); 30 related CRM/ratings;
  полный suite **1183 tests: 1170 passed, 13 skipped, exit 0** на свежей БД;
  ruff/format/mypy clean (382). Security-auditor: **accept** после delta;
  ordering-тест усилен non-monotonic UUIDv4.
- **Остатки:** thread-based block-vs-vote race test отложен из-за
  `ARCADE-TEST-DB-SEED-001`; ночная задача/backfill для уже существующих
  заблокированных и дрейфа — `ARCADE-RATINGS-NIGHTLY-001`; тяжёлый
  multi-game block делает O(votes) запросов под lock (редкая staff-
  операция); session-domain `activate_session`/`heartbeat` is_active
  остаётся отдельным residual; live staging NOT TESTED.
- **Модели:** реализация — `deepseek-flash[1m]`; review — `security-auditor`
  (`deepseek-v4-pro`, text-only).
- **Commit:** `766029e`.

### ARCADE-CRM-BLOCK-IDEMPOTENT-001 — явные block/unblock

- **Первопричина:** маршруты `/block/` и `/unblock/` вызывали один toggle;
  повторный block разблокировал аккаунт, а устаревшая форма могла изменить
  состояние в противоположную сторону.
- **Результат:** `_set_user_active` под `select_for_update` User выставляет
  запрошенное состояние; повторный block/unblock — no-op (`changed=False`,
  без audit и без повторного отзыва сессий), реальный переход пишет прежний
  `USER_BLOCKED`/`USER_UNBLOCKED` audit, отзывает SDK-сессии/билеты при
  block и сохраняет tombstone/self guards. Detail POST принимает только
  явные `block`/`unblock`/`delete`; маршруты `toggle/` и `toggle-block/`
  удалены.
- **Проверки:** 27 `test_crm_users` (идемпотентность, ровно один audit,
  authentication flip, tombstone, block-vs-submit/anonymise/storage/
  create-session races); полный suite **1178 tests: 1165 passed, 13 skipped,
  exit 0** на свежей БД (прогон занял ~65 мин из-за нагрузки); ruff/format/
  mypy clean (382). Security-auditor **accept**, только informational/minor.
- **Остатки:** оценки заблокированных не исключаются из денормализованного
  агрегата немедленно (только фильтр чтения/ночной пересчёт) — следующая
  задача `ARCADE-RATINGS-BLOCK-001`; no-op block не повторяет revoke
  (теоретическое legacy-окно); `activate_session`/`heartbeat` не
  перепроверяют `is_active` под lock (legacy-окно, отдельный срез);
  сообщение tombstone для block сформулировано как «разблокировать»;
  unblock не входит в 403/CSRF матрицу тестов; step-up не требуется по
  §2.16.1. Live staging NOT TESTED.
- **Модели:** реализация — `deepseek-flash[1m]`; review — `security-auditor`
  (`deepseek-v4-pro`, text-only).
- **Commit:** `88c2a64`.

### ARCADE-ROLLBACK-SAFE-001 — безопасный rollback и история публикаций

- **Первопричина:** `rollback_version` переключал `current_version` на
  произвольную версию и выставлял статус `published`, обходя validation,
  autotest и проверку score rules; история фактических публикаций
  отсутствовала (audit писал только CRM-view).
- **Результат:** `publish_version` и `rollback_version` пишут append-only
  `AdminAuditLog` в той же транзакции, что и переключение, с actor/IP и
  before/after; повторных audit-записей из CRM больше нет. Rollback требует:
  target ранее публиковался (история), validation blockers = 0,
  autotest passed, score direction/schemaVersion совпадают с фактической
  текущей опубликованной версией (manifest, не import-time поля `Game`);
  статус игры — published/hidden/archived, причём статус не меняется
  (hidden/archived не перепубликуются), draft/review отклоняются. Ошибки —
  `V_NOT_PUBLISHED`, `V_GAME_NOT_PUBLISHED`, `V_SCORE_RULES_CHANGED`,
  `V_VALIDATION_BLOCKED`, `V_AUTOTEST_FAILED`.
- **Проверки:** 12 rollback tests (never-published, blockers, autotest,
  score rules включая import-time mutation, hidden/archived, draft/review,
  foreign game, string schemaVersion) + обновлённые CRM audit/step-up тесты;
  полный suite **1177 tests: 1164 passed, 13 skipped, exit 0** на свежей БД;
  ruff/format/mypy clean (382). Security-auditor: **reject → delta accept**;
  ложная syntax-находка (PEP 758) опровергнута `ast.parse` и реальным
  импортом на Python 3.14.10.
- **Остатки:** concurrency publish-vs-rollback test заблокирован
  `ARCADE-TEST-DB-SEED-001` (row locking корректен, static review); аудит
  публикаций до появления CRM-аудита (и dev `probe_seed`) не даёт истории —
  rollback консервативно блокируется; будущий scheduled-publish task обязан
  вызывать `publish_version`; смена score rules требует owner-решения об
  эпохе (сейчас блокируется); live staging NOT TESTED. Один полный прогон
  упал 1165 errors из-за `DuplicateDatabase`/`ObjectInUse` после
  остановленного предыдущего прогона — после очистки сессий gate зелёный.
- **Модели:** реализация — `deepseek-flash[1m]`; review — `security-auditor`
  (`deepseek-v4-pro`, text-only), reject + delta accept.
- **Commit:** `ecfb419`.

### ARCADE-REGISTRATION-LIMITS-001 — device + IP registration limits

- **Первопричина:** регистрация ограничивалась 3/сутки только по IP: это
  блокировало общий NAT/CGNAT и не соответствовало Приложению E (3/сутки на
  устройство + 30/сутки на IP). Проверка не была атомарной на реальном Redis.
- **Результат:** `registration_attempt(device, ip)` резервирует device
  (3/сутки) и IP (30/сутки); device key — хэш CSRF-cookie с fallback
  `nocookie:<normalized IP>`; слоты возвращаются при невалидной форме/ошибке
  сохранения и сохраняются при успехе. IPv6 /64 и IPv4-mapped collapse
  применяются к device/IP ключам.
- **Находка review (блокирующая, исправлена):** throttle-кэш использовал
  pickle-сериализатор django-redis, поэтому INCR на реальном Redis падал в
  неатомарный GET/SET и конкурентный burst превышал IP-лимит. Добавлен
  `SERIALIZER: django_redis.serializers.json.JSONSerializer`; это также
  закрывает real-Redis неатомарность пакета `de08292`. `ConnectionInterrupted`
  включён в fail-closed; добавлен real-Redis тест (29 seed + 20 потоков →
  ровно один allowed) и view-lifecycle тесты reserve/release.
- **Проверки:** 49 targeted (device/IP, IPv6 /64, IPv4-mapped, release/keep,
  fail-closed с реальным типом исключения, real-Redis atomicity); полный
  suite **1166 tests: 1153 passed, 13 skipped, exit 0** на свежей БД;
  ruff/format/mypy clean (382). Security-auditor: **reject → delta accept**.
- **Остатки / owner:** device key через CSRF ротируется при login —
  фактический device-лимит ~1/token-cycle, cookie clearing обходится;
  binding-контроль — атомарный IP 30/сутки. Appendix E требует challenge
  после 3 и жёсткий блок 100 — не реализованы (owner O4), сейчас hard 30;
  denied attempts сохраняют слоты, поэтому burst может временно блокировать
  NAT; release get/decr TOCTOU; production trusted-proxy allowlist;
  signed device cookie требует cookie-policy/legal — **OWNER APPROVAL
  REQUIRED**. Live load/staging NOT TESTED.
- **Модели:** реализация — `deepseek-flash[1m]`; review — `security-auditor`
  (`deepseek-v4-pro`, text-only), reject + delta accept.
- **Commit:** `bbfdcaf`.

### ARCADE-AUTH-THROTTLE-001 — атомарные account limits, fail-closed

- **Первопричина:** счётчики входа/2FA/восстановления жили в общем
  allkeys-lru cache; проверка лимита выполнялась до записи неудачи, поэтому
  параллельные попытки могли превысить лимит; при отказе Redis счётчики
  fail-open. Регистрация ограничивалась только IP, IPv6 не агрегировался.
- **Результат:** счётчики переведены в выделенный `throttle` (noeviction) с
  socket timeouts 1 s. `login_attempt`/`two_factor_attempt` атомарно
  резервируют попытку до Argon2 (5/15 мин, 10/15 мин на аккаунт); успех
  очищает аккаунтный счётчик; IP считает только неудачи (60/15, 30/15).
  Password reset — 3/ч на аккаунт + 20/ч на IP, каждый запрос. Регистрация
  резервирует слот 3/сутки на IP и возвращает его при невалидной форме или
  ошибке сохранения. Auth и complaints fail-closed (нейтральный 503 / 429
  `E_RATE_LIMIT`), публичные игровые лимиты остаются fail-open. IPv6 /64
  вынесен в `apps/core/net.py`; reset-бакет использует `casefold`; неудачный
  owner-recovery пишет `EVENT_2FA_FAILED`.
- **Проверки:** 43 targeted (20-поточный login cap, IPv6 /64, 2FA/reset
  IP-лимиты, release, fail-closed формы/complaints); полный suite
  **1159 tests: 1146 passed, 13 skipped, exit 0** на свежей БД;
  ruff/format/mypy clean (382 файла). Security-auditor: initial **accept**,
  delta **accept**, новых обходов нет.
- **Остатки:** account-lockout DoS — свойство выбранной политики (5 попыток
  могут временно заблокировать известный логин); IP-failure счётчики
  неатомарны (кратковременный overshoot при burst); TTL-repair через
  best-effort delete, без Lua; malformed 2FA не увеличивает IP-failures;
  shared unknown-IP bucket только при misconfigured deployment; device key
  регистрации — `ARCADE-REGISTRATION-LIMITS-001`; challenge O4; live
  Redis/load/staging NOT TESTED.
- **Модели:** реализация — `deepseek-flash[1m]`; review — `security-auditor`
  (`deepseek-v4-pro`, text-only), два прохода.
- **Commit:** `de08292`.

### ARCADE-THROTTLE-001 — отдельные session scopes и IP-лимиты

- **Первопричина:** create, activate и close использовали общий scope
  `sessions` (30/час), поэтому активация и закрытие расходовали лимит
  создания; results не имел вторичного IP-лимита; complaints ограничивались
  20/сутки на субъект, что не соответствовало Приложению E и допускало
  rotation гостевых identity.
- **Результат:** create — `sessions` 30/ч + guest IP 600/ч; activate/close —
  отдельные subject-бакеты 30/ч (ставка Приложения E для создания, 1:1 к
  созданным сессиям); results — subject 60/ч + IP 1200/ч; complaints —
  5/сутки subject + 30/сутки IP. IP-ключи используют `_client_ip` (IPv6 /64
  и IPv4-mapped).
- **Проверки:** 9 targeted (separate buckets в обе стороны, results IP,
  report subject/IP); полный suite **1147 tests: 1134 passed, 13 skipped,
  exit 0** на свежей БД; ruff/format/mypy clean. Security-auditor review
  **accept**, блокирующих замечаний нет.
- **Остатки:** authenticated users освобождены от `sessions_ip`
  (pre-existing, решение владельца/challenge); heartbeat bucket по URL
  session_id (pre-existing, invalid-id flood); reports fail-open при отказе
  throttle-Redis (закрыть в ARCADE-AUTH-THROTTLE-001); нет socket timeouts
  у throttle cache; challenge в Приложении E не реализован (owner O4);
  DRF list-счётчики неатомарны (небольшой overshoot). Live Redis/NAT/staging
  NOT TESTED.
- **Модели:** реализация — `deepseek-flash[1m]`; review — `security-auditor`
  (`deepseek-v4-pro`, text-only).
- **Commit:** `b953419`.

### ARCADE-RESULT-VERIFICATION-001 — missing eventLog/seed quarantine

- **Результат:** при непустом verification profile отсутствие `eventLog`
  (flag `missing_event_log`) или непустого `seed` (`missing_seed`) даёт
  quarantined verdict и исключает LeaderboardEntry; пустой seed больше не
  превращается в seed mismatch, а идёт в quarantine. `_profile` игнорирует
  пустой manifest-profile, не маскируя game-level profile.
- **Проверки:** 25 result tests (missing log/seed, blank seed, valid path);
  полный suite **1144 tests: 1131 passed, 13 skipped, exit 0** на свежей БД;
  ruff/format/mypy clean; security-auditor accept с minor, minor и delta
  (blank seed, empty-profile precedence) подтверждены повторным review.
- **Остаток:** heuristic baseline допускает пустой `events` при совпадающем
  seed; live staging NOT TESTED. Первый reuse-DB прогон дал 20
  translation-seed failures — тестовая БД, не код (см. PROJECT_STATUS §0.37).
- **Модели:** реализация — `deepseek-flash[1m]`; review — `security-auditor`
  (`deepseek-v4-pro`, text-only).
- **Commit:** `1fc0e97`.

### ARCADE-SESSION-LIFECYCLE-001 — abandoned ACTIVE sessions

- **Результат:** `7da168a`; `_is_stale`/`_expire_locked`; lazy expiry in
  create/activate under advisory lock; two-phase session-row locks before
  play-credit; 5-min beat task `expire_stale_sessions`; popularity credit
  idempotent.
- **Проверки:** 46 session tests incl. create-sweep vs beat-task race with
  `credited_ms=20_000`; ruff/mypy clean; reviewer accept after lock-cycle fix;
  full suite **1137/1129/8**.
- **Остаток:** live beat/Redis, staging NOT TESTED; fixed `current` midnight
  bucketing negligible.

### ARCADE-SESSION-PLAY-001 — no session on GET /play

- **Результат:** `35ae98f`; GET renders shell only (CSRF/runtime base, no
  session/`ba_anon`/context/ticket); player.js creates+activates via existing
  API, then creates HostBridge and sets iframe src with `&s=`; create error
  visible in `player-status`; e2e waits for async src.
- **Проверки:** play tests 3/3; JS 31/31; native reviewer reject → e2e fix →
  accept; full suite **1137/1129/8**.
- **Остаток:** real Playwright E2E/staging NOT TESTED.

### ARCADE-SESSION-HEARTBEAT-SUBMIT-001 — final heartbeat

- **Результат:** `f7a3779`; final heartbeat awaited before result; 410
  surfaces immediately; transient failure still attempts result; Idempotency-
  Key unchanged.
- **Проверки:** JS 31/31 incl. transient/expired branches; reviewer accept.

### ARCADE-SESSION-PAGEHIDE-001 — close on pagehide

- **Результат:** pagehide `fetch(..., keepalive:true)` с `X-CSRFToken`;
  sendBeacon оставлен fallback без fetch (form CSRF не принимается close API);
  close идемпотентен.
- **Проверки:** JS 31/31; reviewer delta accept; full suite **1137/1129/8**.
- **Остаток:** browser may kill page without pagehide; live E2E NOT TESTED.
- **Commit:** `cb92702`.

### AI-HQ-CI-001 — CI quality gate restoration

- **Результат:** `a0aa34b`; добавлен `redis-throttle` service и
  `REDIS_THROTTLE_URL`, ruff/mypy охватывают `autonomy/` и `scripts/`,
  FakeRunner возвращает обязательный `self_check`, sandbox-copy тест
  соответствует allowlist, добавлен отдельный diagnostic coverage step с
  `COVERAGE_FILE=.coverage.autonomy`.
- **Проверки:** 38 affected tests; mypy 381 файл; ruff clean; autonomy/
  devcontrol coverage 73 %.
- **Review:** code-reviewer **accept** + delta accept.
- **Остаток:** фактический GitHub Actions run **NOT VERIFIED** — в среде нет
  `gh`/токена; YAML разобран, локальные эквивалентные проверки зелёные.
- **Commit:** `a0aa34b`.

### AI-HQ-A1 — trusted sandbox-only agent checks

- **Результат:** `1f46062`; удалены host pytest/mypy/ruff/npm из allowlist
  developer/QA, оставлены пять точных команд trusted main-checkout
  sandbox runner (без `:*`); `--source-root` принимает только linked
  worktree, привязан к `BA_TASK_WORKTREE`, проверяет `.git`-файл/gitdir;
  JS — node-only read-only sandbox; `_changed_files` берёт коммитимый набор
  из Git; `PROTECTED_PARTS` закрывает контрольную плоскость и host-exec
  поверхности; reviewer лишён Bash.
- **Security review:** три раунда; blocker wildcard-чейнинга, host-exec
  поверхности и SyntaxError устранены; финальный verdict — **accept**.
- **Проверки:** 69 affected tests; JS 26/26; source-root smoke 41/41; full
  suite **1130/1122/8, exit 0**.
- **Остаток:** R-040 (OS-sandbox), полный suite вместо targeted,
  продуктовый `apps/` в web-контейнере, динамическая exact-match семантика
  CLI не проверена.
- **Commit:** `1f46062`.

### AI-HQ-A2 — immutable candidate QA and strict verdicts

- **Результат:** `45a69f1`; candidate commit создаётся до QA и записывается в
  state; QA — в отдельном чистом worktree на точном SHA, без права
  редактирования; reviewer получает полный diff; `_reviewer_verdict`/
  `_qa_passed` строгие (malformed/prose/truncated → reject); коммитимый набор
  из Git, каждый путь через `_safe_file`; merge только после QA pass и
  reviewer accept; все failure-пути удаляют оба worktree.
- **Проверки:** 23 affected tests; QA SHA/clean/separate, malformed reviewer
  never merges; full suite **1132/1124/8**; security-auditor accept.
- **Остаток:** QA/reviewer model trust, очень большой diff может исчерпать
  argv/context (fail-closed), R-040.
- **Commit:** `45a69f1`.

### ARCADE-ARTIFACTS-STREAMING-001 — artifact streaming + ZIP hash (AI HQ)

- **Результат:** `8d22aee` + fixes `167ece6`; original ZIP SHA-256 проверяется
  до отдачи и стримится bounded-chunk из verified fd; runtime zip — temp-file
  spool и FileResponse; corrupted package → 404 без частичного тела; spool
  закрывается на любом исключении; удалён неиспользуемый буферный helper.
- **Проверки:** 13 targeted artifact tests (chunked read, corrupted package,
  spool, symlink/path-swap); ruff/mypy clean; reviewer accept; full suite
  **1112/1104/8**.
- **Остаток:** R-050 double-read in-place swap, runtime zip не hash-verified,
  real nginx/volume E2E NOT TESTED.
- **Commit:** `8d22aee`, `167ece6`.

### ARCADE-RUNTIME-SCHEMA-SINGLE-SOURCE-001 — generated host schemas (AI HQ)

- **Результат:** `f9a75d4` + `d1c4e6f`; host registry генерируется из
  `schemas/messages/*.json` с flatten `$ref`/`allOf`; parity test ловит drift;
  generator падает на неподдерживаемых keywords. DRAFT-схемы уточнены
  (limit enum, maxLength) — R-055.
- **Проверки:** JS 23/23; registry tests 4/4; `generate_host_schemas.py
  --check`; full suite **1113/1105/8**.
- **Остаток:** `npm run build` не вызывает генерацию (drift ловится тестом);
  browser/staging E2E NOT TESTED; R-055 требует contract/owner подтверждения.
- **Commit:** `f9a75d4`, `d1c4e6f`.

### ARCADE-SESSION-LOCK-ORDER-001 — App F User-before-GameSession locks (AI HQ)

- **Результат:** `92ef3b1` + comment fix `f871f06`; `submit_result` и
  `heartbeat` берут User row lock до GameSession, `submit_result` проверяет
  `is_active` под локом; порядок совместим с create_session/anonymize_user.
- **Проверки:** 3 concurrency-теста (submit vs anonymize/block, heartbeat);
  targeted 22/22, race suite 8/8; full suite **1116/1108/8**; reviewer accept.
- **Остаток:** R-056 `put_storage`; live load/staging E2E NOT TESTED.
- **Commit:** `92ef3b1`, `f871f06`.

### ARCADE-CRM-MODERATION-PAGINATION-001 — moderation queues pagination (AI HQ)

- **Результат:** `07a287a` + fix `380cd11`; rating/complaint queues по 50,
  rating summary по полному filtered set, фильтры и обе page-позиции
  сохраняются при пагинации любой очереди.
- **Проверки:** 13 targeted tests (120 votes + 120 complaints, page 2,
  summary complete); ruff clean; reviewer accept; full suite **1117/1109/8**.
- **Остаток:** browser/staging NOT TESTED.
- **Commit:** `07a287a`, `380cd11`.

### ARCADE-STORAGE-LOCK-ORDER-001 — storage write lock order (AI HQ)

- **Результат:** `bcd99a7`; `put_storage` для user subject берёт User row
  lock до storage advisory/row и перепроверяет `is_active`; guest-ветка не
  изменена.
- **Проверки:** 4 parametrized race-теста с anonymize/block; targeted 26/26;
  ruff/mypy целевого модуля; reviewer accept; full suite **1121/1113/8**.
- **Остаток:** live load/staging E2E NOT TESTED.
- **Commit:** `bcd99a7`.

### ARCADE-ARTIFACTS-SINGLE-PASS-001 — single-pass ZIP hash (AI HQ)

- **Результат:** `ee9e9c4`; original ZIP читается один раз в temp spool с
  одновременным SHA-256, отдаётся только проверенный spool; mismatch → 404
  без тела; double-read/in-place-swap устранён.
- **Проверки:** 15 targeted artifact tests (byte-exact, in-place mutation,
  chunked, symlink/path-swap); ruff/mypy clean; reviewer accept; full suite
  **1123/1115/8**.
- **Остаток:** runtime zip не hash-verified; real nginx/volume E2E NOT TESTED.
- **Commit:** `ee9e9c4`.

### ARCADE-RUNTIME-HASH-VERIFY-001 — runtime tree digest (AI HQ)

- **Результат:** `8f9f7ac`; runtime zip собирается verified-descriptor walk с
  per-file SHA-256 по arcname; канонический `runtime_hash_for` digest
  сверяется с `version.runtime_hash` до отдачи; mismatch → 404 без тела.
- **Проверки:** 17 targeted artifact tests (valid + mismatch); ruff/mypy
  clean; reviewer accept без findings; full suite **1125/1117/8**.
- **Остаток:** real nginx/volume E2E и нагрузка больших runtime NOT TESTED.
- **Commit:** `8f9f7ac`.

### ARCADE-SDK-ABORT-PENDING-001 — SDK pending-request abort (AI HQ)

- **Результат:** `ebe7d30` + test cleanup `b34a288`; при `exit()`/`newSession`
  SDK немедленно settle-ит pending-запросы (`E_TIMEOUT`/cancelled), удаляет
  таймеры, игнорирует late responses; newSession не отменяет сам себя.
- **Проверки:** 3 JS-теста; JS **26/26**; SDK contract/package tests; reviewer
  accept; full Python suite **1125/1117/8**.
- **Остаток:** browser/staging E2E NOT TESTED.
- **Commit:** `ebe7d30`, `b34a288`.

### ARCADE-RUNTIME-BUILD-SCHEMAS-001 — BLOCKED

- QA обнаружил blocker: `npm run build` исполняется в Docker assets stage, где
  нет `scripts/`/`schemas/` (исключены `.dockerignore`) и нет python3; вызов
  schema-генерации сломал бы `docker build`.
- Изменение Dockerfile/infra вне согласованного scope. Drift уже ловится
  parity-тестом `tests/unit/test_host_schemas_registry.py` и
  `npm run check:schemas`; задача остановлена без merge.
