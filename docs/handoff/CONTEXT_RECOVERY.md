# CONTEXT_RECOVERY — Breaktime Arcade

Краткая инструкция для нового сеанса Claude Code после `/compact` или потери истории чата. Не полагаться на память предыдущей сессии, старые отчёты или сообщения исполнителя как на доказательство.
**Дата актуализации:** 2026-11-20 (BA-ZIP-WORKER-001).
**Первый документ новой сессии — `NOW.md`; полные реестры — по необходимости.**

**Реестры — рабочий источник проектного контекста, но не нормативная база.**
Нормативные требования определяются только утверждёнными ТЗ и решениями
владельца; отчёт агента, независимый аудит и приёмка владельцем — разные
источники.

С BA-AUTONOMOUS-001 действует режим автономной разработки: технические
решения категории C принимаются агентом; к владельцу обращаться только за
решениями категории D (нормативные/продуктовые/необратимые/безопасность/
расходы/production). После завершения пакета продолжать следующий
незаблокированный пакет по `docs/status/BACKLOG.md` без ожидания команды.

## 0. Обязательные правила продолжения

1. Перед новой задачей прочитать `docs/status/PROJECT_STATUS.md`.
2. Проверить `docs/tasks/TASK_HISTORY.md`: возможно, работа уже выполнена.
3. Проверить `docs/decisions/OWNER_DECISIONS.md` до вопросов, которые уже
   решены владельцем.
4. Проверить `docs/audits/AUDIT_REGISTER.md` до постановки нового аудита.
5. Проверить `docs/risks/RISK_REGISTER.md` до повторного исследования
   известного дефекта.
6. Не запрашивать повторно файлы, уже доступные в проекте или истории.
7. Не повторять завершённые аудиты без конкретной причины и ссылки на
   существующий отчёт.
8. Каждое новое задание должно ссылаться на предыдущую связанную работу.
9. После выполнения задачи обновлять шесть реестров и
   `PROJECT_STATUS.md`.
10. Различать отчёт агента, независимую проверку и приёмку владельцем; не
    выдавать одно за другое.

## 1. Что определяет требуемое поведение

1. **Нормативные технические задания.** BA-PLAT-4.2, BA-GAME-2.2 и совместимые с ними документы. Нормативные ТЗ имеют приоритет для требований.
2. **Явно утверждённые решения владельца.** Только раздел **A** в `docs/decisions/OWNER_DECISIONS.md`. Решения владельца не выводятся из кода, отчётов исполнителя или рекомендаций аудиторов.
3. **Согласованные изменения требований.** Только если они документально подтверждены отдельной записью/решением. В текущих постоянных файлах отдельного реестра таких изменений нет; при отсутствии документа изменение не считается требованием.

## 2. Что определяет фактическое состояние

- **Текущий исходный код и конфигурация** — показывают, что фактически реализовано.
- **Результаты фактически выполненных проверок** — с указанием команды, даты и лога; без лога результат считается заявленным, а не доказанным.
- **Независимые аудиты** — `docs/audits/AUDIT_REGISTER.md`; аудит не является приёмкой этапа.
- **Отчёты исполнителя** — исторические и технические свидетельства, но не независимое подтверждение.
- **Исторические handoff-документы** — контекст прошлых работ, требующий проверки актуальности.

## 3. Правила сопоставления источников

- Код показывает, что реализовано, но **не отменяет нормативные требования**.
- Отчёт исполнителя **не равнозначен независимому аудиту**.
- Handoff-документы являются историческими источниками и **требуют проверки актуальности**.
- При противоречии между требованием и реализацией необходимо **фиксировать расхождение**, а не считать реализацию новым требованием.
- Нельзя выводить требование из фактического поведения только потому, что оно уже реализовано.
- Нельзя выдавать прохождение тестов, generated-отчёт или заявление исполнителя за приёмку.

## 4. Практический порядок чтения

