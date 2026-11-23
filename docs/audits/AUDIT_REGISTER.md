# AUDIT_REGISTER — Breaktime Arcade

Реестр аудитов/проверок и их замечаний. Независимость источника указывается
в каждой записи; наличие записи не является доказательством приёмки этапов.
Результаты тестов считаются техническими доказательствами, но не заменяют
решение владельца.

Дата фиксации: 2026-11-20 (актуализация BA-ZIP-PREFLIGHT-001).
Источник записей: отчёты аудитов в истории работ BA. Для BA-AUDIT-002/
BA-AUDIT-003 и BA-DOC-AUDIT-001 отдельные постоянные файлы в проекте не
найдены; для App F существует
`docs/foundation/BA-AUDIT-APP-F-REPORT.md`.

## ARCADE-P4 — hardening and first game

| Поле | Значение |
|---|---|
| Цель | Проверить R-033/R-037/R-041/R-042, resilience и первую реальную игру |
| Область | ZIP quota/retention, isolated worker, CRM import/publish, public iframe/SDK, update/rollback, mobile/console |
| Итоговый статус | **IMPLEMENTED / TECHNICAL REVIEW**; product/staging/legal — owner |
| Доказательства | fresh **966/12**, E2E **18**, live worker import 131 ms, result `saved/rank 1`, leaderboard 200, v1.1.0/rollback, bad ZIP `V_MANIFEST_SCHEMA` |
| Исправлено | media 0644/403; отсутствие cover/screenshots на detail; HTMX inline style/CSP; 360px header overflow |
| Остаётся | staging `.env.staging` NOT TESTED; hard FS quota/load NOT TESTED; original P3 reviewer JSON not persisted |
| Документы | `docs/foundation/ARCADE_P4_ACCEPTANCE_REPORT.md`, `docs/foundation/ARCADE_P4_PROGRESS.md`, `docs/audits/ZIP_WORKER_REVIEW_EVIDENCE.md`, `docs/audits/R-041_SYNC_WAIT_ANALYSIS.md` |

## ARCADE-P5 — Archer

| Поле | Значение |
|---|---|
| Цель | проверить полноценную игру Archer и интеграцию |
| Область | physics/combo/SDK/package/locales/assets/live CRM/runtime |
| Итоговый статус | **IMPLEMENTED / LIVE DEV E2E PASS / PRO REVIEW ACCEPT**; product/staging/prod owner |
| Доказательства | Node 11, package 14, import 1, fresh 981/12, E2E 18; live result 156 rank 3; 321/214/156 leaderboard; rollback/republish |
| Найдено/исправлено | HUD behind start, pause label, stage aspect, bow arc, end-event drop, RNG identity/range, idle-gap threshold, offline handling |
| Остаётся | source prototype absent; staging/production; non-Chromium; real network fault injection |
| Документы | `docs/foundation/ARCHER_ACCEPTANCE_REPORT.md`, `ARCHER_GAME_SPEC.md`, `ARCHER_PROGRESS.md` |

## BA-AUDIT-002

| Поле | Значение |
|---|---|
| Цель | Повторный независимый аудит реализации после BA-FIX-001 и утверждённых решений владельца |
| Область | Accept-Language, middleware, языковые URL, `Content-Language`, кэш активных языков, readiness, тесты |
| Итоговый статус | **COMPLETED** (аудит); на момент отчёта BA-FIX-001 **не готов к закрытию** |
| Блокирующее замечание | D-001: обход проверки активного `en` через `QuerySet.update()`/`bulk_update()` из-за TTL-кэша `i18n:active_codes` |
| Другие замечания | D-006 — транзакционная инвалидация кэша; D-002 — региональный `q=0`; D-003 — неполное покрытие тестами; D-004/A-007 — смешанный diff; D-005 — внутренний API Django |
| Что исправлено | D-001/D-006 отмечены как Fixed последующими решениями/работами; BA-FIX-001 остаётся открытым; точная хронология — в `TASK_HISTORY.md` |
| Что остаётся | BA-FIX-001 **NOT_ACCEPTED**; A-007 (разделение diff) остаётся процессным вопросом; BA-STAGE-1.1 **NOT_ACCEPTED** |
| Связанные документы | `docs/status/PROJECT_STATUS.md`, `docs/decisions/OWNER_DECISIONS.md`, `docs/risks/RISK_REGISTER.md` |
| Примечание | В `reports/BA_AUDIT_20261118_162920.zip` находится generated-отчёт BA-FIX-001, а не полный отчёт BA-AUDIT-002. Не использовать его как замену реестру. |

Критические замечания BA-AUDIT-002: D-001 (блокирующее на момент аудита).
Некритические/процессные: D-002, D-003, D-004/A-007, D-005.

## BA-AUDIT-003

| Поле | Значение |
|---|---|
| Цель | Независимая проверка BA-FIX-003 и отсутствия регрессий после последних изменений |
| Область | helper получения активных языков, middleware, root redirect, 503/406/404/302, `Vary`, тестовая изоляция, Git, остаточные риски |
| Итоговый статус | **COMPLETED** (аудит); BA-FIX-003 **ACCEPTED** с некритичными замечаниями |
| Блокирующие замечания | Не обнаружены |
| AUD3-001 | Широкие `except Exception` могут скрывать программные ошибки; некритичное замечание |
| AUD3-002 | `portal_urls.language_url` не защищён от отказа cache/DB; возможен HTTP 500; некритичное замечание/остаточный риск |
| AUD3-003 | Error-тесты используют monkeypatch, а не реальный отказ Redis/DB; ограничение доказательной базы |
| AUD3-004 | В предыдущем отчёте `views.py` был неверно обозначен `M`; фактически untracked `??` |
| AUD3-005 | Тестовая изоляция улучшена, но часть error-состояний остаётся модельной |
| Что исправлено | BA-FIX-003 **ACCEPTED** с некритичными замечаниями; AUD3-001/AUD3-002 закрыты технически в BA-I18N-002 |
| Что остаётся | AUD3-003/AUD3-005 и R-003/R-004/R-005; BA-FIX-001 **NOT_ACCEPTED**; BA-STAGE-1.1 **NOT_ACCEPTED** |
| Связанные документы | `docs/risks/RISK_REGISTER.md`, `docs/status/PROJECT_STATUS.md` |
| Примечание | «Готов с некритичными замечаниями» относится к BA-FIX-003, а не к BA-STAGE-1.1. |

## BA-DOC-AUDIT-001

| Поле | Значение |
|---|---|
| Цель | Инвентаризация документации и сохранённого контекста BA и AI Dev |
| Область | `CLAUDE.md`, `technical_specification/`, `docs/`, `reports/`, `.claude/`, AI Dev handoff/проектные документы, Git-состояние |
| Итоговый статус | **COMPLETED** (аудит); выявлены существенные документальные пробелы |
| Основные выводы | Нет постоянного реестра решений владельца, аудитов, рисков, статуса и истории задач; `docs/` в BA в основном пуст; specs в BA untracked; старый generated-отчёт устарел; AI Dev документирует AI-среду, но не текущий BA; инструкции о «замороженном BA» устарели |
| Блокирующие замечания | Нет технического блокера; документальный контекст недостаточен для надёжного восстановления |
| Что исправлено | Documentation Block 1 (BA-DOC-001 + FIX-01/02/03) **ACCEPTED**; BA-DOC-002 актуализировал шесть документов |
| Что остаётся | Устаревшие README/CLAUDE/.claude/README и AI Dev-статус; вопросы SDK/ENV, BA-GAME, Git/backup; документальная приёмка не закрывает технические этапы |
| Связанные документы | Все документы в `docs/status`, `docs/decisions`, `docs/audits`, `docs/risks`, `docs/tasks`, `docs/handoff` |

## BA-AUDIT-APP-F — предыдущий аудит App F

