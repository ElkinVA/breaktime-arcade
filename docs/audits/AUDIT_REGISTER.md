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


## ARCADE-APPF-RACE-TESTS-001 — App F concurrency/idempotency tests

| Поле | Значение |
|---|---|
| Тип | Test coverage via AI HQ; test-only, no migrations |
| Результат | `7af18bb`: 8 tests — concurrent result/leaderboard, rating limits + unique, storage If-Match/ETag race, Idempotency-Key replay |
| Проверки | targeted 8/8 on main; ruff clean; reviewer accept; full suite 1103/1095/8 exit 0 |
| Статус | **COMPLETED / AI HQ REVIEW ACCEPT**; product/staging/prod не заявляются |
| Остаток | service-level scope; HTTP round-trip and live browser/staging NOT TESTED |
| Источник | commit `7af18bb`; evidence в `.autonomy/evidence/` |


## ARCADE-SESSION-RACE-001 — create_session vs block/anonymise

| Поле | Значение |
|---|---|
| Тип | Reliability/security fix via AI HQ; no schema change |
| Результат | `2ac43e1`: User row lock + `is_active` recheck in create_session, same lock in anonymize_user; no session survives block/anonymise |
| Проверки | 2 concurrency tests; 19 CRM users tests; full suite 1105/1097/8 exit 0; reviewer accept after malformed-review retry |
| Статус | **COMPLETED / AI HQ REVIEW ACCEPT**; product/staging/prod не заявляются |
| Остаток | R-051 pre-existing lock-order inversion; live SDK/staging NOT TESTED |
| Источник | commit `2ac43e1`; evidence в `.autonomy/evidence/` |


## ARCADE-ARTIFACTS-TOCTOU-001 — artifact download TOCTOU

| Поле | Значение |
|---|---|
| Тип | Security hardening via AI HQ; no schema/contract change |
| Результат | `75d0159`: `O_NOFOLLOW` + fstat/inode verification, dir_fd tree walk, symlink/swap rejection for package and runtime |
| Проверки | 4 new TOCTOU + 6 existing artifact tests; ruff/mypy; reviewer accept; full suite 1109/1101/8 exit 0 |
| Статус | **COMPLETED / AI HQ REVIEW ACCEPT**; product/staging/prod не заявляются |
| Остаток | R-050 memory peak, runtime zip not hash-verified, real nginx/volume E2E NOT TESTED |
| Источник | commit `75d0159`; evidence в `.autonomy/evidence/` |


## ARCADE-RUNTIME-JSONSCHEMA-001 — schema-driven host/SDK validation

| Поле | Значение |
|---|---|
| Тип | Public runtime validation via AI HQ; wire contract unchanged |
| Результат | `855caa1` + tooling `3e037c4`: per-message schema tables, JSON-Schema-subset validator, `E_MESSAGE_INVALID`, sync vendored SDK, negative JS tests |
| Проверки | 19 JS tests on main; SDK contract/package tests; reviewer accept; full suite 1109/1101/8 exit 0 |
| Статус | **COMPLETED / AI HQ REVIEW ACCEPT**; product/staging/prod не заявляются |
| Остаток | R-052 myBest mismatch; R-053 hand-mirrored schemas; browser/staging E2E NOT TESTED |
| Источник | commits `855caa1`, `3e037c4`; evidence в `.autonomy/evidence/` |


## ARCADE-SDK-MYBEST-001 — myBest contract fix

| Поле | Значение |
|---|---|
| Тип | Public SDK/host conformance fix via AI HQ; no schema change |
| Результат | `20f379c`: bestOnly emits `{entries,myRank}`, SDK myBest extracts value/achievedAt; null/zero covered; vendored SDK synced |
| Проверки | JS 23/23 on main; full Python suite 1109/1101/8 exit 0; reviewer accept |
| Статус | **COMPLETED / AI HQ REVIEW ACCEPT**; product/staging/prod не заявляются |
| Остаток | nickname null in bestOnly entry (schema-legal); browser E2E NOT TESTED |
| Источник | commit `20f379c`; evidence в `.autonomy/evidence/` |


## ARCADE-SESSION-API-CAMELCASE-001 — sessionId create response

| Поле | Значение |
|---|---|
| Тип | Public API conformance fix via AI HQ; C-001/SESSION_ID_PROTOCOL |
| Результат | `16068f4`: POST sessions returns exact `{sessionId,ticket,expires_at}`, player.js/SDK camelCase only, tests/mocks updated |
| Проверки | JS 23/23; targeted sessions 41/41; full suite 1109/1101/8 exit 0; reviewer accept after reviewer-JSON prompt fix `3a91997` |
| Статус | **COMPLETED / AI HQ REVIEW ACCEPT**; product/staging/prod не заявляются |
| Остаток | probe/Playwright E2E NOT TESTED; R-054 expires_at snake_case/no alias |
| Источник | commit `16068f4`; tooling `3a91997`; evidence в `.autonomy/evidence/` |