0. `docs/handoff/NOW.md` — текущий пакет, статус, следующий шаг, блокеры и последние фактические проверки.
1. `docs/status/PROJECT_STATUS.md` — фактический этап, статусы, ограничения и следующий допустимый шаг.
2. `docs/decisions/OWNER_DECISIONS.md` — раздел A: решения владельца; разделы B/C: нормативные/технические требования и ограничения задач.
3. `docs/audits/AUDIT_REGISTER.md` — аудиты, замечания и их статусы.
4. `docs/risks/RISK_REGISTER.md` — открытые и принятые риски.
5. `docs/tasks/TASK_HISTORY.md` — история задач и связь с документами.
6. `CLAUDE.md` — правила проекта, стек, запреты и процесс.
7. Нормативные ТЗ: `technical_specification/ts_site.txt` (BA-PLAT-4.2 + BA-GAME-2.2) и `technical_specification/ts_game.txt` (BA-GAME-2.2).
8. `../ai-dev/docs/project-reference/README.md` — provenance, SHA-256, различия и пробелы ТЗ (read-only sibling).
9. `git status --short`, `git branch --show-current`, `git rev-parse HEAD` — фактическое рабочее состояние.

Если `PROJECT_STATUS.md` или `OWNER_DECISIONS.md` отсутствуют, противоречат ТЗ или друг другу — **остановиться и запросить решение владельца**. Не восстанавливать контекст догадками.

## 5. Что важно знать сразу

- BA — портал коротких браузерных мини-игр с отдельными origin игр, SDK как единственным каналом связи и статическим runtime bundle.
- Нормативная база: BA-PLAT-4.2 и BA-GAME-2.2. **BA-SDK-1.1 и BA-ENV-1.1 отсутствуют**; их содержание нельзя придумывать или заменять предположениями.
- BA-GAME-2.2 существует в двух вариантах; эталонный вариант **не выбран**. Не выбирать его самостоятельно.
- Этап 0 формально не закрыт; этап 1 не завершён.
- BA-STAGE-1.1 — ограниченный срез этапа 1, **NOT_ACCEPTED**.
- BA-FIX-001 — **NOT_ACCEPTED / открыт**; BA-FIX-002 — **PARTIAL**;
  BA-FIX-003 — **ACCEPTED** с некритичными замечаниями.
- **Documentation Block 1** (BA-DOC-001 + FIX-01/02/03) — **ACCEPTED**;
  это не принятие этапа 0/1, BA-STAGE-1.1 или App F.
- BA-FOUNDATION-001 — **COMPLETED**, не принят; отчёт Partial/Blocked;
  ограничения и блокеры не устранены.
- BA-FOUNDATION-002 — **PARTIAL / BLOCKED**; DRAFT SDK/ENV, схемы и SQL
  design не являются утверждённым контрактом.
- BA-I18N-002 — **COMPLETED**; R-006/R-007 закрыты, 147 tests; R-003/
  R-004/R-005 остаются.
- BA-STAGE-1.2-E2E — **IMPLEMENTED / AWAITING INDEPENDENT REVIEW**;
  11 browser/E2E passed; обычный suite skip E2E.
- BA-STAGE-2.1 — **PARTIAL**: регистрация/вход/профиль §2.10, email,
  password reset, export, deletion window и Celery-анонимизация
  реализованы и покрыты тестами; legal texts/versions, game history/
  records, bounce/provider и subject-подключение `AnonymousIdentity`
  остаются.
- BA-STAGE-2.2 — **PARTIAL**: обязательный TOTP для staff, 10 recovery-
  кодов, replay-protection, disable через password+TOTP, staff-middleware
  и email notice реализованы (6 tests); owner offline recovery, журнал/
  SecurityEvent и роли/CRM step-up остаются.
- BA-STAGE-2.3 — **IMPLEMENTED / AWAITING INDEPENDENT REVIEW**: 2 account
  E2E, полный набор 13 E2E passed; это не приёмка.
- BA-STAGE-2.4 — **PARTIAL**: owner offline recovery, `LoginEvent`,
  regeneration recovery-кодов; роли/CRM step-up и encryption остаются.
- BA-STAGE-2.5 — **PARTIAL**: Celery cleanup для expired гостей/токенов,
  `LoginEvent` >365 дней и nickname-резервов; глобальные сроки §2.22 не
  покрыты.
- BA-QUALITY-001 — **IMPLEMENTED / AWAITING INDEPENDENT REVIEW**: coverage
  81.65 % при пороге 70 %, `make coverage`; отдельные модули ниже 70 %.