| Поле | Значение |
|---|---|
| Тип | Статический аудит фактической реализации App F (отчёт агента; не приёмка) |
| Цель | Проверить postMessage, origin/source, sessionId/requestId, JSON Schema, rate limit, idempotency, состояния сессии, submit/leaderboard/storage и EventLog |
| Область | `apps/gameplay`, SDK, host protocol, player/iframe, `apps/core/contracts.py`, `schemas/messages/*.json`, `schemas/eventlog.json`, `config/settings/base.py` |
| Итоговый статус | **COMPLETED** (аудит); вывод: **App F runtime не реализован**; App F не готов к приёмке |
| Фактический результат | `apps/gameplay`, `sdk/1.1.0/ba-sdk.js`, `static/src/js/host_protocol.js`, `static/src/js/player.js` и iframe-страница пусты/0 байт; существуют только draft-схемы, `apps/core/contracts.py` и contract-тесты |
| Что не подтверждено | postMessage/origin/source, sessionId/requestId, lifecycle, idempotency, rate/size, server-side trust, EventLog в runtime, leaderboard/storage, browser/E2E |
| Отчёт | `docs/foundation/BA-AUDIT-APP-F-REPORT.md` (2026-11-19) |
| Примечание | Это существующий отчёт; BA-DOC-002 повторно аудит не выполнял. Наличие схем/валидатора не является доказательством сквозной системы |

## BA-FOUNDATION-001 — статус проверки, не аудит

| Поле | Значение |
|---|---|
| Тип | Отчёт о работе над фундаментом этапа 0; не независимый аудит |
| Цель | Закрыть подтверждённые дефекты этапа 0 без новых нормативных решений |
| Результат | JSON Schema manifest/catalog/eventLog; DRF deny-by-default; nginx listener healthcheck; architecture/API/runbooks; тесты/миграции/dev-стек/backup |
| Статус | **COMPLETED** (работа); **не ACCEPTED**; отчёт Partial/Blocked; этап 0 не закрыт |
| Дата | 2026-11-19 |
| Отчёт | `BA-FOUNDATION-001_REPORT.md` в корне; запрошенный `docs/foundation/BA-FOUNDATION-001_REPORT.md` отсутствует |
| Ограничения | BA-SDK/ENV, sessionId conflict, message schemas, SQL/App J, production infra, Docker digest; независимая проверка выявила ограничения, отдельный отчёт независимой проверки в файлах не найден |
| Примечание | Не включать в AUDIT_REGISTER как независимый аудит без первичного отчёта |

## BA-APPF-001 — подготовка решений, не аудит

| Поле | Значение |
|---|---|
| Тип | DRAFT/PREP-документ; не аудит и не приёмка |
| Результат | 45 решений `APPF-DEC-001`…`045`; 29 Blocker; 17 вопросов владельцу |
| Статус | **COMPLETED** (подготовка); **не ACCEPTED**; BA-APPF-002 **NOT_STARTED** |
| Отчёт | `docs/foundation/BA-APPF-001_DESIGN_DECISIONS.md` |
| Примечание | Ни одно предложение не является решением владельца |

## BA-I18N-002 — техническая работа, не аудит

| Поле | Значение |
|---|---|
| Тип | Техническая реализация/self-check; не независимый аудит |
| Результат | R-006/R-007 закрыты: `language_registry` переживает cache failure, `language_url` безопасен, middleware/root ловят только `LanguageRegistryUnavailable`; regression-тесты |
| Статус | **COMPLETED** (работы); не `ACCEPTED`; 147 tests, lint/mypy clean |
| Ограничение | R-003/R-004/R-005 и R-002 с ограниченной доказательной базой не закрыты |
| Источник | `TASK_HISTORY.md`, `tests/integration/test_language_registry.py`, `tests/integration/test_core.py` |

## BA-STAGE-1.2-E2E — browser-проверка, не аудит

| Поле | Значение |
|---|---|
| Тип | Browser/E2E self-check на dev-стеке; не независимый аудит |
| Результат | 11 E2E passed: шесть языков, root redirect, 404, language switcher, 360px, healthz; обычный suite — 147 passed, 1 skipped |
| Статус | **IMPLEMENTED / AWAITING INDEPENDENT REVIEW**; не `ACCEPTED`; CI browser E2E не запускает |
| Ограничение | E2E требует живого dev-стека, Playwright и TLS ignore; не заменяет приёмку |
| Источник | `tests/e2e/test_portal_shell_e2e.py` |

## BA-STAGE-2.1 — техническая работа, не аудит

| Поле | Значение |
|---|---|
| Тип | Техническая реализация/self-check §2.10; не независимый аудит и не приёмка |
| Результат | `accounts.0002`; модели профиля/email/nickname/token/anonymous/legal; регистрация/вход/выход; email verification; password reset; профиль; password change; export; deletion request/cancel + Celery anonymization; Argon2id/HIBP-hook/rate limits/CSRF |
| Статус | **PARTIAL** (работы); core проверен, приёмка §2.10 не выполнена |
| Доказательства | `tests/integration/test_accounts.py` (17), `tests/unit/test_account_services.py` (4); full suite — см. фактический прогон в отчёте; lint/mypy/check/migrations — фактические результаты в `docs/foundation/BA-STAGE-2.1_REPORT.md` |
| Ограничения | Нет утверждённых legal texts/versions; нет моделей истории игр/рекордов и игрового cleanup; нет bounce/provider; `AnonymousIdentity` не подключена к subject-запросам; 2FA персонала — отдельный пакет |
| Источник | `TASK_HISTORY.md`, `apps/accounts/**`, `docs/foundation/BA-STAGE-2.1_REPORT.md` |

## BA-STAGE-2.2 — техническая работа, не аудит

| Поле | Значение |
|---|---|
| Тип | Техническая реализация 2FA персонала; не независимый аудит и не приёмка |
| Результат | `accounts.0003`; `User.totp_secret`/`totp_last_counter`; `RecoveryCode`; TOTP enrollment/verify/recovery/disable; replay-protection; staff-middleware; email notice |
| Статус | **PARTIAL** (работы); 6 integration tests; full suite 173 passed, 1 skipped |
| Ограничения | Нет owner offline recovery, журнала входов/SecurityEvent в БД, ролей/CRM step-up и browser E2E; TOTP-секрет хранится как base32 |
| Источник | `TASK_HISTORY.md`, `apps/accounts/services/two_factor.py`, `tests/integration/test_two_factor.py`, `docs/foundation/BA-STAGE-2.2_REPORT.md` |

## BA-STAGE-2.3 — browser E2E, не аудит

| Поле | Значение |
|---|---|
| Тип | Browser/E2E self-check аккаунтов на dev-стеке; не независимый аудит |
| Результат | `tests/e2e/test_accounts_e2e.py`: 2 passed; полный E2E — 13 passed (11 shell + 2 account) |
| Статус | **IMPLEMENTED / AWAITING INDEPENDENT REVIEW**; не `ACCEPTED`; CI E2E не запускает |
| Ограничение | Создаёт уникального dev-пользователя; повторный прогон зависит от rate limit 3/day; 2FA E2E staff не покрыт |
| Источник | `TASK_HISTORY.md`, `tests/e2e/test_accounts_e2e.py`, `docs/foundation/BA-STAGE-2.3_REPORT.md` |

## BA-STAGE-2.4 — техническая работа, не аудит

| Поле | Значение |
|---|---|
| Тип | Техническая реализация 2FA completion; не независимый аудит |
| Результат | `accounts.0004`; `OwnerRecoveryCode`; `LoginEvent`; owner recovery → обязательный re-enrollment; regeneration recovery-кодов; события login/2FA/recovery |
| Статус | **PARTIAL** (работы); 9 2FA integration tests; full suite 176 passed, 2 skipped |
| Ограничения | Роли/CRM step-up, уведомления о смене ролей, encryption TOTP-секрета и retention cleanup остаются |
| Источник | `TASK_HISTORY.md`, `apps/accounts/services/two_factor.py`, `apps/accounts/services/audit.py`, `tests/integration/test_two_factor.py`, `docs/foundation/BA-STAGE-2.4_REPORT.md` |