## ARCADE-EXTERNAL-AUDIT-2026-11-25 — P1/P2 response

| Поле | Значение |
|---|---|
| Тип | Внешний статический audit + code fixes; независимые review |
| Результат | published-import blocker и re-lock re-check (`1763554`/`cc9923b`); production browser autotest gate + rollback exemption (`50f9135`/`d8c5d9f`); empty eventLog quarantine (`154de78`); pagehide pending-submit guard (`64d7149`); probe_seed guard, schedule validation/autotest tests, exact eventLog boundary (`8756e8c`, `541280a`, `4bd039c`, `e136af8`) |
| Проверки | pipeline 40; pipeline+wizard 50; result 30; JS 31; полный suite **1250 tests: 1237 passed, 13 skipped, exit 0** (на `e136af8`); ruff/format/mypy clean (388) |
| Статус | **PARTIAL / CODE FIXES ACCEPT**; AI HQ OS sandbox, Redis broker isolation, draft isolation, browser runner/override — owner-gated |
| Остаток | browser E2E в CI, staging/prod live, server-side terminal operation для pagehide, PB `is_public` semantics |
| Источник | `docs/audits/EXTERNAL_AUDIT_2026-11-25.md`; commits above; review agents text-only |

## ARCADE-LEADERBOARD-RANK-UNIFY-001 — shared rank calculation

| Поле | Значение |
|---|---|
| Тип | Minor refactor / drift protection; code-reviewer ACCEPT + delta ACCEPT |
| Результат | shared `entry_rank` in `apps/gameplay/services/ranking.py`; submit and read-side queries import it; bulk `rank_annotation` unchanged; no query-shape or behavior change |
| Проверки | 50 rank/leaderboard/profile/CRM tests; 8 leaderboard tests on delta incl. full `user_id ASC` tie-break and `entry_rank`↔`annotate_rank` parity; full **1236 tests: 1223 passed, 13 skipped, exit 0**; ruff/format 478 clean; mypy 388 clean |
| Статус | **COMPLETED / CODE-REVIEW ACCEPT**; browser E2E/staging NOT TESTED |
| Остаток | submit `previous` row not filtered by `is_public` (no hidden-row moderation exists yet) |
| Источник | commits `c7bc92e`, `40264c2`; модели: implement — `deepseek-flash[1m]`, review — `code-reviewer` (`deepseek-v4-pro`, text-only) |

## ARCADE-RANK-NONPB-001 — rank for non-personal-best results

| Поле | Значение |
|---|---|
| Тип | §6.7 leaderboard semantics; code-reviewer ACCEPT + delta ACCEPT |
| Результат | non-PB rank uses the user's existing best row; PB uses the new result; `is_record = is_personal_best and rank == 1`; aligns with read-side me.rank/myBest |
| Проверки | 29 result tests (added PB-not-first and lower-is-better non-PB), 19 leaderboard/profile/race tests; полный suite **1236 tests: 1223 passed, 13 skipped, exit 0**; ruff/format/mypy clean (387) |
| Статус | **COMPLETED / CODE-REVIEW ACCEPT**; browser E2E/staging NOT TESTED |
| Остаток | tie-with-own-best test; duplicated `_rank`; previous row not filtered by `is_public` → `ARCADE-LEADERBOARD-RANK-UNIFY-001` |
| Источник | commits `df8cad6`, `910f268`; модели: implement — `deepseek-flash[1m]`, review — `code-reviewer` (`deepseek-v4-pro`, text-only) |

## ARCADE-EVENTLOG-BYTES-001 — UTF-8 eventLog limit

| Поле | Значение |
|---|---|
| Тип | §2.12.7 / §6.5 payload limit; code-reviewer ACCEPT + delta ACCEPT |
| Результат | size check after UTF-8 encode; lone-surrogate UnicodeEncodeError mapped to structured 400/error list in serializer and semantic validator; schema-valid oversized test and two surrogate tests |
| Проверки | 3 eventLog tests; foundation contracts + game results 38 passed; полный suite **1234 tests: 1221 passed, 13 skipped, exit 0**; ruff/format/mypy clean (387) |
| Статус | **COMPLETED / CODE-REVIEW ACCEPT**; HTTP E2E not exercised |
| Остаток | exact-2-MiB boundary tests; duplicated 2 MiB constant |
| Источник | commits `ea47229`, `0a0dbfb`; модели: implement — `deepseek-flash[1m]`, review — `code-reviewer` (`deepseek-v4-pro`, text-only) |

## ARCADE-SUBMIT-RESTART-001 — result submission vs restart race