- BA-CATALOG-001 — **PARTIAL**: published-only list, фильтры, поиск,
  detail/genre/HTMX.
- BA-CATALOG-002 — **IMPLEMENTED / AWAITING INDEPENDENT REVIEW**: M2M
  `GameGenre`/`GameTag` и фильтры.
- BA-CATALOG-003 — **PARTIAL**: query-time FTS/trigram.
- BA-CATALOG-004 — **PARTIAL**: persisted vector/backfill/GIN.
- BA-CATALOG-005 — **IMPLEMENTED / AWAITING INDEPENDENT REVIEW**:
  unaccent/rank/bulk; benchmark не выполнен. Следующий пакет —
  `BA-QUALITY-002`.
- App F — реализованы серверные срезы (session/ticket, result,
  leaderboard, storage, playtime, ratings, popularity); принят только
  APPF-SESSION-001, остальные — AWAITING OWNER ACCEPTANCE; клиентский
  runtime/SDK/EventLog отсутствует. `BA-APPF-001` — подготовка решений;
  `BA-APPF-002` — **NOT_STARTED**.
- BA-ZIP-PREFLIGHT-001 — **TECHNICALLY ACCEPTED** (agent, OD-TECH-001);
  продуктовая приёмка — владелец: metadata-only проверка ZIP.
- BA-ZIP-EXTRACT-001 — **TECHNICALLY ACCEPTED** (agent, OD-TECH-001);
  продуктовая приёмка — владелец: потоковая safe-extraction (byte caps,
  CRC, канонические пути, atomic rename); security review accept.
- BA-DEVCONTROL-001 — **IMPLEMENTED / AWAITING OWNER SETUP + REVIEW**:
  отдельный Telegram-сервис `devcontrol/` (owner-only, `claude --bg`,
  state/events/hooks); live Telegram не проверен — нужен токен владельца;
  runtime `~/.local/state/ba-devcontrol`.
- BA-ZIP-WORKER-001 — **TECHNICALLY ACCEPTED** (agent, OD-TECH-001);
  продуктовая приёмка — владелец: отдельный
  Compose-сервис `zip-worker` (`zipnet` только с broker, prefork,
  read_only/limits, очередь `zip`, cancel, audit); code/security review
  accept; остатки R-033/R-035/R-036/R-037. Отчёт —
  `docs/foundation/BA-ZIP-WORKER-001_REPORT.md`.
- R-036 Phase 1 — **TECHNICALLY ACCEPTED** (agent): delivery observability
  (`task_received/failure/retry`, worker shutdown), R-036 docstrings,
  5 contract tests; live `celery.task.received`; full 402/3; code/security
  review accept; delivery behavior unchanged. Phase 2 — AWAITING OWNER
  DECISION. Отчёт — `docs/foundation/R-036_PHASE1_REPORT.md`.
- BA-APPF-002 / DB-001 — **TECHNICALLY ACCEPTED** (agent; owner chose
  tombstone): все сессии пользователя при удалении получают
  subject_type=deleted + random per-session UUID; created/active aborted,
  ticket/binding cleared; finished/expired state kept; migration 0011;
  403/3; review accept. Отчёт —
  `docs/foundation/BA-APPF-002_DB001_SESSION_CLEANUP_REPORT.md`.
- BA-APPF-002 / DB-006 — **TECHNICALLY ACCEPTED** (agent): model `save()` +
  PostgreSQL trigger; GameVersion content/hash/version immutable; audit FKs
  only unchanged/→NULL; user-deletion SET_NULL; migrations 0006/0007;
  16 tests; full 419/3; code/security review accept. Отчёт —
  `docs/foundation/BA-APPF-002_DB006_REPORT.md`.
- BA-APPF-002 / DB-005 + DB-007 — **TECHNICALLY ACCEPTED** (agent):
  GameTranslation.name 60; GameSession mode↔subject CHECK
  user/guest/preview/autotest + deleted tombstone; migrations
  catalog.0008, gameplay.0012; 14 tests; full 433/3. Отчёт —
  `docs/foundation/BA-APPF-002_DB005_DB007_REPORT.md`.