## BA-STAGE-2.5 — техническая работа, не аудит

| Поле | Значение |
|---|---|
| Тип | Техническая реализация account retention; не независимый аудит |
| Результат | Celery Beat `accounts.cleanup_expired_account_records`: expired `AnonymousIdentity`/`AccountToken`, `LoginEvent` >365 дней, expired `NicknameReservation`; `NICKNAME_RESERVATION_DAYS=730`; 1 integration test |
| Статус | **PARTIAL** (работы); full suite 177 passed, 2 skipped |
| Ограничения | `SecurityEvent`/`GameStorage`/`GameSession`/mail/backup/consent сроки не покрыты |
| Источник | `TASK_HISTORY.md`, `apps/accounts/tasks.py`, `tests/integration/test_account_retention.py`, `docs/foundation/BA-STAGE-2.5_REPORT.md` |

## BA-QUALITY-001 — coverage self-check, не аудит

| Поле | Значение |
|---|---|
| Тип | Технический замер coverage/CI-порог; не независимый аудит |
| Результат | `make coverage`; 2594 statements, 476 missed, **81.65 %**, порог 70 %; 177 passed, 2 skipped |
| Низкие модули | `hibp.py` 39 %, `health.py` 59 %, `ba_i18n.py` 63 %, `coverage.py` 36 %, `theme/views.py` 40 %, `storage.py` 0 % |
| Статус | **IMPLEMENTED / AWAITING INDEPENDENT REVIEW**; не приёмка §2.26 |
| Источник | `TASK_HISTORY.md`, `pyproject.toml`, `Makefile`, `docs/foundation/BA-QUALITY-001_REPORT.md` |

## BA-CATALOG-001 — техническая работа, не аудит

| Поле | Значение |
|---|---|
| Тип | Техническая реализация публичного каталога; не независимый аудит |
| Результат | `apps/catalog/services/catalog.py`; published-only list; genre/mobile/duration/q/sort; localized detail с fallback `en`; genre page; HTMX partial; home cards; 5 integration tests |
| Статус | **PARTIAL** (работы); full suite 182 passed, 2 skipped |
| Ограничения | Нет tags/доп. жанров (M2M), FTS/`pg_trgm`, ratings/popularity, coverage badge, play runtime |
| Источник | `TASK_HISTORY.md`, `tests/integration/test_catalog_public.py`, `docs/foundation/BA-CATALOG-001_REPORT.md` |

## BA-CATALOG-002 — техническая работа, не аудит

| Поле | Значение |
|---|---|
| Тип | Техническая реализация M2M жанров/тегов; не независимый аудит |
| Результат | `catalog.0003`; `GameGenre`/`GameTag`; `Game.additional_genres`/`tags`; фильтры по доп. жанру и мультивыбору тегов; 6 integration tests |
| Статус | **IMPLEMENTED / AWAITING INDEPENDENT REVIEW**; full suite 183 passed, 2 skipped |
| Ограничения | FTS/`pg_trgm`, ratings/popularity/coverage badge/play не покрыты |
| Источник | `TASK_HISTORY.md`, `tests/integration/test_catalog_public.py`, `docs/foundation/BA-CATALOG-002_REPORT.md` |

## BA-CATALOG-003 — техническая работа, не аудит

| Поле | Значение |
|---|---|
| Тип | Техническая реализация FTS/trigram; не независимый аудит |
| Результат | `SearchVector`/`SearchQuery` по name/short_description/description, `TrigramSimilarity`, fallback `icontains`; config из `Language.fts_config`/`simple`; 7 integration tests |
| Статус | **PARTIAL**; full suite 184 passed, 2 skipped |
| Ограничения | `search_vector` не заполняется, GIN по выражению нет, `unaccent`/ranking не применены |
| Источник | `TASK_HISTORY.md`, `apps/catalog/services/catalog.py`, `tests/integration/test_catalog_public.py`, `docs/foundation/BA-CATALOG-003_REPORT.md` |

## BA-CATALOG-004 — техническая работа, не аудит

| Поле | Значение |
|---|---|
| Тип | Техническая реализация persisted `search_vector`; не независимый аудит |
| Результат | post_save signal (SearchVector A/B/C, simple); `catalog.0004` backfill; stored vector + GIN в поиске; тест заполнения |
| Статус | **PARTIAL**; full suite 184 passed, 2 skipped |
| Ограничения | Нет `unaccent`, `SearchRank`, bulk/import refresh и проверки плана на объёме |
| Источник | `TASK_HISTORY.md`, `apps/catalog/signals.py`, `catalog/0004`, `docs/foundation/BA-CATALOG-004_REPORT.md` |

## BA-CATALOG-005 — техническая работа, не аудит

| Поле | Значение |
|---|---|
| Тип | Техническая реализация unaccent/ranking/bulk refresh; не независимый аудит |
| Результат | `Unaccent` Func в vector/query; `SearchRank`; Celery Beat `catalog.refresh_catalog_search_vectors`; backfill `catalog.0005`; 8 tests |
| Статус | **IMPLEMENTED / AWAITING INDEPENDENT REVIEW**; full suite 185 passed, 2 skipped |
| Ограничения | Нет benchmark/EXPLAIN на объёме, ratings/popularity/play |
| Источник | `TASK_HISTORY.md`, `apps/catalog/services/search.py`, `catalog/0005`, `docs/foundation/BA-CATALOG-005_REPORT.md` |

## Соотношение с BA-AUDIT-001

BA-AUDIT-001 (предшествующий аудит) выявил A-001–A-007 и стал основанием BA-FIX-001. Его постоянный отдельный файл в проекте отсутствует; сведения сохраняются в истории работ и в `TASK_HISTORY.md`. Он не является формальной приёмкой BA-STAGE-1.1.

## Пробелы доказательной базы

- Отдельные первичные отчёты BA-FIX-001 (i18n), BA-FIX-002, BA-FIX-003,
  BA-AUDIT-002, BA-AUDIT-003 и BA-STAGE-1.1 в файлах не найдены; записи
  реестров являются вторичными источниками и не выдаются за полный лог.
- `reports/BA_AUDIT_20261118_162920.zip` — generated-отчёт, в котором
  BA-FIX-001 обозначен как настройка AI-среды; это не отчёт об
  i18n-исправлениях и не доказательство приёмки.
- Наличие JSON Schema/валидатора App F не является доказательством работающей
  реализации; см. `BA-AUDIT-APP-F-REPORT.md`.

## BA-FOUNDATION-002 — пакет для независимого аудита

| Поле | Значение |
|---|---|
| Тип | Не аудит; подготовительный пакет BA-FOUNDATION-002 |
| Цель | Подготовить DRAFT SDK/ENV, message schemas, проектную схему БД/ERD, App J mapping, digest/CI для независимой проверки |
| Итоговый статус | Partial/Blocked; независимая проверка ещё не выполнена |
| Блокеры | отсутствие оригиналов BA-SDK-1.1/BA-ENV-1.1, неутверждённые payload-схемы, неполная production-инфраструктура, base image digest |
| Артефакты | `docs/contracts/`, `docs/foundation/`, `schemas/messages/`, `docs/foundation/BA-FOUNDATION-002_REPORT.md` (запрошенный `reports/...` заблокирован guard-хуком) |
| Примечание | Не считать этот раздел независимым аудитом или приёмкой этапа 0 |

## BA-AUTONOMY-003 — AI infrastructure (техническая работа)