| Поле | Значение |
|---|---|
| Тип | §6.1 player/SDK race; code-reviewer ACCEPT |
| Результат | per-session submit chain with shared Idempotency-Key; newSession/exit await chain (with re-check for late submits) before close; restarts serialized; per-attempt 10 s AbortSignal timeout; stale leaderboard/storage still dropped |
| Проверки | JS **31/31**, `check:js` clean, player contract 4 passed; race test pins no close/create before both queued submits settle, key reuse, stale drops; full Python suite was green on previous Python commit |
| Статус | **COMPLETED / CODE-REVIEW ACCEPT**; real browser E2E/staging NOT TESTED |
| Остаток | hardening follow-up: exit vs pending newSession, exit/two-restart/late-submit tests, silent boundary submit drop, unreachable `exited` state |
| Источник | commits `24d9979`, `a81ec48`; модели: implement — `deepseek-flash[1m]`, review — `code-reviewer` (`deepseek-v4-pro`, text-only) |

## ARCADE-RATINGS-NIGHTLY-001 — nightly rating aggregate recalc

| Поле | Значение |
|---|---|
| Тип | §2.9 backend/data; code-reviewer ACCEPT + delta ACCEPT |
| Результат | `recalculate_all` union(votes, aggregates), pk order, per-game atomic + advisory lock, skip-if-unchanged, per-game error isolation; daily beat task (2400/3000, acks_late); command `recalculate_ratings --dry-run --limit`, non-zero on failures |
| Проверки | 12 nightly tests (drift is_valid/is_active, zeroing, union, error isolation, pk order, beat/annotations, dry-run no locks/writes, soft limit, command); полный suite **1230 tests: 1217 passed, 13 skipped, exit 0**; ruff/format/mypy clean (387); makemigrations clean |
| Статус | **COMPLETED / CODE-REVIEW ACCEPT**; live beat/worker NOT TESTED |
| Остаток | M1 offset, M3 six queries per game, M4 next-day catch-up after timeout, M5 batch-boundary test |
| Источник | commits `006aaca`, `b24ff78`, `4c5dd02`; модели: implement — `deepseek-flash[1m]`, plan — `architect`, review — `code-reviewer` (`deepseek-v4-pro`, text-only) |

## ARCADE-ZIP-WORKER-SECRETS-001 — least-privilege env for ZIP worker

| Поле | Значение |
|---|---|
| Тип | P0/P1 ZIP security hardening; security-auditor ACCEPT |
| Результат | `env_file` удалён из base/staging zip-worker; 13-ключевой non-secret allowlist (settings, broker, run flags, quota, worker CLI/TTL limits) с интерполяцией из `.env`; staging overlay не монтирует секреты; prod overlay запинен |
| Проверки | 11 compose tests (allowlist, secret-name denylist, quota parity, defaults vs base.py, overlay non-widening, prod pin); полный suite **1218 tests: 1205 passed, 13 skipped, exit 0**; ruff/format/mypy clean (384); live worker healthy, keys-only env, broker hash = web, benign ZIP E2E completed, db/cache DNS unreachable |
| Статус | **COMPLETED / SECURITY-AUDITOR ACCEPT**; live staging/prod NOT TESTED |
| Остаток | M1 dev-lite repo mount; M3 empty SECRET_KEY fail-loud; M4 broker password if requirepass; M5 no Sentry from worker |
| Источник | commits `1c19af5`, `d90af22`, `1cbbec3`; модели: implement — `deepseek-flash[1m]`, plan — `architect`, review — `security-auditor` (`deepseek-v4-pro`, text-only) |

## ARCADE-TEST-DB-SEED-001 — complete i18n reseed after flush

| Поле | Значение |
|---|---|
| Тип | Test-infra correction; product untouched |
| Результат | dynamic discovery of all `apps/i18n/migrations/*_seed_*.py` in migration order, idempotent reseed before/after transaction tests, fail-loud on empty glob/unknown seeder |
| Проверки | full reuse-DB suite **1214 tests: 1201 passed, 13 skipped, exit 0** (13:00); targeted transaction+home 4 passed; ruff/format/mypy clean; code-reviewer ACCEPT + delta ACCEPT |
| Статус | **COMPLETED**; test-only; no product acceptance claimed |
| Остаток | interrupted run can leave reuse-DB unseeded until next transaction test; one unreproduced step-up flake noted |
| Источник | commits `8e5f507`, `995f5d2`; модели: implement — `deepseek-flash[1m]`, review — `code-reviewer` (`deepseek-v4-pro`, text-only) |

## ARCADE-RUNTIME-ORPHAN-001 — ref-aware runtime TTL cleanup