- BA-APPF-002 / DB-004 + residuals — **TECHNICALLY ACCEPTED** (agent):
  Game identity immutable после публикации + DELETE forbidden;
  GamePlayCredit удаляется при удалении аккаунта; GameSession.mode
  immutable; migrations catalog.0009/0010/gameplay.0013; 441/3. Отчёт —
  `docs/foundation/BA-APPF-002_DB004_RESIDUALS_REPORT.md`.
- BA-APPF-002 runtime A+B — **IMPLEMENTED / TECHNICAL REVIEW**:
  SDK/host/player/play view, server-side create+activate, exact runtime
  origin, CSRF relay; full 452/4; E2E/probe и review evidence отсутствуют.
  Отчёт — `docs/foundation/BA-APPF-002_RUNTIME_SDK_REPORT.md`.
- Прохождение тестов не является приёмкой; отчёт исполнителя не является
  результатом независимого аудита.
- Staging не затрагивать без отдельного разрешения. В текущей зоне
  BA-STAGE-1.1 staging не изменялся.

## 6. Решения владельца — не путать с предложениями

Решения владельца находятся только в разделе **A** файла `docs/decisions/OWNER_DECISIONS.md`. Не считать решением владельца:

- рекомендации аудиторов/агентов;
- предложенные технические улучшения;
- варианты исправления R-001/R-003/R-004/R-005;
- предложенную структуру документации;
- технические замечания из раздела B.2, включая `TECH-EN-005` и `TECH-HTTP-004`, до отдельного подтверждения.

Нормативные требования находятся в разделе B.1; ограничения конкретных задач — в разделе C. Эти категории не являются решениями владельца.

## 7. Правила работы

- Не изменять `CLAUDE.md`, нормативные ТЗ, `.claude/`, README, `.env`, `certs/`, `creds/` без отдельного разрешения.
- В документационной задаче не изменять исходный код, тесты и конфигурацию;
  в режиме BA-AUTONOMOUS-001 реализация и тесты разрешены в рамках
  утверждённых требований и текущего пакета.
- Не выполнять `git add`, коммиты, reset, checkout, stash и другие изменения Git без явного задания.
- Не выполнять миграции и не изменять БД/volumes/Docker/Compose без явного задания.
- Не обращаться к staging/production без явного разрешения.
- Не выдавать тесты, generated-отчёты или заявления исполнителя за приёмку.
- Не повторять существующий аудит App F; использовать
  `docs/foundation/BA-AUDIT-APP-F-REPORT.md`.
- Не запрашивать повторно уже переданные файлы, если они есть в проекте.
- Проверять `TASK_HISTORY.md` и `AUDIT_REGISTER.md` до постановки работы,
  которая уже выполнена или проверена.
- При неоднозначности остановиться и задать конкретный вопрос владельцу.

## 8. Порядок начала новой задачи

1. Прочитать обязательные документы из списка выше.
2. Сверить задачу с `PROJECT_STATUS.md` и разделом A `OWNER_DECISIONS.md`.
3. Проверить актуальный HEAD, Git status, staged и рабочее дерево.
4. Найти точный пункт нормативного ТЗ; если нужного документа нет (BA-SDK-1.1/BA-ENV-1.1) — остановиться.
5. Составить минимальный план и оценить риски; получить согласование на существенные изменения.
6. Выполнить только согласованную область.
7. Обновить `PROJECT_STATUS.md`, решения/аудит/риски/историю задач, если задача меняет контекст.
8. Зафиксировать фактические проверки и продолжить следующий незаблокированный пакет по `BACKLOG.md`; останавливаться только на решении владельца или критическом блокере.

## 9. Актуальные ограничения на самостоятельные решения

- Не закрывать BA-FIX-001 и не принимать BA-STAGE-1.1.
- Не объявлять этапы 0/1 формально закрытыми.
- Не запускать следующий крупный этап без аудита и нового ID.
- R-006/R-007 закрыты в BA-I18N-002; не переоткрывать без регрессии. R-003/R-004/R-005 остаются и требуют отдельного пакета.
- Не выбирать вариант BA-GAME-2.2 и не создавать BA-SDK-1.1/BA-ENV-1.1.
- Не считать App F готовым к реализации/приёмке; `BA-APPF-002` не запускать
  без отдельного задания и утверждения `BA-APPF-001`/контрактов.