| Поле | Значение |
|---|---|
| Тип | Техническая работа по AI-инфраструктуре; не независимый аудит этапа |
| Цель | Pro text-only планирование/review, Flash-исполнение; guards; изоляция `ba`/`ai-dev`; NOW; указатели |
| Результат | `ba-plan`; обновлены skills/agents/settings; `bash_guard.py`; `ai-dev/.claude` guard; `NOW.md`; docs pointer fixes; `ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-v4-pro` |
| Проверки | `make test` 185 passed, 2 skipped; `make lint` 333; `make types` 316; guard tests 19/19 и 16/16 |
| Статус | **IMPLEMENTED / AWAITING OWNER ACCEPTANCE** |
| Review | Независимый Pro security-review — **accept** (2026-11-20); findings 1–8 исправлены; остаточный R-027 принят; owner acceptance pending |
| Ограничения | R-026 (Pro leading-only), R-027 (guard heuristic), R-028 (ai-dev registration), R-029 (context drift) |
| Источник | `TASK_HISTORY.md`, `docs/tasks/BA-AUTONOMY-003_PLAN.md`, `docs/foundation/BA-AUTONOMY-003_REPORT.md` |

## APPF-SESSION-001 — серверный session/ticket срез App F (техническая работа)

| Поле | Значение |
|---|---|
| Тип | Техническая реализация App F §2.12.1–2.12.4; не независимый аудит этапа |
| Цель | GameSession, одноразовый launch ticket, активация, heartbeat, CSRF, throttle, лимит ≤3 активных |
| Результат | Модель + миграции 0001/0002; сервисы; `POST /api/v1/sessions`, `/activate`, `/heartbeat`; 24 integration tests (3 конкурентных); исправлен обход лимита через активацию и дефект миграции свежей БД |
| Проверки | `pytest` 209 passed, 2 skipped; модуль 24 passed; `make lint` 335; `make types` 317; `makemigrations --check` — no changes; `migrate --plan` — пусто; `./verify_stack.sh` — здоров |
| Статус | **ACCEPTED владельцем 2026-11-20** (OD-STATUS-007); evidence — `APPF-SESSION-001_REVIEW_EVIDENCE.md` |
| Review | `code-reviewer` + `security-auditor` (deepseek-v4-pro, text-only) — оба **accept** после раунда исправлений (throttle по живой identity, конкурентные тесты, None-guard) |
| Ограничения | subject без FK до DB-001; [PROP]-контракт context; retention GameSession §2.22; R-030; graph-правка `catalog.0001` — осознанное исключение |
| Источник | `TASK_HISTORY.md`, `docs/tasks/APPF-SESSION-001_PLAN.md`, `docs/foundation/APPF-SESSION-001_REPORT.md` |

## APPF-SESSION-002 — throttle hardening (техническая работа)

| Поле | Значение |
|---|---|
| Тип | Техническая реализация Приложения E; не аудит этапа |
| Цель | subject/IP-лимиты, heartbeat на сессию, structured 429, redis-throttle, реальный IP |
| Результат | Throttle-классы, ClientIPMiddleware, exceptions handler, redis-throttle, +13 тестов |
| Проверки | 37 session tests; полный suite 241/2 skipped; lint/types/migrations; XFF end-to-end |
| Статус | **IMPLEMENTED / AWAITING OWNER ACCEPTANCE** |
| Review | code-reviewer/security-auditor — блокеров нет; staging smoke и узкий TRUSTED_PROXY_IPS — pre-prod |
| Источник | `docs/foundation/APPF-SESSION-002_REPORT.md` |

## APPF-RESULT-001 — результат и рекорды (техническая работа)

| Поле | Значение |
|---|---|
| Тип | Техническая реализация §2.11–§2.13/§2.22–§2.23; не аудит этапа |
| Цель | `POST /sessions/{id}/result`, GameResult, LeaderboardEntry, DB-001/002/003 |
| Результат | Модели/миграции 0003–0005, API, триггеры, идемпотентность, 19 tests (100 parallel) |
| Проверки | 19 result tests; полный suite 241/2 skipped; lint/types/migrations |
| Статус | **IMPLEMENTED / AWAITING OWNER ACCEPTANCE** |
| Review | code-reviewer/security-auditor — **accept**, блокеров нет; retention JSONB — owner |
| Источник | `docs/foundation/APPF-RESULT-001_REPORT.md` |

## APPF-LEADERBOARD-001 — публичный API рекордов (техническая работа)

| Поле | Значение |
|---|---|
| Тип | Техническая реализация §2.11/§2.23; не аудит этапа |
| Результат | `GET games/{id}/leaderboard?limit=10|100`, `/me/best`; порядок/tie-break, me, published-only, read-throttle |
| Проверки | 7 tests; полный suite 260/2 skipped; lint/types |
| Статус | **IMPLEMENTED / AWAITING OWNER ACCEPTANCE** |
| Review | code-reviewer/security-auditor — **accept**; nickname-публичность — owner-верификация |
| Источник | `docs/foundation/APPF-LEADERBOARD-001_REPORT.md` |

## APPF-STORAGE-001 — хранилище игры (техническая работа)

| Поле | Значение |
|---|---|
| Тип | Техническая реализация §2.22/§2.23; DB-008 делегирован |
| Результат | `GET/PUT games/{id}/storage`; 64 КиБ, revision/If-Match, TTL гостя, активная сессия + 60/min, trigger `pg_column_size` |
| Проверки | 12 tests (гонка create, cleanup); полный suite 260/2 skipped; lint/types/migrations |
| Статус | **IMPLEMENTED / AWAITING OWNER ACCEPTANCE** |
| Review | code-reviewer/security-auditor — **accept** после устранения blockers; sliding TTL/retention — owner |
| Источник | `docs/foundation/APPF-STORAGE-001_REPORT.md` |

## APPF-PLAYTIME-001 — подтверждённое игровое время (техническая работа)

| Поле | Значение |
|---|---|
| Тип | Техническая реализация §2.12.3; не аудит этапа |
| Результат | `UserGamePlaytime`, зачёт credited_ms только mode=user, удаление при анонимизации, race-safe upsert |
| Проверки | 40 session tests (включая параллельные heartbeat); full 273/2 skipped; lint/types/migrations |
| Статус | **IMPLEMENTED / AWAITING OWNER ACCEPTANCE** |
| Review | code-reviewer/security-auditor — **accept** |
| Источник | `docs/foundation/APPF-PLAYTIME-001_REPORT.md` |

## APPF-RATINGS-001 — оценки игр (техническая работа)

| Поле | Значение |
|---|---|
| Тип | Техническая реализация §2.9; не аудит этапа |
| Результат | `GameRatingVote`/`GameRatingAggregate`, порог playtime, возраст, 1/24ч, 5/30д, 20/сутки, транзакционный агрегат, публичный summary |
| Проверки | 10 tests (включая гонки); full 273/2 skipped; lint/types/migrations |
| Статус | **IMPLEMENTED / AWAITING OWNER ACCEPTANCE** |
| Review | code-reviewer/security-auditor — **accept**; антифрод §2.9.6 — owner-gap |
| Источник | `docs/foundation/APPF-RATINGS-001_REPORT.md` |

## APPF-POPULARITY-001 — популярность и close (техническая работа)

| Поле | Значение |
|---|---|
| Тип | Техническая реализация §2.8; не аудит этапа |
| Результат | `GamePlayCredit`/`GameDailyStats`, зачёт завершения (≥15 с, user/guest, окно 30 мин), `POST /sessions/{id}/close`, серверная длительность в гейте |
| Проверки | 8 tests (гонки, UTC-границы, expired heartbeat, ownership); full 281/2 skipped; lint/types/migrations |
| Статус | **IMPLEMENTED / AWAITING OWNER ACCEPTANCE** |
| Review | code-reviewer/security-auditor — **accept**; R-032 guest identity inflation — owner-gap |
| Источник | `docs/foundation/APPF-POPULARITY-001_REPORT.md` |

## BA-ZIP-PREFLIGHT-001 — безопасная проверка ZIP (техническая работа)

