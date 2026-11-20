# TASK_HISTORY — Breaktime Arcade

**Дата актуализации:** 2026-11-19 (BA-DOC-002).  
Хронология подтверждённых работ и аудитов. Запись не является приёмкой.
Точные даты ранних работ в постоянных файлах не зафиксированы; ниже указано
«дата не зафиксирована», а не выдуманная дата. Статусы: `COMPLETED`,
`ACCEPTED`, `PARTIAL`, `BLOCKED`, `REJECTED`, `NOT_STARTED`, `SUPERSEDED`,
`NOT_ACCEPTED`.

## 1. Записи работ

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
```

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
- `tests/integration/test_catalog_public.py`;
- `reports/BA_AUDIT_20261118_162920.zip` (исторический generated-отчёт).
- **Не найдены:** отдельные первичные отчёты BA-FIX-001 (i18n),
  BA-FIX-002, BA-FIX-003, BA-AUDIT-002, BA-AUDIT-003 и BA-STAGE-1.1;
  `docs/foundation/BA-FOUNDATION-001_REPORT.md`; отчёт независимой проверки
  BA-FOUNDATION-001; отчёт BA-APPF-002 (работа не запускалась).

Исторические отчёты не считать автоматически актуальными; «реализовано»,
«COMPLETED» и «ACCEPTED» — разные статусы.