| Поле | Значение |
|---|---|
| Тип | P1 ZIP storage lifecycle (§5.5); code-reviewer reject (worker mount) → delta accept |
| Результат | ежедневный `cleanup_orphan_runtimes`: flat/host-раскладки, symlink/non-hash skip, защита `GameVersion.runtime_hash`, TTL 24 ч, идемпотентность, лог `pipeline.runtime_orphan_removed`; worker rw `runtime_data` + `ZIP_PUBLIC_RUNTIME_ROOT` |
| Проверки | 4 новых теста (referenced/expired/fresh/symlink/flat, идемпотентность, beat/task, missing/symlink root) + compose regression; полный suite **1214 tests: 1201 passed, 13 skipped, exit 0** (fresh DB); ruff/format/mypy clean (383); live worker recreation + aged orphan removal с логом |
| Статус | **COMPLETED / CODE-REVIEW ACCEPT**; live beat/staging NOT TESTED; §5.5 закрыт |
| Остаток | referenced-protection только unit (dev-БД без GameVersion); default worker получил rw runtime-том (осознанно); TTL не настраивается per-game |
| Источник | commit `34f237f`; модели: implement — `deepseek-flash[1m]`, review — `code-reviewer` (`deepseek-v4-pro`, text-only) |

## ARCADE-ZIP-CONCURRENT-IMPORT-001 — same-game import race

| Поле | Значение |
|---|---|
| Тип | P1 ZIP pipeline integrity (§5.5); code-reviewer reject → delta accept |
| Результат | advisory xact lock по technical_id + adoption карточки; V_ID_CONFLICT vs V_VERSION_DUP; store_runtime усыновляет идентичный бандл после rename-гонки |
| Проверки | threaded race (одна Game/Version, created+duplicate), lock spy, adoption, constraint, forced rename/tampered; полный suite **1210 tests: 1197 passed, 13 skipped, exit 0** (fresh DB); ruff/format/mypy clean (383) |
| Статус | **COMPLETED / CODE-REVIEW ACCEPT**; live staging not tested |
| Остаток | orphan runtime закрыт `ARCADE-RUNTIME-ORPHAN-001` (`34f237f`); error-code asymmetry; report mutation after rollback; no barrier in race test |
| Источник | commit `03aaf0f`; модели: implement — `deepseek-flash[1m]`, review — `code-reviewer` (`deepseek-v4-pro`, text-only) |

## ARCADE-ZIP-JOB-REAPER-001 — stale RUNNING extraction reaper

| Поле | Значение |
|---|---|
| Тип | P1 ZIP pipeline reliability (§5.5); code-reviewer accept after delta |
| Результат | RUNNING >600 s (или null started + old created_at) → TIMEOUT X_JOB_STALE с finished_at; guarded idempotent update; beat 5 мин, task limits; web-late-completion авторитетен |
| Проверки | 3 reaper tests (границы, null, terminal/queued, task body, beat); полный suite **1203 tests: 1190 passed, 13 skipped, exit 0** (fresh DB); ruff/format/mypy clean (383) |
| Статус | **COMPLETED / CODE-REVIEW ACCEPT**; live beat NOT TESTED |
| Остаток | beat profile; no CANCEL marker; draft 7d purge; TTL invariant check; OR-index; env not in BA-ENV |
| Источник | commit `1687517`; модели: implement — `deepseek-flash[1m]`, review — `code-reviewer` (`deepseek-v4-pro`, text-only) |

## ARCADE-EMAIL-RESET-INVALIDATION-001 — reset tokens die with email change

| Поле | Значение |
|---|---|
| Тип | P1 account security (§5.1); security-auditor accept after delta |
| Результат | смена/удаление email инвалидирует PASSWORD_RESET+EMAIL_VERIFY атомарно; confirm сверяет verified/current email и active; inactive token отклоняется |
| Проверки | 25 account tests; полный suite **1200 tests: 1187 passed, 13 skipped, exit 0** (fresh DB); ruff/format/mypy clean (382) |
| Статус | **COMPLETED / SECURITY-AUDITOR ACCEPT**; live staging not tested |
| Остаток | submission-order race — ARCADE-EMAIL-RESET-RACE-001; timing oracle; single-address assumption |
| Источник | commit `26d8075`; модели: implement — `deepseek-flash[1m]`, review — `security-auditor` (`deepseek-v4-pro`, text-only) |

## ARCADE-RESTORE-CHECK-001 — verified restore-check

| Поле | Значение |
|---|---|
| Тип | P1 backup/DR integrity (§5.4); security-auditor accept after delta |
| Результат | SHA-256 до/после restore vs BackupRun; empty/unreadable reject; DROP FORCE; required tables + django_migrations; meta counts; malformed SQL fails |
| Проверки | 22 unit restore-check; полный suite **1197 tests: 1184 passed, 13 skipped, exit 0** (fresh DB); ruff/format/mypy clean (382); real dev restore OK (44 tables/42 migrations/10 required), temp DB dropped; staging/prod NOT TESTED |
| Статус | **COMPLETED / SECURITY-AUDITOR ACCEPT** |
| Остаток | A→B→A swap window; no concurrent advisory lock; structural-only; superuser role owner-gated; baked image rebuild for cron; file-level S608 noqa |
| Источник | commit `cdb567a`; модели: implement — `deepseek-flash[1m]`, review — `security-auditor` (`deepseek-v4-pro`, text-only) |