| Поле | Значение |
|---|---|
| Тип | Техническая реализация §2.14.2/§2.14.7; не аудит этапа |
| Результат | Metadata-only `preflight_zip`: пути/типы/лимиты/коллизии/расширения/служебные файлы, SHA-256, стабильные diagnostics; без распаковки и исполнения |
| Проверки | 16 unit tests (path traversal, canonical/duplicate, symlink, encryption, forged sizes, NFKC, ZIP bomb, DD/ZIP64); full suite 297/2 skipped; ruff/mypy зелёные |
| Статус | **TECHNICALLY ACCEPTED** (agent, OD-TECH-001); продуктовая приёмка — владелец |
| Review | code-reviewer — **accept**; security-auditor — **ACCEPT** после исправления M-1/M-2/m-1/m-3/m-6; остаток O-1…O-5/m-4…m-7 — R-034 (non-blocking) |
| Источник | `docs/foundation/BA-ZIP-PREFLIGHT-001_REPORT.md` |

## BA-ZIP-EXTRACT-001 — безопасная распаковка ZIP (техническая работа)

| Поле | Значение |
|---|---|
| Тип | Техническая реализация §2.14.2; не аудит этапа |
| Результат | Повторный preflight; streaming 64 КиБ; независимый byte count; лимиты 20/100 МБ, 2000 файлов; CRC; канонические пути; prefix-конфликты; O_EXCL/O_NOFOLLOW; atomic rename; cleanup |
| Проверки | 11 unit tests (valid/hashes, limits, CRC, prefix, deep path/dirs, mutable data, destination exists, deadline/cleanup, symlink preflight); full 308/2 skipped; ruff/mypy |
| Статус | **TECHNICALLY ACCEPTED** (agent, OD-TECH-001); продуктовая приёмка — владелец |
| Review | security-auditor — **ACCEPT** после MINOR-1…6/A/B; остаток durability/error taxonomy — R-035 |
| Источник | `docs/foundation/BA-ZIP-EXTRACT-001_REPORT.md` |

## BA-ZIP-WORKER-001 — изолированный extraction worker

| Поле | Значение |
|---|---|
| Тип | Техническая реализация §2.14.2; не аудит этапа |
| Результат | Отдельный `zip-worker` в `zipnet` только с broker; prefork 1; read_only/cap_drop/no-new-privileges/pids/mem/cpus/tmpfs; uploads ro / artifacts rw; O_NOFOLLOW/O_NONBLOCK + fstat + `/proc/self/fd`; flock; statvfs; ATTEMPTS/quarantine; CANCEL + cancel_check; JSON-аудит; cleanup |
| Проверки | 22 new tests; full 330/2 skipped; ruff/mypy; compose config; E2E web→zip-worker→COMPLETED; network probes (db/cache/internet gaierror); queue bindings zip/zip |
| Статус | **TECHNICALLY ACCEPTED** (agent, OD-TECH-001); продуктовая приёмка — владелец |
| Review | План: code/security **accept** after conditions; реализация: security **ACCEPT**, code **ACCEPT** с pre-existing R-036; остатки R-033/R-035/R-036/R-037 |
| Источник | `docs/foundation/BA-ZIP-WORKER-001_REPORT.md` |

## BA-DEVCONTROL-001 — Telegram Dev Control

| Поле | Значение |
|---|---|
| Тип | Инфраструктурный компонент; не аудит этапа |
| Результат | Отдельный stdlib-сервис: owner-only Telegram long polling, команды/кнопки, `claude --bg`/agents/logs/stop, state/events/inbox, hooks Stop/PermissionRequest/SessionEnd, systemd unit |
| Проверки | 31 unit tests; full 360/3 skipped; ruff/mypy; live `--bg` probe; Stop hook `turn_done`; sandbox test runner (real test passed, exit 0, no leftovers); hardened permissions |
| Статус | **TECHNICALLY ACCEPTED** (agent); live Telegram/token setup pending |
| Review | code-reviewer — **ACCEPT**; security-auditor — **ACCEPT** после sandbox test runner, env/permissions hardening, git history narrowing; residual R-038/R-039 non-blocking |
| Источник | `docs/foundation/BA-DEVCONTROL-001_REPORT.md` |

## BA-ZIP-HARDENING-001 (R-035) — durability/error taxonomy

| Поле | Значение |
|---|---|
| Тип | Техническая hardening-работа; не аудит этапа |
| Результат | Method allowlist stored/deflate; fsync файлов + staging/destination dirs; fsync COMPLETED/ATTEMPTS/audit; read `X_ARCHIVE_BAD` / write `X_IO` |
| Проверки | 54 ZIP tests; full 369/3 skipped; ruff/mypy; benchmark 2000 files 7.7s |
| Статус | **TECHNICALLY ACCEPTED** (agent); product — owner |
| Review | code-reviewer — **ACCEPT**; security-auditor — **ACCEPT** (local method validation, CRC/truncation split, preflight allowlist, benchmark) |
| Остаток | Directory fsync best-effort; close OSError edge; per-file fsync overhead |
| Источник | `docs/foundation/BA-ZIP-HARDENING-001_REPORT.md` |

## BA-QUALITY-002 — search benchmark/GIN/coverage

| Поле | Значение |
|---|---|
| Тип | Техническая quality-работа; не аудит этапа |
| Результат | Dev-only benchmark/EXPLAIN; existing GIN search_vector подтверждён (10k FTS 2.4 мс); trigram/unaccent GIN не обоснован; coverage 90.88 %, <70 % нет |
| Проверки | 397/3 skipped; ruff/mypy; coverage 90.88 %; benchmark 1k/10k |
| Статус | **TECHNICALLY ACCEPTED** (agent); product — owner |
| Review | code-reviewer — **ACCEPT**; security-auditor — **ACCEPT** (dev-only guard, DDL cleanup, SQL constants) |
| Остаток | Full OR 10k ~150 мс — Seq Scan; изменение формы запроса — продуктовое решение |
| Источник | `docs/foundation/BA-QUALITY-002_REPORT.md` |

## R-036 — анализ глобального `CELERY_TASK_ACKS_LATE`

| Поле | Значение |
|---|---|
| Тип | Текстовый архитектурный анализ; не аудит этапа |
| Результат | Семантика ack/redelivery Celery 5.7+Redis, матрица задач, варианты A–F, рекомендация F; проверены defaults, visibility_timeout 3600, prefork/solo, идемпотентность |
| Статус | **ANALYSIS COMPLETED / AWAITING OWNER DECISION**; поведение не изменялось |
| Решение владельца | Phase 2 (idempotency + reject для backup/restore/anonymize), задержка redelivery, отдельный worker — не принято |
| Источник | `docs/foundation/R-036_ACKS_LATE_ANALYSIS.md` |

## R-036 Phase 1 — delivery observability (non-behavioral)

| Поле | Значение |
|---|---|
| Тип | Техническая наблюдаемость; не аудит этапа |
| Результат | `celery.task.received`/`failure`/`retry`/worker shutdown только с безопасными полями; docstrings R-036; 5 контрактных тестов; live `received` в worker |
| Проверки | 402 passed, 3 skipped; ruff/format/mypy clean |
| Статус | **TECHNICALLY ACCEPTED** (agent); поведение доставки не изменялось |
| Review | code-reviewer — **ACCEPT**; security-auditor — **ACCEPT**; minor fixes: lock, partial write, string hostname; residual — нет throttling fd-2 |
| Phase 2 | **AWAITING OWNER DECISION** (idempotency guards, reject, visibility timeout, worker) |
| Источник | `docs/foundation/R-036_PHASE1_REPORT.md` |

## BA-APPF-002 / DB-001 — tombstone-анонимизация сессий при удалении

| Поле | Значение |
|---|---|
| Тип | Техническая privacy-доработка approved DB-001; owner chose tombstone |
| Результат | Все сессии пользователя получают subject_type=deleted + random UUID; created/active aborted + ticket/binding cleared; finished/expired state kept; migration gameplay.0011 |
| Проверки | 403 passed, 3 skipped; ruff/format/mypy clean; makemigrations/migrate --plan clean; 0011 applied |
| Статус | **TECHNICALLY ACCEPTED** (agent); first review reject, re-review accept |
| Review | code-reviewer — **ACCEPT** (after tombstone/lock); security-auditor — **ACCEPT** (after tombstone/lock); blockers/majors нет |
| Остаток | Retention сессий/результатов APPF-OD-030 не утверждён; строгая гарантия после удаления — за счёт порядка row-lock, без DB-trigger |
| Источник | `docs/foundation/BA-APPF-002_DB001_SESSION_CLEANUP_REPORT.md` |