- Не смешивать отчёт агента, независимый аудит и приёмку владельцем.
- В документационной задаче изменять только разрешённые документы; не
  выполнять `git add`/коммиты/индексные операции; не менять код, SQL,
  схемы, ТЗ и инфраструктуру.

## 10. Источники

`PROJECT_STATUS.md`, `OWNER_DECISIONS.md`, `AUDIT_REGISTER.md`, `RISK_REGISTER.md`, `TASK_HISTORY.md`, `BACKLOG.md`, `CLAUDE.md`, нормативные ТЗ и AI Dev provenance README.

## 11. BA-FOUNDATION-002 — что читать дополнительно

- `docs/contracts/BA-SDK-1.1_DRAFT.md` — DRAFT, не нормативный.
- `docs/contracts/BA-ENV-1.1_DRAFT.md` — DRAFT, не нормативный.
- `docs/contracts/SESSION_ID_PROTOCOL.md` — внешний `sessionId`, внутренний
  `session_id`.
- `docs/contracts/MESSAGE_PROTOCOL.md` и `schemas/messages/*.json` — draft
  протокол App F.
- `docs/contracts/CONTRADICTIONS.md` — расхождения, включая `session_id`.
- `docs/audits/BA-GAME-2.2_COMPARISON.md` — два варианта; канонический не выбран.
- `docs/foundation/DB_SCHEMA.md`, `ERD.md`, `ba_schema.sql` — проектная
  схема БД, не миграция.
- `docs/contracts/APP_J_FIELD_MAPPING.md` — mapping App J.
- `docs/foundation/BA-FOUNDATION-002_REPORT.md` — итог, доказательства и
  блокеры. Запрошенный `reports/BA-FOUNDATION-002_REPORT.md` заблокирован
  guard-хуком; файл сохранён в `docs/foundation/` до решения владельца.

**Текущий статус BA-FOUNDATION-002:** Partial/Blocked. Этап 0 не закрыт.
DRAFT-документы не являются нормативными и не должны подключаться как
окончательные контракты. BA-SDK-1.1/BA-ENV-1.1 оригиналы по-прежнему
отсутствуют.

## 12. App F — что читать и чего не делать

- `docs/foundation/BA-AUDIT-APP-F-REPORT.md` — существующий аудит App F
  (2026-11-19): runtime не реализован; существуют только draft-схемы,
  `apps/core/contracts.py` и contract-тесты. Не повторять этот аудит без
  причины.
- `docs/foundation/BA-APPF-001_DESIGN_DECISIONS.md` — подготовка 45
  проектных решений (DRAFT/PREP): 29 Blocker, 17 вопросов владельцу. Ни одно
  решение не является решением владельца.
- `BA-APPF-002` — **NOT_STARTED**. Не отражать её как выполненную и не
  запускать реализацию до утверждения контрактов и решений.
- BA-FOUNDATION-001: фактический отчёт — `BA-FOUNDATION-001_REPORT.md` в
  корне; `docs/foundation/BA-FOUNDATION-001_REPORT.md` отсутствует.

## 13. BA-I18N-002 / BA-STAGE-1.2-E2E — что изменилось

- Добавлен `apps/i18n/services/language_registry.py`: кэш активных языков
  является оптимизацией; отказ Redis переводится в чтение PostgreSQL.
- `language_url` использует безопасный helper и не отдаёт 500 при
  недоступном реестре; middleware/root ловят только
  `LanguageRegistryUnavailable`; неожиданные ошибки не маскируются.
- R-006/R-007 закрыты regression-тестами; 147 tests, lint/mypy clean.
- BA-STAGE-1.2-E2E: `tests/e2e/test_portal_shell_e2e.py`, 11 passed против
  dev-стека; обычный suite — 147 passed, 1 skipped.
- R-003 (TTL других языков), R-004/R-005 (transaction/Redis evidence) и
  R-002 (ограниченное подтверждение) остаются.