## ARCADE-CONTENT-LENGTH-001 — malformed header returns 400/413

| Поле | Значение |
|---|---|
| Тип | P1 API robustness (§6 п.9); code-reviewer reject → delta accept |
| Результат | defensive `_content_length`: missing/empty → 0, non-numeric/negative → 400 E_INVALID_REQUEST, > MAX → 413; except pinned `# fmt: skip` |
| Проверки | unit boundaries + dispatch-level authenticated/CSRF 400; full suite **1188 tests: 1175 passed, 13 skipped, exit 0** (fresh DB); ruff/format/mypy clean (382) |
| Статус | **COMPLETED / CODE-REVIEW ACCEPT**; live HTTP/gunicorn not tested |
| Остаток | int() leniency like Django/DRF; chunked/no-header rejected by DRF (pre-existing); 413 dispatch not exercised (view-level) |
| Источник | commit `ab62a7d`; test-flake fix `116efbd`; модели: implement — `deepseek-flash[1m]`, review — `code-reviewer` (`deepseek-v4-pro`, text-only) |

## ARCADE-RATINGS-BLOCK-001 — blocked votes excluded immediately

| Поле | Значение |
|---|---|
| Тип | P1 ratings/account integrity (TS §2.9 п.4); security-auditor review after delta |
| Результат | recalc всех игр пользователя при block/unblock/staff transition/delete в детерминированном game-id порядке; vote() берёт User-lock и повторно проверяет is_active; голоса остаются в БД и возвращаются при unblock |
| Проверки | 5 test_ratings_block + 30 related; полный suite **1183 tests: 1170 passed, 13 skipped, exit 0** (fresh DB); ruff/format/mypy clean (382); security-auditor **accept** (delta: ordering-тест на non-monotonic UUID) |
| Статус | **COMPLETED / SECURITY-AUDITOR ACCEPT**; live staging not tested |
| Остаток | thread race test blocked by TEST-DB-SEED; nightly recalc/backfill — ARCADE-RATINGS-NIGHTLY-001; O(votes) block cost; session is_active residuals |
| Источник | commit `766029e`; модели: implement — `deepseek-flash[1m]`, review — `security-auditor` (`deepseek-v4-pro`, text-only) |

## ARCADE-CRM-BLOCK-IDEMPOTENT-001 — explicit block/unblock

| Поле | Значение |
|---|---|
| Тип | P1 CRM account safety (§5.1); security-auditor review |
| Результат | явные идемпотентные block/unblock вместо toggle; no-op без audit; реальный переход — audit + revoke SDK-сессий; toggle-маршруты удалены; race-тесты переведены на block_user |
| Проверки | 27 `test_crm_users`; полный suite **1178 tests: 1165 passed, 13 skipped, exit 0** (fresh DB); ruff/format/mypy clean (382); security-auditor **accept**, findings informational/minor |
| Статус | **COMPLETED / SECURITY-AUDITOR ACCEPT**; live staging not tested |
| Остаток | rating aggregates exclusion — next ARCADE-RATINGS-BLOCK-001; no-op revoke legacy window; activate/heartbeat is_active; tombstone wording; unblock 403/CSRF test |
| Источник | commit `88c2a64`; модели: implement — `deepseek-flash[1m]`, review — `security-auditor` (`deepseek-v4-pro`, text-only) |

## ARCADE-ROLLBACK-SAFE-001 — publication history and safe rollback

| Поле | Значение |
|---|---|
| Тип | P0/P1 publication safety; security-auditor reject → delta accept |
| Результат | publish/rollback audit пишется атомарно с переключением; rollback только на ранее опубликованную версию, с validation/autotest и score rules текущей версии; hidden/archived сохраняются, draft/review отклоняются; CRM не дублирует audit |
| Проверки | 12 rollback tests + CRM audit/step-up; полный suite **1177 tests: 1164 passed, 13 skipped, exit 0** (fresh DB); ruff/format/mypy clean (382); ложная PEP 758 syntax-находка опровергнута исполнением |
| Статус | **COMPLETED / SECURITY-AUDITOR ACCEPT**; live staging not tested |
| Остаток | concurrency test blocked by TEST-DB-SEED; pre-audit/direct publications без истории блокируются; future scheduled-publish must call publish_version; score-rule epoch — owner decision |
| Источник | commit `ecfb419`; модели: implement — `deepseek-flash[1m]`, review — `security-auditor` (`deepseek-v4-pro`, text-only) |