## BA-APPF-002 / DB-006 — immutable GameVersion

| Поле | Значение |
|---|---|
| Тип | Техническая integrity-доработка approved DB-006 |
| Результат | model `save()` guard + PostgreSQL trigger; content/hash/version immutable; audit FKs only unchanged/→NULL; SET_NULL user deletion works |
| Проверки | 419 passed, 3 skipped; ruff/format/mypy clean; 16 targeted tests; makemigrations/migrate --plan clean; 0006/0007 applied |
| Статус | **TECHNICALLY ACCEPTED** (agent) |
| Review | security-auditor — **ACCEPT**; code-reviewer — **ACCEPT** |
| Остаток | 0006/0007 intermediate; strict `manual_review_at`; `GameVersion.game` CASCADE/DB-004 вне scope |
| Источник | `docs/foundation/BA-APPF-002_DB006_REPORT.md` |

## BA-APPF-002 / DB-005 + DB-007 — public name и mode↔subject

| Поле | Значение |
|---|---|
| Тип | Schema/integrity доработка approved DB-005/007 |
| Результат | GameTranslation.name 60; GameSession CHECK user/guest/preview/autotest + deleted tombstone |
| Проверки | 433 passed, 3 skipped; 14 targeted; ruff/format/mypy clean; migrations 0008/0012 applied; makemigrations/migrate --plan clean |
| Статус | **TECHNICALLY ACCEPTED** (agent) |
| Review | code-reviewer/security-auditor — см. итог |
| Остаток | DB-005 precheck блокирует длинные имена без truncation; tombstone aggregates/mode immutability — отдельные срезы; preview/autotest creation flow отсутствует |
| Источник | `docs/foundation/BA-APPF-002_DB005_DB007_REPORT.md` |

## BA-APPF-002 / DB-004 + DB-001/DB-007 residuals

| Поле | Значение |
|---|---|
| Тип | Integrity/privacy residual доработка |
| Результат | Game identity immutable после публикации + DELETE forbidden; GamePlayCredit cleanup; GameSession.mode immutable |
| Проверки | 441 passed, 3 skipped; 5 targeted; ruff/format/mypy clean; catalog.0009/gameplay.0013 applied; migration check/plan clean |
| Статус | **TECHNICALLY ACCEPTED** (agent) |
| Review | code-reviewer — **ACCEPT**; security-auditor — **ACCEPT** |
| Остаток | GameDailyStats не пересчитывается; DELETE всех Game запрещён (архив — статус); mode immutable |
| Источник | `docs/foundation/BA-APPF-002_DB004_RESIDUALS_REPORT.md` |

## BA-APPF-002 — App F runtime/SDK/player, срез A+B

| Поле | Значение |
|---|---|
| Тип | Runtime/SDK/iframe/player implementation |
| Результат | official SDK, host protocol, player host, play view server-side activation, exact runtime origin/full hash, CSRF relay, guest normalization |
| Проверки | 456 passed, 4 skipped; 3 play tests + 4 static SDK checks + 2 runtime E2E + 4 JS host tests + eventLog/verifier validation; ruff/format/mypy clean; node --check clean |
| Статус | **IMPLEMENTED / TECHNICAL REVIEW**; BA-SDK-1.1 submitted not approved |
| Review | code-reviewer — INCOMPLETE; security-auditor — INCOMPLETE (diff evidence, parentOrigin residual); probe/E2E 2 passed |
| Остаток | JS schema validation, snake/camel API adapter, retry policy, staging/prod origin, static collectstatic perms |
| Источник | `docs/foundation/BA-APPF-002_RUNTIME_SDK_REPORT.md` |

## AUTONOMY-AUDIT-2026-11-23 — проверка AI Headquarters

| Поле | Значение |
|---|---|
| Тип | Read-only аудит оркестрации/Dev Control; не product acceptance |
| Результат | A PASS (код), D PASS (код)/NOT TESTED live; B/C/E FAIL/NOT TESTED; `.autonomy` и systemd user units/timers отсутствуют; Telegram API timeout |
| Проверки | autonomy/devcontrol tests 94 passed, 1 skipped; full 981/12; `claude agents --json` — только текущая interactive-сессия |
| Статус | **COMPLETED / AUDIT ONLY** |
| Остаток | `AUTONOMY-CONTINUATION-001` — BLOCKED owner; timer не устанавливался |

## APPF-RUNTIME-REVIEW-001 — App F Runtime

| Поле | Значение |
|---|---|
| Тип | Независимое техническое/security ревью runtime A+B/C |
| Результат | stale-response guard, newSession close, per-session Idempotency-Key, host validation; JS/negative tests |
| Проверки | targeted pytest 79 passed; npm test:js 7 passed; check:js clean; full suite — см. отчёт |
| Статус | **IMPLEMENTED / INDEPENDENT REVIEW ACCEPT**; product/staging/prod — owner |
| Review | code-reviewer + security-auditor — **ACCEPT** после delta |
| Остаток | race/idempotency tests, server cross-check, R-036 Phase 2, R-043/44/45 |
| Источник | `docs/foundation/APPF-RUNTIME-REVIEW-001_REPORT.md` |

## BA-TOKEN-OBSERVABILITY-001 — metadata-only учёт invocations

| Поле | Значение |
|---|---|
| Тип | Техническая instrumentation; execution behavior не менялся |
| Результат | `autonomy/observability.py`; `RunResult` optional fields; `invocations.jsonl`; task/attempt/agent/role/session/invocation, Claude-reported cache/cost, optional num_turns |
| Проверки | observability 8 passed; autonomy/devcontrol/vps subset 100 passed/1 skipped; full suite exit 0; ruff/format/mypy clean |
| Статус | **IMPLEMENTED / INDEPENDENT REVIEW ACCEPT** |
| Review | code-reviewer ACCEPT; minor fixes applied; provider request_count/cache unavailable, documented |
| Источник | `docs/audits/BA_TOKEN_OBSERVABILITY_IMPLEMENTATION_REPORT.md` |

## Общие ограничения

- Аудит не закрывает BA-FIX-001 и не принимает BA-STAGE-1.1.
- Прохождение тестов не считается приёмкой.
- Статус «Fixed» в аудите означает исправление конкретного замечания, а не закрытие этапа.
- Открытые риски перечислены в `docs/risks/RISK_REGISTER.md`; не считать их исправленными.
- Нормативные ТЗ и отсутствующие BA-SDK-1.1/BA-ENV-1.1 не заменяются выводами аудита.

## BA-AUTONOMY-004 — AI task control plane

| Поле | Значение |
|---|---|
| Тип | AI infrastructure / routing / queue |
| Результат | durable queue, Pro Architect/Reviewer + Flash Developer/QA, modelUsage evidence, auto-next, recovery, completed dedup |
| Проверки | 670 passed, 4 skipped; 13 autonomy tests; 193 guard tests; ruff/format/mypy clean |
| Статус | **TECHNICALLY ACCEPTED** (independent Pro review); product acceptance owner |
| Остаток | no isolated worktree; reviewer does not rerun full suite; no OS sandbox |
| Источник | `docs/foundation/AI_AUTONOMY_EVIDENCE.md` |


## BA-AUTONOMY-005 — bounded control-plane hardening package

| Поле | Значение |
|---|---|
| Тип | Worktree reliability / limits / isolation / notifications / VPS prep |
| Результат | 5 large tasks accepted by independent Pro review; no sixth task created |
| Проверки | 720 passed, 11 skipped; ruff/format/mypy clean |
| Статус | **TECHNICALLY ACCEPTED** (agent); product/infrastructure activation owner |
| Остаток | R-040 OS sandbox; live Telegram/VPS not exercised; sandbox scripts/ copy gap |
| Источник | `docs/foundation/AI_AUTONOMY_EVIDENCE.md` |