- BA-STAGE-1.2-E2E зафиксирован как **IMPLEMENTED / AWAITING INDEPENDENT
  REVIEW**; не переоткрывать без технической причины.
- Следующий незаблокированный пакет — `BA-QUALITY-002` (benchmark/
  покрытие); App F и BA-APPF-002 остаются заблокированными/не запущенными.

## 14. BA-STAGE-2.1 — что изменилось

- Миграция `apps/accounts/migrations/0002_nicknamereservation_anonymousidentity_emailaddress_and_more.py`
  применена в dev.
- Модели: `UserProfile`, `EmailAddress`, `NicknameHistory`,
  `NicknameReservation`, `AnonymousIdentity`, `AccountToken`,
  `UserLegalAcceptance`.
- Сервисы: `registration`, `profile`, `email`, `tokens`, `nickname`,
  `anonymous`, `rate_limit`, `hibp`; Celery `anonymize_due_accounts`.
- Маршруты: `/auth/register|login|logout|verify-email|resend-verification|password-reset`,
  `/account/|edit|password|export|delete|delete/cancel`.
- Security: Argon2id, CSRF, safe `next`, HIBP fail-closed hook, one-time
  hashed tokens, нейтральный reset, инвалидация reset-токенов и прочих
  сессий, повторная аутентификация для смены email.
- Фактические проверки: `tests/integration/test_accounts.py` (17),
  `tests/unit/test_account_services.py` (4), полный suite — 167 passed,
  1 skipped; lint/mypy/check/migrations — см. отчёт.
- **Не готово:** legal texts/versions (сейчас `draft`), страницы `/legal/*`,
  история игр/личные рекорды/места, bounce/provider, игровой cleanup при
  удалении, `AnonymousIdentity` в реальном subject-запросе, 2FA персонала.
- Не считать BA-STAGE-2.1 завершённым или принятым; это **PARTIAL**.

## 15. BA-STAGE-2.2 — что изменилось

- Миграция `accounts.0003_user_totp_last_counter_user_totp_secret_recoverycode`
  применена в dev.
- `User.totp_secret` (base32), `User.totp_last_counter`; `RecoveryCode`
  (`code_hash`, `used_at`).
- Сервис `apps/accounts/services/two_factor.py`: TOTP, replay-protection,
  10 recovery-кодов, enable/disable.
- Маршруты `/auth/2fa/`, `/auth/2fa/recovery/`, `/auth/2fa/setup/`,
  `/auth/2fa/disable/`; staff-middleware требует 2FA; email-уведомление
  при enable/disable.
- Фактические проверки: 6 integration tests (`tests/integration/test_two_factor.py`),
  full suite — 173 passed, 1 skipped; lint/mypy/check/migrations — clean.
- **Не готово:** офлайн-код восстановления владельца, отдельный журнал
  входов/SecurityEvent, уведомления о смене ролей, роли/CRM step-up,
  browser E2E. TOTP-секрет хранится в БД как base32 (риск R-020).
- Не считать BA-STAGE-2.2 завершённым или принятым; это **PARTIAL**.

## 16. BA-STAGE-2.3 — что изменилось

- `tests/e2e/test_accounts_e2e.py`: регистрация → профиль → export →
  logout/login → смена пароля → login с новым паролем → deletion request/
  cancel; отдельный отказ формы без согласия.
- 2 E2E passed; полный E2E — 13 passed (11 shell + 2 account).
- Обычный `make test` по-прежнему skip E2E; CI E2E не запускает.
- E2E создаёт уникального dev-пользователя и не удаляет его; повторный
  прогон может упереться в registration rate limit 3/day.
- Не считать BA-STAGE-2.3 приёмкой; статус — **IMPLEMENTED / AWAITING
  INDEPENDENT REVIEW**.

## 17. BA-STAGE-2.4 — что изменилось

- Миграция `accounts.0004_ownerrecoverycode_loginevent` применена в dev.
- `OwnerRecoveryCode`: офлайн-код только для superuser, one-time; после
  использования 2FA сбрасывается и требуется повторный enrollment.
- `LoginEvent`: журнал login/2FA/recovery/enable/disable без plaintext
  login/IP (hash); retention 12 мес. ещё не реализован.