## ARCADE-REGISTRATION-LIMITS-001 — device + IP registration limits

| Поле | Значение |
|---|---|
| Тип | P1 abuse/NAT protection; security-auditor reject → delta accept |
| Результат | device 3/сутки (CSRF-derived interim key, IP fallback) + IP 30/сутки; reserve/release вокруг формы; IPv6 /64 и IPv4-mapped; throttle cache JSON serializer делает INCR атомарным на реальном Redis; ConnectionInterrupted fail-closed |
| Проверки | 49 targeted + real-Redis конкурентный тест (29 seed + 20 потоков → ровно один allowed); полный suite **1166 tests: 1153 passed, 13 skipped, exit 0** (fresh DB); ruff/format/mypy clean (382) |
| Статус | **IMPLEMENTED / SECURITY-AUDITOR ACCEPT; OWNER DECISION REQUIRED** (device cookie, challenge/100) |
| Остаток | CSRF device rotation (~1/token-cycle); hard 30/day без challenge и блока 100; denied attempts keep slots (NAT burst DoS); release TOCTOU; production trusted-proxy allowlist; live load/staging not tested |
| Источник | commit `bbfdcaf`; модели: implement — `deepseek-flash[1m]`, review — `security-auditor` (`deepseek-v4-pro`, text-only) |

## ARCADE-AUTH-THROTTLE-001 — atomic account limits, fail-closed

| Поле | Значение |
|---|---|
| Тип | P0 auth/abuse protection; security-auditor initial + delta review |
| Результат | account counters в выделенном `throttle` (noeviction, socket timeouts 1 s); атомарный reserve login 5/15 мин и 2FA 10/15 мин до Argon2; success очищает account; IP failures 60/15 и 30/15; reset 3/ч + 20/ч; registration slot reserve/release; auth и complaints fail-closed, games fail-open; IPv6 /64; casefold reset; owner-recovery audit |
| Проверки | 43 targeted; полный suite **1159 tests: 1146 passed, 13 skipped, exit 0** (fresh DB); ruff/format/mypy clean (382); security-auditor **accept**, delta **accept**, new bypass none |
| Статус | **COMPLETED / SECURITY-AUDITOR ACCEPT**; live Redis/load/staging not tested |
| Остаток | account-lockout DoS policy; IP-failure burst race; touch-repair без Lua; malformed 2FA IP; shared unknown-IP; registration device key — T3; challenge O4 |
| Источник | commit `de08292`; модели: implement — `deepseek-flash[1m]`, review — `security-auditor` (`deepseek-v4-pro`, text-only) |

## ARCADE-THROTTLE-001 — session scopes, results/report IP caps

| Поле | Значение |
|---|---|
| Тип | P0 API abuse protection; security-auditor review |
| Результат | create/activate/close разделены по scope (create 30/ч + guest IP 600/ч; activate/close — отдельные 30/ч); results subject 60/ч + IP 1200/ч; complaints 5/сутки subject + 30/сутки IP |
| Проверки | 9 targeted; полный suite **1147 tests: 1134 passed, 13 skipped, exit 0** (fresh DB); ruff/format/mypy clean; security-auditor **accept**, findings non-blocking |
| Статус | **COMPLETED / SECURITY-AUDITOR ACCEPT**; live Redis/NAT/staging not tested |
| Остаток | authenticated sessions_ip exemption; heartbeat invalid-id buckets; reports fail-open до AUTH-THROTTLE-001; нет throttle socket timeouts; challenge O4; DRF counters non-atomic |
| Источник | commit `b953419`; модели: implement — `deepseek-flash[1m]`, review — `security-auditor` (`deepseek-v4-pro`, text-only) |

## ARCADE-RESULT-VERIFICATION-001 — missing eventLog/seed quarantine

| Поле | Значение |
|---|---|
| Тип | P0 result integrity/security; security-auditor review |
| Результат | verification-profile results missing eventLog or non-empty seed are quarantined; no LeaderboardEntry; blank seed reaches quarantine; empty manifest profile does not mask game profile |
| Проверки | 25 targeted result tests; full suite **1144 tests: 1131 passed, 13 skipped, exit 0** (fresh DB); ruff/format/mypy clean; security-auditor accept, delta (blank seed + empty-profile precedence) accept — no new bypass |
| Статус | **COMPLETED / SECURITY-AUDITOR ACCEPT**; product/staging not claimed |
| Остаток | empty `events` heuristic gap; staging/live not tested |
| Источник | commit `1fc0e97`; модели: implement — `deepseek-flash[1m]`, review — `security-auditor` (`deepseek-v4-pro`, text-only) |

## ARCADE-SESSION-LIFECYCLE-001 / PLAY-001 / HEARTBEAT-SUBMIT-001 / PAGEHIDE-001