## BA-PRODUCT-ROADMAP-001 — Browser Arcade / App F сверка с ТЗ

| Поле | Значение |
|---|---|
| Тип | Read-only product/roadmap audit |
| Результат | Фактическое состояние отделено от нормативного плана; работы разделены на A/B/C; зафиксированы внешние блокеры и крупные этапы |
| Проверки | Сверены BA-PLAT-4.2, BA-GAME-2.2, BA-SDK/ENV, NOW/PROJECT_STATUS/BACKLOG, код, маршруты, пустые модули и тесты; полный gate 792 passed, 11 skipped |
| Статус | AUDIT COMPLETE; implementation не запускалась |
| Остаток | App F/pipeline/CRM/legal/production остаются незакрытыми |
| Источник | `docs/foundation/BA_PRODUCT_ROADMAP_AUDIT.md` |

## ARCADE-P0/P1/P2 — technical acceptance 2026-11-22

| Поле | Значение |
|---|---|
| Тип | Product/App F implementation wave |
| Результат | P0 ADR-APPF-001; P1 ratings/leaderboard + SEO/i18n/a11y; P2 ZIP pipeline, CRM games/wizard/roles/moderation/content-analytics |
| Проверки | Full fresh gate 917 passed, 12 skipped; each package: Developer self-check, Flash QA, independent Pro Reviewer; evidence in `.autonomy/evidence/` |
| Статус | TECHNICALLY ACCEPTED; product acceptance owner; external actions not performed |
| Остаток | Real game/rights, legal texts, email provider, domains/TLS, S3/CDN/hosting/DR, production deploy; App F runtime product review |
| Источник | `docs/handoff/NOW.md`, `docs/status/PROJECT_STATUS.md`, commits `7c56f93`…`11c9805` |

## ARCADE-P3-ZIP-WORKER-INTEGRATION-001 — isolated extraction

| Поле | Значение |
|---|---|
| Тип | Security/architecture integration |
| Результат | Product import only enqueues isolated zip-worker; source/hash verification; cleanup task on writable default worker; runtime volume/base init for environments |
| Проверки | Pro Review accept after two findings fixed; live CRM upload → `ZipExtractionJob completed`; worker logs; source removed; cleanup task live; full gate 930 passed, 12 skipped; E2E 18 |
| Статус | TECHNICALLY ACCEPTED; product acceptance owner |
| Остаток | Staging live runtime/backup NOT TESTED (`.env.staging` absent); R-033/R-037; real game/email/legal/domains/TLS/S3/deploy external |
| Источник | `docs/foundation/PRODUCT_ACCEPTANCE_REPORT.md`, commits `021a36c`…`9017254` |

## BA-TOKEN-OBSERVABILITY-002 — invocation lifecycle

| Поле | Значение |
|---|---|
| Тип | Technical instrumentation; execution behavior не менялся |
| Результат | Schema v2 start/finish events; failed/timeout/cancelled/interrupted; reconciliation по owner pid/PID reuse/boot_id; runner — единственный писатель; `_account` — success-only state/budget; manual `python -m autonomy.observability reconcile` |
| Проверки | 30 observability tests; targeted autonomy subset; ruff/format/mypy clean; full suite exit 0 (final count — в отчёте); реальный control run: 5 scenarios, 5 started/5 finished |
| Статус | **IMPLEMENTED / INDEPENDENT REVIEW ACCEPT** (minor fixes applied) |
| Review | `code-reviewer` ACCEPT после delta: by_status zeros, abandoned start, SIGINT window, manual CLI, недостающие тесты, ERROR_TYPES/reasoning исправлены |
| Остаток | Timeout/cancel/interrupted usage неизвестен; provider request_count/cache/invoice; SIGKILL child; нет ротации |
| Источник | `docs/audits/BA_TOKEN_OBSERVABILITY_002_IMPLEMENTATION_REPORT.md` |

## BA-TOKEN-EFFICIENCY-OPTIMIZATION-001 — practical context reduction

| Поле | Значение |
|---|---|
| Тип | Prompt/documentation optimization; no model/routing/budget changes |
| Результат | Architect brief + targeted reads; context discipline developer/QA/reviewer; session hygiene runbook |
| Проверки | Обязательный bundle 168 145→5 011 chars (−97.0 %); реальная пара planning calls: input 132 148→59 430 (−55.0 %), cost 1.617→1.205 USD (−25.5 %), output +48.8 %, num_turns 32→39; оба proposal валидны (4/3 задачи) |
| Статус | **IMPLEMENTED; effect measured (single pair, indicative)** |
| Остаток | Интерактивные сессии вне journal; tool-loop не ограничен hard cap; один запуск на фазу |
| Источник | `docs/audits/BA_TOKEN_EFFICIENCY_OPTIMIZATION_REPORT.md` |


## APPF-RUNTIME-REVIEW-001 — stale/idempotency delta tests

| Поле | Значение |
|---|---|
| Тип | Test-only delta; production code не менялся |
| Результат | `tests/js/player_race.test.mjs`: stale submit success/error, leaderboard, storage после newSession; same-session Idempotency-Key reuse; fresh key для новой сессии; `tests/integration/test_migrations_check.py` guard |
| Проверки | `npm run test:js` 8 entries / 0 failed; `npm run check:js` clean; migration guard 1 passed |
| Review | `code-reviewer` ACCEPT после исправления vacuous deferred-ответов |
| Статус | **IMPLEMENTED / INDEPENDENT REVIEW ACCEPT**; product/staging/prod не заявляются |
| Остаток | Live browser E2E/staging/prod NOT TESTED; server cross-check strictness NOT TESTED |
| Источник | `docs/foundation/APPF-RUNTIME-REVIEW-001_DELTA_TESTS.md` |

## ARCADE-RETENTION-001 — App F retention cleanup

| Поле | Значение |
|---|---|
| Тип | Product/ops implementation via AI HQ; no schema change |
| Результат | `8e42426`: gameplay/pipeline retention services + Celery tasks + daily beat; sessions 30d excluding result-linked, credits 90d, drafts 7d, guest storage TTL |
| Проверки | 8 retention tests; `test_migrations_check.py` pass; targeted ruff/mypy clean; AI HQ QA exit 0; independent reviewer accept; full suite 1028 tests / 1020 passed / 8 skipped / exit 0 |
| Статус | **COMPLETED / AI HQ REVIEWER ACCEPT**; product/staging/prod не заявляются |
| Остаток | no index on purge timestamps; concurrent result insert → ProtectedError/retry; live beat NOT TESTED |
| Источник | commit `8e42426`; QA/reviewer evidence в `.autonomy/evidence/` |


## ARCADE-CATALOG-SLUG-301-001 — slug history / 301

| Поле | Значение |
|---|---|
| Тип | Product/SEO implementation via AI HQ; migration added |
| Результат | `cf0936c`: `GameSlugHistory` + запись старого slug при изменении Game/GameTranslation; game_detail 301 на canonical, unknown 404 |
| Проверки | 5 slug tests; migration guard; catalog public/SEO 16 tests; ruff/mypy clean; full suite 1033/1025/8 exit 0; AI HQ reviewer accept |
| Статус | **COMPLETED / AI HQ REVIEWER ACCEPT**; product/staging/prod не заявляются |
| Остаток | cross-language negative redirect test absent; `FALLBACK_LANGUAGE_CODE` duplicated with SEO/sitemap; concurrent get_or_create race not tested |
| Источник | commit `cf0936c`; `.autonomy/evidence/qa-26588089-*.json`, reviewer evidence |


## ARCADE-CRM-SEO-DIAGNOSTICS-001 — CRM SEO diagnostics