- Regeneration recovery-кодов через password+TOTP; owner code
  перегенерируется для superuser.
- 9 2FA integration tests; full suite — 176 passed, 2 skipped.
- Не считать BA-STAGE-2.4 завершённым; роли/CRM step-up, уведомления о
  смене ролей, encryption TOTP-секрета и retention остаются.

## 18. BA-STAGE-2.5 — что изменилось

- Celery Beat `accounts.cleanup_expired_account_records` (daily): expired
  `AnonymousIdentity`/`AccountToken`, `LoginEvent` старше 365 дней, expired
  `NicknameReservation`.
- `NICKNAME_RESERVATION_DAYS=730`; reservation при удалении аккаунта
  использует настройку.
- 1 retention integration test; full suite — 177 passed, 2 skipped.
- **Не покрыто:** `SecurityEvent`, `GameStorage`, `GameSession`, mail-логи,
  бэкапы, согласия; App F/CRM/провайдеры отсутствуют.
- Не считать BA-STAGE-2.5 завершённым; это **PARTIAL**.

## 19. BA-QUALITY-001 — что изменилось

- `make coverage` и `[tool.coverage.run/report]`; `fail_under=70`.
- Фактический coverage — 81.65 % (2594 statements, 476 missed);
  177 passed, 2 skipped.
- Низкие модули: `hibp.py` 39 %, `health.py` 59 %, `ba_i18n.py` 63 %,
  `coverage.py` 36 %, `theme/views.py` 40 %, `storage.py` 0 %.
- Порог по совокупности выполнен; отдельные модули ниже 70 %. Это не
  приёмка §2.26 и не независимый аудит.
- Следующий пакет — `BA-CATALOG-001` (публичный каталог без App F).

## 20. BA-CATALOG-001 — что изменилось

- `apps/catalog/services/catalog.py`: `published_games`, `filter_games`,
  `parse_filters`, `localized_translation`, `card_items`, `genre_options`.
- `/games/`: published-only, genre/mobile/duration/q/sort, HTMX partial.
- `/games/<slug>/`: game/translation slug, fallback `en`, 404 для draft.
- `/genres/<slug>/`: genre page; home показывает latest cards.
- 5 integration tests; full suite — 182 passed, 2 skipped.
- **Не реализовано:** M2M дополнительных жанров/тегов, FTS/`pg_trgm`,
  ratings/popularity/голоса, coverage badge, play runtime (App F).
- Не считать BA-CATALOG-001 завершённым; это **PARTIAL**.

## 21. BA-CATALOG-002 — что изменилось

- Миграция `catalog.0003_gamegenre_game_additional_genres_gametag_game_tags_and_more`
  применена в dev.
- `GameGenre`/`GameTag`; `Game.additional_genres`/`Game.tags`.
- Фильтры: genre матчит primary или additional; tags — мультивыбор OR.
- 6 integration tests; full suite — 183 passed, 2 skipped.
- FTS/`pg_trgm`, ratings/popularity, coverage badge и play runtime остаются.
- Не считать пакет приёмкой §2.8; статус — **IMPLEMENTED / AWAITING
  INDEPENDENT REVIEW**.

## 22. BA-CATALOG-003 — что изменилось

- `filter_games(filters, language_code)`: `SearchVector`/`SearchQuery` по
  name/short_description/description, `TrigramSimilarity`, `icontains`
  fallback; config из `Language.fts_config` или `simple`.
- 7 integration tests; full suite — 184 passed, 2 skipped.
- `GameTranslation.search_vector` не заполняется, GIN по выражению нет,
  `unaccent`/ranking не применены; пакет **PARTIAL**.
- Следующий пакет — `BA-CATALOG-004` (persisted vector/GIN/backfill).

## 23. BA-CATALOG-004 — что изменилось

- `apps/catalog/signals.py`: post_save `GameTranslation` обновляет
  `search_vector` через SearchVector A/B/C (simple).
- `catalog.0004_backfill_search_vector`: backfill существующих NULL-векторов.
- `filter_games` использует stored vector + GIN, сохраняя query-time
  FTS/trigram fallback.
- 7 integration tests; full suite — 184 passed, 2 skipped.
- **Не реализовано:** `unaccent`, `SearchRank`, bulk/import refresh,
  проверка плана на объёме.