| Поле | Значение |
|---|---|
| Тип | Product session lifecycle / player UX; independent code review |
| Результат | `7da168a`: lazy stale expiry + 5-min beat + two-phase locks; `35ae98f`: GET shell, player creates session; `f7a3779`: final heartbeat; pagehide keepalive close |
| Проверки | 46 session tests incl. sweep vs beat race; play 3/3; JS 31/31; reviewer accept (B1b after e2e fix); full suite 1137/1129/8 exit 0 |
| Статус | **COMPLETED / CODE-REVIEW ACCEPT**; product/staging/prod не заявляются |
| Остаток | real Playwright E2E, live beat/Redis and staging NOT TESTED; browser kill may skip pagehide |
| Источник | commits `7da168a`, `35ae98f`, `f7a3779`, `cb92702` |

## AI-HQ-CI-001 — CI quality gate

| Поле | Значение |
|---|---|
| Тип | CI/test infrastructure; independent code review |
| Результат | `a0aa34b`: redis-throttle service/env, ruff/mypy autonomy+scripts, self_check FakeRunner, sandbox-copy test, diagnostic coverage step |
| Проверки | 38 affected tests; mypy 381 files; ruff clean; autonomy/devcontrol coverage 73 %; review accept + delta |
| Статус | **IMPLEMENTED / REVIEW ACCEPT; GitHub CI run NOT VERIFIED** (нет gh/токена) |
| Источник | commit `a0aa34b` |

## AI-HQ-A1 — trusted sandbox-only agent checks

| Поле | Значение |
|---|---|
| Тип | P0 security hardening of autonomy control plane; security-auditor review |
| Результат | `1f46062`: five exact sandbox commands (no wildcard), task-bound source-root, `.git`/gitdir validation, node-only JS sandbox, Git-derived changed files, protected host-exec surfaces, reviewer no Bash |
| Проверки | 69 affected tests; JS 26/26; source-root smoke 41/41; full suite 1130/1122/8 exit 0; security verdict accept after 3 rounds |
| Статус | **COMPLETED / SECURITY-AUDITOR ACCEPT**; product/staging/prod не заявляются |
| Остаток | R-040 OS-sandbox; full-suite-only runs; apps/ in web container; CLI exact-match semantics not dynamically verified |
| Источник | commit `1f46062` |

## AI-HQ-A2 — immutable candidate QA

| Поле | Значение |
|---|---|
| Тип | P0 control-plane integrity; security-auditor review |
| Результат | `45a69f1`: commit candidate before QA, clean QA worktree at exact SHA, full diff, strict QA/reviewer JSON, Git-derived files, merge only after both gates |
| Проверки | 23 affected tests; malformed reviewer never merges; full suite 1132/1124/8 exit 0; security accept |
| Статус | **COMPLETED / SECURITY-AUDITOR ACCEPT**; product/staging/prod не заявляются |
| Остаток | QA/reviewer model trust; huge diff argv/context; R-040 |
| Источник | commit `45a69f1` |

## ARCADE-ARTIFACTS-STREAMING-001 — artifact streaming + ZIP hash

| Поле | Значение |
|---|---|
| Тип | Security/performance hardening via AI HQ; no schema/contract change |
| Результат | `8d22aee` + `167ece6`: SHA-256 before body, chunked package streaming, temp-file runtime zip, spool cleanup on any failure |
| Проверки | 13 targeted artifact tests; ruff/mypy clean; reviewer accept; full suite 1112/1104/8 exit 0 |
| Статус | **COMPLETED / AI HQ REVIEW ACCEPT**; product/staging/prod не заявляются |
| Остаток | R-050 double-read/in-place swap, runtime zip not hash-verified, E2E NOT TESTED |
| Источник | commits `8d22aee`, `167ece6`; evidence в `.autonomy/evidence/` |


## ARCADE-RUNTIME-SCHEMA-SINGLE-SOURCE-001 — generated host schemas

| Поле | Значение |
|---|---|
| Тип | Runtime maintainability via AI HQ; wire behavior preserved |
| Результат | `f9a75d4` + `d1c4e6f`: generated host registry, parity test, unsupported-keyword guard; DRAFT schema tightenings R-055 |
| Проверки | JS 23/23; registry tests 4/4; generator --check; full suite 1113/1105/8 exit 0 |
| Статус | **COMPLETED / AI HQ REVIEW ACCEPT**; product/staging/prod не заявляются |
| Остаток | build does not auto-generate; browser/staging E2E NOT TESTED; R-055 contract confirmation |
| Источник | commits `f9a75d4`, `d1c4e6f`; evidence в `.autonomy/evidence/` |


## ARCADE-SESSION-LOCK-ORDER-001 — App F lock order