| Поле | Значение |
|---|---|
| Тип | Product/CRM implementation via AI HQ; no schema/contract change |
| Результат | `f5474d8`: read-only `/crm/seo/` screen + `seo_diagnostics` service; empty descriptions, duplicate titles, missing alt, incomplete translations; per-language summary; links; `GAMES_VIEW` gating |
| Проверки | 11 tests (queries, summary, screen links, role matrix, anonymous redirect); ruff/mypy clean; full suite 1044/1036/8 exit 0; AI HQ reviewer accept без findings |
| Статус | **COMPLETED / AI HQ REVIEWER ACCEPT**; product/staging/prod не заявляются |
| Остаток | large-catalog performance NOT TESTED; staging/prod NOT TESTED |
| Источник | commit `f5474d8`; QA/reviewer evidence в `.autonomy/evidence/` |


## ARCADE-SLUG-HISTORY-HARDENING-001 — slug residuals

| Поле | Значение |
|---|---|
| Тип | Minor hardening via AI HQ; no schema/contract change |
| Результат | `bf33191`: IntegrityError re-fetch в record helpers; общий `FALLBACK_LANGUAGE_CODE`; cross-language negative + concurrent-insert tests |
| Проверки | 7 slug tests; migration guard; ruff/mypy clean; AI HQ reviewer accept (2 minor notes); full suite 1046 tests / 1038 passed / 8 skipped / exit 0 |
| Статус | **COMPLETED / AI HQ REVIEWER ACCEPT**; product/staging/prod не заявляются |
| Остаток | concurrent test использует mock, не реальную двухтранзакционную гонку |
| Источник | commit `bf33191`; QA/reviewer evidence в `.autonomy/evidence/` |


## ARCADE-CRM-USERS-001 — CRM customer accounts

| Поле | Значение |
|---|---|
| Тип | Product/CRM implementation via AI HQ; security-sensitive |
| Результат | `4095ed8` + fixes: `/crm/users/` search/filters/detail, block/unblock audit, deletion window/confirm, export via shared service; step-up export/delete; staff-target/tombstone guards; pagination; epoch filter |
| Проверки | 19 targeted tests; ruff/format/mypy clean; AI HQ code reviewer accept; security-auditor conditional → delta **resolved**; full suite 1064 tests / 1056 passed / 8 skipped / exit 0 |
| Статус | **COMPLETED / CODE REVIEW ACCEPT; SECURITY DELTA RESOLVED**; product/staging/prod не заявляются |
| Остаток | R-049: block не отзывает game SDK sessions/launch tickets; tombstone password/TOTP retention; live CSRF/HTTP not tested |
| Источник | commit `4095ed8` + security fix commit; evidence в `.autonomy/evidence/` |


## ARCADE-CRM-TAXONOMY-001 — CRM genre/tag CRUD

| Поле | Значение |
|---|---|
| Тип | Product/CRM implementation via AI HQ; choices-only audit migration |
| Результат | `98b848c` + fixes: genre/tag CRUD routes, translations, image/sort_order, delete guards, requires-translation queue, audit |
| Проверки | 9 taxonomy tests; ruff/mypy clean; AI HQ reviewer accept; full suite 1072/1064/8 exit 0; minors fixed (queue case, image cleanup, slug validation) |
| Статус | **COMPLETED / AI HQ REVIEW ACCEPT**; product/staging/prod не заявляются |
| Остаток | new upload rollback may leave an orphan file; staging/prod NOT TESTED |
| Источник | commit `98b848c` + minor-fix commit; evidence в `.autonomy/evidence/` |


## ARCADE-CRM-RATINGS-001 — ratings moderation filters/summary

| Поле | Значение |
|---|---|
| Тип | Product/CRM implementation via AI HQ; no schema/contract change |
| Результат | `c577416` + fixes: фильтры game/value/visibility, overall average + per-value distribution, hide/restore/audit сохранены |
| Проверки | 25 targeted tests; ruff/mypy clean; AI HQ reviewer accept; full suite 1075/1067/8 exit 0; minors fixed (summary-scope note, no filter truncation) |
| Статус | **COMPLETED / AI HQ REVIEW ACCEPT**; product/staging/prod не заявляются |
| Остаток | строки сверх 100 не пагинируются (disclosed); staging/prod NOT TESTED |
| Источник | commit `c577416` + minor-fix commit; evidence в `.autonomy/evidence/` |


## ARCADE-R049-SESSION-REVOCATION-001 / ARCADE-R049-TOMBSTONE-CREDENTIALS-001 — R-049 follow-ups

| Поле | Значение |
|---|---|
| Тип | Product/security implementation via AI HQ; no schema/public-contract change |
| Результат | `a9e7d2b`: block абортирует created/active SDK-сессии, сжигает tickets, unblock no-op; `08ab9c7`: tombstone удаляет password/TOTP/recovery credentials |
| Проверки | QA pass; 17 + 18 targeted tests, DB-001/CRM delete checks, migration guard clean; ruff clean; mypy — только pre-existing stub; reviewer accept; full suite 1079/1071/8 exit 0 |
| Статус | **COMPLETED / AI HQ REVIEW ACCEPT**; product/staging/prod не заявляются |
| Остаток | R-049: узкая гонка create_session с revoke-сканом; inverse ordering оставляет finished result намеренно; live SDK/staging NOT TESTED |
| Источник | commits `a9e7d2b`, `08ab9c7`; evidence в `.autonomy/evidence/` |


## ARCADE-ARTIFACTS-DOWNLOAD-001 — CRM artifact downloads

| Поле | Значение |
|---|---|
| Тип | Product/CRM implementation via AI HQ; security-sensitive download paths |
| Результат | `f8c3a52` + `91c9c0f`: original ZIP byte-exact, runtime zip, validation/autotest/import reports JSON/MD; step-up для ZIP/runtime; hash-derived paths, containment/symlink guards, nosniff/no-store |
| Проверки | 6 targeted tests; CRM games/wizard tests; ruff clean; mypy clean для нового модуля; reviewer accept; full suite 1085/1077/8 exit 0 |
| Статус | **COMPLETED / AI HQ REVIEW ACCEPT**; product/staging/prod не заявляются |
| Остаток | R-050: TOCTOU при write-доступе к artifact root; runtime zip не hash-verified; real nginx/volume E2E NOT TESTED |
| Источник | commits `f8c3a52`, `91c9c0f`; evidence в `.autonomy/evidence/` |


## ARCADE-CRM-GAME-RECORDS-001 — CRM records/epochs tab

| Поле | Значение |
|---|---|
| Тип | Product/CRM read-only implementation via AI HQ |
| Результат | `db8a835` + `551e73e`: текущая/архивная таблица рекордов в карточке игры, public ordering/rank parity, селектор эпох, пагинация 25, role guard |
| Проверки | 5 targeted tests; ruff/mypy изменённых модулей; reviewer reject → blocker fixed → accept; full suite 1090/1082/8 exit 0 |
| Статус | **COMPLETED / AI HQ REVIEW ACCEPT**; product/staging/prod не заявляются |
| Остаток | live browser/staging NOT TESTED; отображаются только public entries |
| Источник | commits `db8a835`, `551e73e`; evidence в `.autonomy/evidence/` |


## ARCADE-CATALOG-GENRE-PAGINATION-001 — genre page pagination

| Поле | Значение |
|---|---|
| Тип | Public catalog implementation via AI HQ; no schema/contract change |
| Результат | `0c4e64d`: shared pagination/clamping, sort/filter persistence, canonical + noindex,follow on deep pages, single-page without chrome |
| Проверки | 5 targeted tests + catalog pagination/public regressions; ruff/mypy clean; reviewer accept; full suite 1095/1087/8 exit 0 |
| Статус | **COMPLETED / AI HQ REVIEW ACCEPT**; product/staging/prod не заявляются |
| Остаток | live HTTP/nginx/staging NOT TESTED; unused `games` context key informational |
| Источник | commit `0c4e64d`; evidence в `.autonomy/evidence/` |