- Не считать пакет завершённым; это **PARTIAL**.

## 24. BA-CATALOG-005 — что изменилось

- `Unaccent` Func применяется в persisted vector и query-time FTS.
- `SearchRank` задаёт порядок при поиске (кроме sort=old).
- Celery Beat `catalog.refresh_catalog_search_vectors` пересчитывает vector
  после bulk/import; backfill `catalog.0005` с `unaccent`.
- 8 integration tests; full suite — 185 passed, 2 skipped.
- Benchmark/EXPLAIN на объёме, ratings/popularity/play не реализованы.
- Статус пакета — **IMPLEMENTED / AWAITING INDEPENDENT REVIEW**; каталог
  в целом остаётся PARTIAL.

## 25. BA-AUTONOMY-003 — AI infrastructure

- Основная сессия остаётся Flash; Pro (`architect`, `code-reviewer`,
  `security-auditor`) работает в text-only режиме: Flash передаёт бриф,
  Pro возвращает план/вердикт без tool-вызовов.
- Факт: v4-pro маршрутизируется (`message.model=deepseek-v4-pro`), но
  tool-использование ненадёжно (`leading-only`); text-only — обязательный
  паттерн, а не опция.
- Добавлены `ba-plan`, Bash-guard, обновлены `ba-development`,
  `ba-code-review`, `ba-testing`, `ba-project-audit`.
- Введён `NOW.md`; указатели `docs/spec` исправлены на
  `technical_specification/`; `ai-dev` — read-only sibling.
- Следующий продуктовый срез — APPF-SESSION-001 (GameSession/LaunchTicket,
  §2.12.1–2.12.4), без SDK/ENV/BA-GAME.

## 26. APPF-SESSION-001 — серверный session/ticket срез App F

- Реализованы `GameSession`, одноразовый launch ticket, activate/heartbeat
  по §2.12.1–2.12.4; API `/api/v1/sessions`, `/activate`, `/heartbeat`.
- CSRF обязателен для анонимных; throttle `sessions`/`heartbeat` с ключом
  по живой guest-identity, IP — fallback; лимит ≤3 активных под
  advisory-lock и при создании, и при активации.
- Subject — `(subject_type, subject_id)` без FK до DB-001; context-поля —
  [PROP] до BA-SDK-1.1. Результаты/leaderboard/storage/SDK вне среза.
- Review: `code-reviewer` + `security-auditor` (deepseek-v4-pro, text-only)
  — **accept**; статус **ACCEPTED** владельцем 2026-11-20 (OD-STATUS-007),
  evidence — `docs/audits/APPF-SESSION-001_REVIEW_EVIDENCE.md`.
- Найден и исправлен дефект свежих БД: `catalog.0001` citext без
  зависимости от `core.0001_extensions` (добавлена graph-зависимость).
- Следующий шаг — приёмка владельца и решения по
  `docs/decisions/APPF-OWNER-DECISION-PACKAGE.md`; затем
  result/leaderboard/storage только после BA-SDK/ENV/BA-GAME и решений
  по DB-001…DB-008.

## 27. APPF-SESSION-002 и APPF-RESULT-001

- Throttle: subject 30/ч + IP 600/ч (/64), heartbeat 3/мин на сессию,
  structured 429, `redis-throttle` noeviction, `ClientIPMiddleware`
  (XFF только от доверенных прокси). Отчёт —
  `docs/foundation/APPF-SESSION-002_REPORT.md`.
- Result: `POST /api/v1/sessions/{id}/result`, GameResult +
  LeaderboardEntry, DB-001/002/003 (CHECK субъекта, триггеры), гость 403
  без записи, preview/autotest `is_test` без рекордов, идемпотентность,
  100-параллельный тест. Отчёт — `docs/foundation/APPF-RESULT-001_REPORT.md`.
- Оба среза — **IMPLEMENTED / AWAITING OWNER ACCEPTANCE**, review
  code-reviewer/security-auditor accept/без блокеров.
- Следующие: Storage → публичный Leaderboard API → SDK/iframe → EventLog;
  retention и challenge — решения владельца.
