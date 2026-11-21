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
| Проверки | 454 passed, 4 skipped; 3 play tests + 4 static SDK checks + 2 runtime E2E + 4 JS host tests + eventLog validation; ruff/format/mypy clean; node --check clean |
| Статус | **IMPLEMENTED / TECHNICAL REVIEW**; BA-SDK-1.1 submitted not approved |
| Review | code-reviewer — INCOMPLETE; security-auditor — INCOMPLETE (diff evidence, parentOrigin residual); probe/E2E 2 passed |
| Остаток | JS schema validation, snake/camel API adapter, retry policy, staging/prod origin, static collectstatic perms |
| Источник | `docs/foundation/BA-APPF-002_RUNTIME_SDK_REPORT.md` |

## Общие ограничения

- Аудит не закрывает BA-FIX-001 и не принимает BA-STAGE-1.1.
- Прохождение тестов не считается приёмкой.
- Статус «Fixed» в аудите означает исправление конкретного замечания, а не закрытие этапа.
- Открытые риски перечислены в `docs/risks/RISK_REGISTER.md`; не считать их исправленными.
- Нормативные ТЗ и отсутствующие BA-SDK-1.1/BA-ENV-1.1 не заменяются выводами аудита.