| Поле | Значение |
|---|---|
| Тип | Reliability/concurrency fix via AI HQ; no schema change |
| Результат | `92ef3b1` + `f871f06`: submit_result/heartbeat User lock before GameSession + is_active check |
| Проверки | 3 concurrency tests; targeted 22/22; race suite 8/8; full suite 1116/1108/8 exit 0; reviewer accept |
| Статус | **COMPLETED / AI HQ REVIEW ACCEPT**; product/staging/prod не заявляются |
| Остаток | R-056 put_storage; live load/staging E2E NOT TESTED |
| Источник | commits `92ef3b1`, `f871f06`; evidence в `.autonomy/evidence/` |


## ARCADE-CRM-MODERATION-PAGINATION-001 — moderation queues pagination

| Поле | Значение |
|---|---|
| Тип | CRM UX implementation via AI HQ; no schema change |
| Результат | `07a287a` + `380cd11`: 50/page rating and complaint queues, full-set rating summary, filters and both page positions preserved |
| Проверки | 13 targeted tests; ruff clean; reviewer accept; full suite 1117/1109/8 exit 0 |
| Статус | **COMPLETED / AI HQ REVIEW ACCEPT**; product/staging/prod не заявляются |
| Остаток | browser/staging NOT TESTED |
| Источник | commits `07a287a`, `380cd11`; evidence в `.autonomy/evidence/` |


## ARCADE-STORAGE-LOCK-ORDER-001 — storage write lock order

| Поле | Значение |
|---|---|
| Тип | Reliability/concurrency fix via AI HQ; no schema change |
| Результат | `bcd99a7`: User lock + is_active before storage advisory/row in put_storage; guest branch unchanged |
| Проверки | 4 race tests; targeted 26/26; ruff/targeted mypy; reviewer accept; full suite 1121/1113/8 exit 0 |
| Статус | **COMPLETED / AI HQ REVIEW ACCEPT**; product/staging/prod не заявляются |
| Остаток | live load/staging E2E NOT TESTED |
| Источник | commit `bcd99a7`; evidence в `.autonomy/evidence/` |


## ARCADE-ARTIFACTS-SINGLE-PASS-001 — single-pass ZIP hash

| Поле | Значение |
|---|---|
| Тип | Security hardening via AI HQ; no schema/contract change |
| Результат | `ee9e9c4`: hash-while-spooling from verified fd, serve only verified spool; no body on mismatch |
| Проверки | 15 targeted artifact tests; ruff/mypy clean; reviewer accept; full suite 1123/1115/8 exit 0 |
| Статус | **COMPLETED / AI HQ REVIEW ACCEPT**; product/staging/prod не заявляются |
| Остаток | runtime zip not hash-verified; real nginx/volume E2E NOT TESTED |
| Источник | commit `ee9e9c4`; evidence в `.autonomy/evidence/` |


## ARCADE-RUNTIME-HASH-VERIFY-001 — runtime tree digest

| Поле | Значение |
|---|---|
| Тип | Security/integrity hardening via AI HQ; no schema/contract change |
| Результат | `8f9f7ac`: per-file SHA-256 while zipping, canonical tree digest vs `runtime_hash`, no body on mismatch |
| Проверки | 17 targeted artifact tests; ruff/mypy clean; reviewer accept (0 findings); full suite 1125/1117/8 exit 0 |
| Статус | **COMPLETED / AI HQ REVIEW ACCEPT**; product/staging/prod не заявляются |
| Остаток | real nginx/volume E2E and large-runtime load NOT TESTED |
| Источник | commit `8f9f7ac`; evidence в `.autonomy/evidence/` |


## ARCADE-SDK-ABORT-PENDING-001 — SDK pending-request abort

| Поле | Значение |
|---|---|
| Тип | SDK lifecycle implementation via AI HQ; wire contract unchanged |
| Результат | `ebe7d30` + `b34a288`: exit/newSession settles pending requests, clears timers, ignores late responses |
| Проверки | JS 26/26; SDK contract/package tests; reviewer accept; full Python suite 1125/1117/8 exit 0 |
| Статус | **COMPLETED / AI HQ REVIEW ACCEPT**; product/staging/prod не заявляются |
| Остаток | browser/staging E2E NOT TESTED |
| Источник | commits `ebe7d30`, `b34a288`; evidence в `.autonomy/evidence/` |


## ARCADE-RUNTIME-BUILD-SCHEMAS-001 — BLOCKED

| Поле | Значение |
|---|---|
| Тип | Build integration proposal via AI HQ |
| Результат | Не merged: QA blocker — npm build runs in Docker assets stage without scripts/schemas/python3; Dockerfile change out of scope |
| Проверки | QA fail с конкретным evidence; parity test/check:schemas уже защищают drift |
| Статус | **BLOCKED — infra/owner decision**; продуктовая функциональность не затронута |
| Источник | `.autonomy/state.json`, QA evidence |
