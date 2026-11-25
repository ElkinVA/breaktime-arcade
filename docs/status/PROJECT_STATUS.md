# PROJECT_STATUS — Breaktime Arcade

**Дата актуализации:** 2026-11-23 (P5 Archer; локальная сверка Claude;
product acceptance remains owner-level).

## 0.1. P4 — фактическое состояние

- **A1/A2 quota/retention:** `0ba8bfe`, strict follow-up `16fb095`;
  system-wide app-layer quota/free-space fail-closed, active-aware cleanup;
  Pro review accept. Hard FS quota **NOT TESTED**.
- **A3 R-041:** sync import kept after analysis; async not justified.
- **A4 R-042:** staging runbook/read-only checks prepared; live staging
  **BLOCKED/NOT TESTED** (`.env.staging` absent).
- **A5 resilience:** concurrent quota, free-space, duplicate, broker
  failure, cleanup rerun, published-runtime preservation tests; no stress.
- **A6:** available ZIP Worker review evidence saved; original P3 JSON was
  not persisted.
- **B Neon Snake:** package `d1ebc41`, media/catalog fixes `5f8bd2b`; live
  CRM→zip-worker→publish→iframe→SDK result/leaderboard; v1.1.0 update and
  rollback to v1.0.0; bad ZIP rejected.
- **Checks:** fresh gate **966 passed, 12 skipped**, Browser E2E **18
  passed**, sandbox package/import/catalog/pipeline green.
- **External:** real game product/legal rights, staging, email, domains/TLS,
  S3/hosting/DR, production deploy — owner action list P4.

## 0. P0/P1/P2 — фактическое состояние

- **P0** `ARCADE-P0-CONTRACT-CLOSURE-001` → `7c56f93`: ADR-APPF-001,
  BA-GAME A, BA-SDK/ENV, 64 КиБ/strict unknown/`sessionId`, DB-001…008,
  App F trust/EventLog/storage/leaderboard, retention, roles/2FA/step-up,
  email adapter, production requirements. Внутренняя техническая приёмка;
  юридические/платные/инфраструктурные действия не выполнялись.
- **P1** `51a08d0` rating UI + TOP-100 leaderboard; `a167a47` JSON-LD,
  CLDR plurals и accessibility. Product acceptance owner.
- **P2** `059b7fa` ZIP intake/import/runtime/publish; `f938315` CRM games;
  `de1c975` CRM wizard/reports/step-up; `6dd54d7` roles/audit;
  `03061c0` rating moderation/complaints; `11c9805` translations/content/
  local analytics. Technical acceptance with independent Pro review.
- Full fresh gate: **917 passed, 12 skipped**.
- Models: Developer/QA `deepseek-flash[1m]`; Architect/Reviewer
  `deepseek-v4-pro`; evidence in `.autonomy/evidence/`.
- Остаются: продуктовая приёмка владельца, App F runtime product review,
  legal/email/domains/TLS/S3/hosting/real game/deploy; STOP снят.
- **Product acceptance 2026-11-22:** E2E 18 passed; live ZIP→publish,
  public runtime, App F session/result/leaderboard/storage, rating/rollback,
  CRM pages, SEO/a11y; fresh gate **930 passed, 12 skipped**. P3
  `ARCADE-P3-ZIP-WORKER-INTEGRATION-001` (`9017254`, Pro-reviewed):
  worker-only extraction, live `ZipExtractionJob completed`, source cleanup,
  runtime volume/init. Отчёт `docs/foundation/PRODUCT_ACCEPTANCE_REPORT.md`.
  Остаются external: real game/rights, email, legal, domains/TLS,
  S3/hosting/DR, production deploy; staging live NOT TESTED.

**Дата предыдущей актуализации:** 2026-11-22 (ADR-APPF-001: внутренняя
приёмка контрактов; внешние действия не выполнялись).
Документ — краткая панель текущего состояния. Нормативные требования
определяются только утверждёнными ТЗ и решениями владельца; отчёты агентов,
аудиты и реестры не заменяют приёмку.

## 0.2. P5 — Archer (2026-11-23)

- **Game:** `games-src/archer` v1.3.3; 60 s ballistic archery, four target
  types, combo ×5, fixed timestep, six locales/catalogs, generated assets,
  official SDK byte-identical.
- **Live dev:** CRM upload 0 blockers → isolated `zip-worker` → publish;
  public detail/play/iframe; full 60 s result **156** rank 3, result
  `200 saved`; leaderboard 321/214/156; update/rollback/republish tested.
- **Tests:** Node 11, Archer package 14, import 1, full fresh **981/12**,
  E2E 18; Neon regression package 13/import 1 and live pages 200.
- **Review:** independent Pro **ACCEPT**, major end-event fixed/delta
  closed.
- **Not tested:** original prototype (file absent), staging/production,
  non-Chromium devices, real network-fault injection.

## 0.3. Локальная сверка 2026-11-23 (Claude)

- Git: `HEAD` = `origin/main`; актуальный hash — `git log -1`; рабочее
  дерево чистое, неотправленных локальных коммитов нет.
- Полный fresh pytest: **981 passed**; 8 skip из-за отсутствия `git` в
  контейнере `web` (7 `test_autonomy_worktree.py` + 1 `test_devcontrol.py`)
  и 4 module-level E2E skip при выключенном `BA_E2E` — всего отчётные
  **12 skipped**. Исторический P5-отчёт указывает 13 package-тестов;
  фактическая текущая коллекция — 14 (отчёт не переписывался).
- PostgreSQL healthy; Redis cache/broker/throttle `PONG`; Celery worker
  `pong`; `zip-worker`/`zip-volume-init` не запущены.
- Dev-БД: **0 игр**, **26 неприменённых миграций**; Archer-страницы локально
  404. Миграции и восстановление не выполнялись.
- `.env`/`certs/` присутствуют; required core env names заданы;
  `.env.staging` присутствует, но staging не валидировался.
- Archer personal best: fallback для record есть; async `myBest` остаётся
  cosmetic residual. SDK-контракт не менялся.
- План ревью: `docs/tasks/APPF-RUNTIME-REVIEW-001_PLAN.md`.

## 0.4. AI Headquarters — проверка 2026-11-23

- **A:** bounded-цикл задач в `autonomy/orchestrator.py`; VPS unit
  `--max-tasks 1` → **PASS код / NOT TESTED live**.
- **B:** нет автозапуска следующей сессии; `/continue` в devcontrol —
  ручной → **FAIL**.
- **C:** нет `.autonomy`, установленных user units/timers и background
  sessions → **FAIL**.
- **D:** `recover_running`, `RUN_LOCK`, worktree cleanup/retry limits;
  autonomy tests **94 passed, 1 skipped** → **PASS код / NOT TESTED live**.
- **E:** `api.telegram.org:443` timeout; bot process/state отсутствуют →
  **FAIL/NOT TESTED**.
- Минимальный timer для существующего orchestrator:
  `docs/tasks/AUTONOMY-CONTINUATION-001_PLAN.md`, **BLOCKED — owner**.

## 0.5. App F Runtime Review — 2026-11-23

`APPF-RUNTIME-REVIEW-001` — **IMPLEMENTED / INDEPENDENT REVIEW ACCEPT**
(code-reviewer + security-auditor, deepseek-v4-pro, text-only; delta
ACCEPT). Исправлены: host validation (`safe integer`, duration, eventLog
null/array, limit 10/100), stale-response guard в player, best-effort close
старой сессии перед newSession, per-session Idempotency-Key, отказ от
retry для activate/close. Проверки: targeted 79 passed, `npm test:js`
7 passed, `npm run check:js` clean; полный suite — см. фактические
результаты. Остатки: race/stale и idempotency-key тесты добавлены (`tests/js/player_race.test.mjs`,
independent review ACCEPT); серверная cross-check strictness — NOT TESTED; R-036 Phase 2 не менялся;
R-043/R-044/R-045 — residual; live E2E/staging/prod — NOT TESTED.
Отчёт — `docs/foundation/APPF-RUNTIME-REVIEW-001_REPORT.md`.

## 0.6. Token observability — 2026-11-23

`BA-TOKEN-OBSERVABILITY-001` — **IMPLEMENTED / INDEPENDENT REVIEW ACCEPT**.
Добавлен metadata-only учёт role invocations: task/attempt/agent/role/
session/invocation, model/reported models, Claude-reported input/output/
cache/cost, optional `num_turns`; `request_count` остаётся `None`, если CLI
не отдаёт точное значение. Запись — `.autonomy/invocations.jsonl`, без
prompt/response/секретов. Execution behavior, модели, бюджет и число
агентов не менялись. 8 observability tests, autonomy subset 100/1 skipped,
full suite exit 0; ruff/mypy clean. Provider request/cache/cost invoice пока
не коррелируется с task_id — residual. Отчёт —
`docs/audits/BA_TOKEN_OBSERVABILITY_IMPLEMENTATION_REPORT.md`.

## 0.7. Token observability lifecycle — 2026-11-23

`BA-TOKEN-OBSERVABILITY-002` — **IMPLEMENTED / INDEPENDENT REVIEW ACCEPT**
(minor fixes applied). Schema v2 в `.autonomy/invocations.jsonl`: start/finish
events, failed/timeout/cancelled/interrupted, reconciliation по owner pid /
PID reuse / boot_id, legacy-записи читаются как authoritative terminal.
Runner — единственный писатель lifecycle; `_account` сохраняет success-only
state/budget. API-error usage сохраняется, если CLI его вернул; unknown
usage — `null` + `usage_known=false`. Реальный control run: success
(usage 5962/105, cost 0.0324), timeout, SIGINT, invalid model, SIGKILL+
reconcile — 5 started/5 finished, двойного учёта нет. 30 observability
tests; full suite **1019 tests: 1011 passed, 8 skipped, exit 0**;
ruff/format/mypy clean.
Residual: usage при timeout/cancel/interrupted неизвестен; provider
request_count/cache/invoice не коррелируются; SIGKILL может оставить child;
ротации журнала нет. Отчёт — `docs/audits/BA_TOKEN_OBSERVABILITY_002_IMPLEMENTATION_REPORT.md`.

## 0.8. Token efficiency optimization — 2026-11-23

Практический срез по аудиту BA-TOKEN-EFFICIENCY-AUDIT-001:

- Architect brief: обязательный bundle 168 145 → 5 011 chars (−97.0 %);
  architect читает brief + точечные разделы, а не четыре полных реестра.
- Реальная пара planning calls: input_tokens 132 148 → 59 430 (−55.0 %),
  cost 1.617336 → 1.205210 USD (−25.5 %), cache read −33.0 %, output +48.8 %
  и num_turns 32→39; оба proposal валидны после штатного `_parse_json`
  (4 и 3 задачи). Один запуск на фазу — индикативно, не статистика.
- Prompt-level context discipline для developer/QA/reviewer; runbook
  `ai_session_policy.md` для интерактивных/`--bg` сессий.
- Модели, маршрутизация, число агентов, budget/stop-политика не менялись.
  Отчёт — `docs/audits/BA_TOKEN_EFFICIENCY_OPTIMIZATION_REPORT.md`.

## 0.9. App F retention cleanup — 2026-11-23

`ARCADE-RETENTION-001` — **COMPLETED / AI HQ REVIEWER ACCEPT** (`8e42426`).
Суточные Celery beat tasks: GameSession `finished/expired/aborted` старше
30 дней с `result__isnull=True` (результаты PROTECT сохраняются);
GamePlayCredit старше 90 дней; GameImportDraft старше 7 дней; гостевое
GameStorage с `expires_at < now`. Deletes идемпотентны для R-036
at-least-once, возвращают per-type counts. 8 integration tests + migration
guard; targeted ruff/mypy clean; full suite **1028 tests: 1020 passed,
8 skipped, exit 0**. QA attempt 1 корректно упал на NOT TESTED
mypy/makemigrations; после добавления host mypy и постоянного
`test_migrations_check.py` attempt 2 прошёл. Остатки: нет индексов на
`updated_at`/`last_credited_at`; concurrent result insert может дать
ProtectedError и retry (данные не теряются); live beat NOT TESTED.

## 0.10. Slug 301 redirects — 2026-11-23

`ARCADE-CATALOG-SLUG-301-001` — **COMPLETED / AI HQ REVIEWER ACCEPT**
(`cf0936c`). Добавлен `GameSlugHistory` (миграция `catalog.0011`) и запись
старого slug при изменении `Game.slug`/`GameTranslation.slug`; старый URL
отдаёт постоянный 301 на текущий canonical URL, неизвестный/неопубликованный
slug — 404. 5 новых integration tests + migration guard; ruff/mypy clean;
полный suite **1033 tests: 1025 passed, 8 skipped, exit 0**. Остатки:
нет отдельного negative-теста cross-language old slug; `FALLBACK_LANGUAGE_CODE`
дублируется с SEO/sitemap; concurrent `get_or_create` race не тестировался.

## 0.11. CRM SEO diagnostics — 2026-11-23

`ARCADE-CRM-SEO-DIAGNOSTICS-001` — **COMPLETED / AI HQ REVIEWER ACCEPT**
(`f5474d8`). Новый read-only экран `/crm/seo/` (§2.19): пустые локализованные
описания, дубли page title по языкам, ассеты без alt, неполное покрытие
переводов; per-language summary и ссылки на игры; доступ через `GAMES_VIEW`.
11 integration tests, role-gating/redirect; ruff/mypy clean; полный suite
**1044 tests: 1036 passed, 8 skipped, exit 0**. Остаток: экран строит
диагностику по всем published games в памяти — performance на очень больших
каталогах не тестировался; staging/prod NOT TESTED.

## 0.12. Slug-history hardening — 2026-11-23

`ARCADE-SLUG-HISTORY-HARDENING-001` — **COMPLETED / AI HQ REVIEWER ACCEPT**
(`bf33191`). `record_game_slug`/`record_translation_slug` переживают
concurrent insert (IntegrityError → re-fetch); `FALLBACK_LANGUAGE_CODE`
вынесен в `apps/catalog/constants.py` и используется slug/SEO; добавлены
cross-language negative test и concurrent-insert test (mock пути).
4 файла, без schema/contracts; targeted 7 slug tests + migration guard;
ruff/mypy clean; full suite **1046 tests: 1038 passed, 8 skipped, exit 0**.
Остаток: concurrent test
детерминированно мокает `get_or_create`, реальная DB-гонка не проверялась.

## 0.13. CRM customer accounts — 2026-11-23

`ARCADE-CRM-USERS-001` — **COMPLETED / AI HQ CODE REVIEW ACCEPT; SECURITY REVIEW CONDITIONAL → DELTA RESOLVED** (`4095ed8` + security fixes). Экран `/crm/users/`: поиск login/nickname/email (min 2, citext), фильтры verified/blocked, detail без password/TOTP/recovery, block/unblock с аудитом, delete через `anonymize_user` с 7-дневным окном и подтверждением, export через ту же `export_account_data`.
Security hardening: customer-маршруты не адресуют staff/owner/tombstone; export требует step-up (§2.16.1), delete — step-up + confirm; tombstone не реактивируется; leaderboard только текущая эпоха; пагинация 50; nosniff; CSRF-negative test. Security delta verdict — **resolved**. Targeted 19 tests; full suite **1064 tests:
1056 passed, 8 skipped, exit 0**. Остатки R-049 (block SDK-сессии, tombstone credentials) закрыты follow-up задачами `a9e7d2b`/`08ab9c7` — см. §0.16; live CSRF/HTTP not tested; узкая гонка create_session остаётся.

## 0.14. CRM taxonomy — 2026-11-23

`ARCADE-CRM-TAXONOMY-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`98b848c` + minor fixes). `/crm/genres/` и `/crm/tags/` list/create/edit/delete
под `CONTENT_MANAGE`; genre code/sort_order/image + per-language translations;
tag code/needs_translation + translations; delete блокируется при
`GameGenre`/`GameTag`/primary genre; requires-translation queue; audit.
Migration `crm.0006` — choices-only AlterField для новых audit actions (без
изменения структуры/данных БД). Исправлены minor review: queue filter
case-insensitive, очистка заменённого/удалённого genre image после commit,
slug validation. 9 targeted tests; ruff/mypy clean; full suite **1072 tests:
1064 passed, 8 skipped, exit 0**. Остаток: image cleanup при rollback новой
загрузки не гарантирован; live staging/prod NOT TESTED.

## 0.15. CRM ratings moderation — 2026-11-23

`ARCADE-CRM-RATINGS-001` — **COMPLETED / AI HQ REVIEW ACCEPT** (`c577416` +
minor fixes). `/crm/moderation/` ratings: фильтры game/value 1–5/visibility,
сводка overall average и per-value distribution одним aggregate-запросом;
hide/restore с reason и audit не менялись. Исправлены minors: добавлено
пояснение, что сводка считается по всем отфильтрованным оценкам, а таблица
показывает последние 100; убрано silent truncation game-фильтра.
25 targeted tests; ruff/mypy clean; full suite **1075 tests: 1067 passed,
8 skipped, exit 0**. Остаток: строки сверх 100 в таблице не пагинируются
(disclosed); staging/prod NOT TESTED.

## 0.16. R-049 follow-ups — 2026-11-23

`ARCADE-R049-SESSION-REVOCATION-001` (`a9e7d2b`) и
`ARCADE-R049-TOMBSTONE-CREDENTIALS-001` (`08ab9c7`) — **COMPLETED / AI HQ
REVIEW ACCEPT**. Блокировка клиента в одной транзакции переводит его
`created`/`active` GameSession в `aborted`, обнуляет ticket hash/expiry и
binding nonce; activate/heartbeat/submit после этого возвращают
`E_SESSION_EXPIRED`, unblock ничего не переиздаёт. Tombstone-анонимизация
удаляет RecoveryCode/OwnerRecoveryCode, ставит unusable password и очищает
TOTP secret/confirmed/counter. QA pass; targeted tests 17 + 18 + DB-001/CRM
delete; migration guard clean; full suite **1079 tests: 1071 passed,
8 skipped, exit 0**. Остаток R-049: узкая гонка `create_session`
(advisory-lock) с revoke-сканом не сериализована; inverse ordering оставляет
завершённый результат намеренно; live SDK/staging NOT TESTED.

## 0.17. CRM artifact downloads — 2026-11-23

`ARCADE-ARTIFACTS-DOWNLOAD-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`f8c3a52` + docstring fix `91c9c0f`). Staff-only CRM endpoints скачивают
original ZIP побайтово, runtime tree как zip и per-version validation/
autotest/import reports в JSON/Markdown. Пути выводятся только из
`package_hash`/`runtime_hash` через `artifacts.py`, проверяются containment и
symlink; ZIP/runtime требуют step-up, все ответы — attachment с фиксированным
именем, `nosniff`, `private, no-store`; missing/unknown → 404. 6 targeted
tests; full suite **1085 tests: 1077 passed, 8 skipped, exit 0**. Остаток
R-050: TOCTOU при write-доступе к artifact root, runtime zip bytes не
гарантированно стабильны, real nginx/volume E2E NOT TESTED.

## 0.18. CRM game records tab — 2026-11-23

`ARCADE-CRM-GAME-RECORDS-001` — **COMPLETED / AI HQ REVIEW ACCEPT after one
reject** (`db8a835` + docstring fix `551e73e`). В карточке игры CRM появилась
read-only секция текущей таблицы рекордов и архивных эпох: rank/nickname/
value/achieved_at/trust_level, пагинация 25, селектор эпох, empty state.
Порядок и rank переиспользуют публичный `leaderboard_ordering`/`annotate_rank`;
показываются только `is_public=True`, записи не меняются. Первый review
отклонил попытку: ISO-строка передавалась в `|date`, колонка даты была пустой,
а тест проверял только context. Retry перевёл `RecordRow.achieved_at` в
datetime и добавил проверку HTML. 5 targeted tests; full suite **1090 tests:
1082 passed, 8 skipped, exit 0**. Остаток: live browser/staging NOT TESTED.

## 0.19. Catalog genre pagination — 2026-11-23

`ARCADE-CATALOG-GENRE-PAGINATION-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`0c4e64d`). Публичная страница жанра использует общий
`apps/catalog/services/pagination.py`: page bounds/clamping, сохранение
active sort/filters в ссылках, компонент пагинации, canonical и
`noindex,follow` на глубоких страницах; single-page жанр не показывает
pagination chrome. 5 targeted tests + catalog regression; full suite
**1095 tests: 1087 passed, 8 skipped, exit 0**. Остаток: live
HTTP/nginx/staging NOT TESTED; неиспользуемый context-key `games` оставлен
для обратной совместимости (informational).

## 0.20. App F race/idempotency tests — 2026-11-23

`ARCADE-APPF-RACE-TESTS-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`7af18bb`, test-only). Добавлены 8 тестов: параллельные `submit_result`
(ровно один лучший `LeaderboardEntry`, без дублей/потерь), конкурентные
рейтинговые голоса с лимитами ≤1/24h и ≤5/30d + UNIQUE(game,user), storage
со stale If-Match/ETag и конкурентной записью JSONB, повтор
Idempotency-Key. Targeted 8/8; миграций нет; full suite **1103 tests:
1095 passed, 8 skipped, exit 0**. Остаток: тесты service-level, HTTP/CSRF/
throttle/ETag round-trip остаётся на существующих integration-тестах;
live browser/staging NOT TESTED.

## 0.21. Session create race — 2026-11-23

`ARCADE-SESSION-RACE-001` — **COMPLETED / AI HQ REVIEW ACCEPT after one
malformed review retry** (`2ac43e1`). `create_session` внутри транзакции
берёт `select_for_update` на User и перепроверяет `is_active`; `anonymize_user`
берёт тот же User row lock перед revoke-сканом. Сессия не может появиться
для блокируемого/анонимизируемого аккаунта; R-049 в коде закрыт. Два
concurrency-теста (block и anonymise) + 19 CRM users tests; full suite
**1105 tests: 1097 passed, 8 skipped, exit 0**. Остаток: live SDK/staging
NOT TESTED; pre-existing lock-order inversion вынесен в R-051.

## 0.22. Artifact download TOCTOU — 2026-11-23

`ARCADE-ARTIFACTS-TOCTOU-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`75d0159`). Original ZIP и runtime-дерево открываются один раз:
`O_NOFOLLOW`, `fstat`/inode сверяются с разрешённым путём, дочерние entries
открываются через `dir_fd`; symlink/path-swap → `ArtifactUnavailable`.
4 новых TOCTOU-теста + 6 прежних; full suite **1109 tests: 1101 passed,
8 skipped, exit 0**. Остаток R-050: runtime-файлы читаются в память целиком,
runtime zip не hash-verified, real nginx/volume E2E NOT TESTED.

## 0.23. Runtime JSON-schema validation — 2026-11-23

`ARCADE-RUNTIME-JSONSCHEMA-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`855caa1`; tooling fix `3e037c4`). `host_protocol.js` и `ba-sdk.js` валидируют
envelopes/payloads явными per-message schema-таблицами (JSON-Schema-subset)
вместо ad-hoc проверок; нарушения дают структурированный `E_MESSAGE_INVALID`;
vendored SDK-копии синхронизированы. Trusted-envelope spoofing по-прежнему
молча отбрасывается (security-justified). 19/19 JS tests на main (включая
negative/oversized/source/origin/replay); Python contract/package tests
зелёные; full suite **1109 tests: 1101 passed, 8 skipped, exit 0**.
Остатки: R-052 pre-existing `myBest` wire-shape mismatch (follow-up), R-053
ручное зеркалирование схем, browser/staging E2E NOT TESTED.

## 0.24. SDK myBest contract fix — 2026-11-23

`ARCADE-SDK-MYBEST-001` — **COMPLETED / AI HQ REVIEW ACCEPT** (`20f379c`).
Host `bestOnly` теперь отвечает `{entries, myRank}` по
`ba_leaderboard_data`; SDK `myBest` извлекает `{value, achievedAt}` из
единственной entry, `null` при отсутствии; value=0 обрабатывается корректно.
JS **23/23**; full Python suite **1109 tests: 1101 passed, 8 skipped,
exit 0**. Остаток: nickname в bestOnly entry = null (schema-legal); browser
E2E NOT TESTED.

## 0.25. Session API camelCase — 2026-11-23

`ARCADE-SESSION-API-CAMELCASE-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`16068f4`; reviewer-prompt fix `3a91997`). `POST /api/v1/sessions` отдаёт
`{sessionId, ticket, expires_at}` по C-001/SESSION_ID_PROTOCOL; player.js
читает только `sessionId`, dual-handling и snake_case mock-и удалены; SDK уже
использовал camelCase. JS **23/23**, targeted sessions 41/41, full suite
**1109 tests: 1101 passed, 8 skipped, exit 0**. Probe/Playwright E2E NOT
TESTED (нет live dev stack в sandbox); `expires_at` намеренно оставлен
snake_case до отдельного решения (§7), alias не выдаётся — R-054.

## 0.26. Artifact streaming — 2026-11-23

`ARCADE-ARTIFACTS-STREAMING-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`8d22aee` + fixes `167ece6`). Original ZIP проверяется по SHA-256 до
отправки тела и стримится bounded-chunk через проверенный descriptor;
runtime zip пишется в temp-file и отдаётся FileResponse, без `io.BytesIO`.
Corrupted package → `ArtifactUnavailable`/404 без частичного тела; symlink/
path-swap защиты сохранены; spool закрывается при любом исключении.
13 targeted tests; full suite **1112 tests: 1104 passed, 8 skipped,
exit 0**. Остаток R-050: ZIP читается дважды (in-place swap между hash и
stream не детектируется), runtime zip не hash-verified, real nginx/volume
E2E NOT TESTED.

## 0.27. Single-source host schemas — 2026-11-23

`ARCADE-RUNTIME-SCHEMA-SINGLE-SOURCE-001` — **COMPLETED / AI HQ REVIEW
ACCEPT** (`f9a75d4` + generator guard `d1c4e6f`). Host registry
`static/src/js/host_schemas.generated.js` генерируется из
`schemas/messages/*.json` (flatten `$ref`/`allOf`), parity test падает при
drift; generator отвергает неподдерживаемые JSON-Schema keywords вместо
тихого drop. Wire-поведение для SDK/host сохранено; DRAFT-схемы уточнены
(лимиты/maxLength) — R-055. JS 23/23; full suite **1113 tests: 1105 passed,
8 skipped, exit 0**. Остаток: `npm run build` не вызывает генерацию (drift
ловится тестом); browser/staging E2E NOT TESTED.

## 0.28. App F lock order — 2026-11-23/24

`ARCADE-SESSION-LOCK-ORDER-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`92ef3b1` + comment fix `f871f06`). `submit_result` и `heartbeat` берут
User row lock до GameSession, как `create_session`/`anonymize_user`;
`submit_result` дополнительно проверяет `is_active` под локом. Три
concurrency-теста (submit vs anonymize/block, heartbeat); targeted 22/22 и
race suite 8/8; full suite **1116 tests: 1108 passed, 8 skipped, exit 0**.
R-051 закрыт. Остаток: R-056 `put_storage` вне scope; live load/staging
E2E NOT TESTED.

## 0.29. CRM moderation pagination — 2026-11-24

`ARCADE-CRM-MODERATION-PAGINATION-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`07a287a` + fix `380cd11`). Очереди оценок и жалоб пагинируются по 50;
rating-сводка считается по всему filtered set, не по странице; фильтры
game/value/status и обе page-позиции сохраняются при переходе между
страницами любой очереди. 13 targeted tests (120 votes + 120 complaints,
page 2, summary=120); full suite **1117 tests: 1109 passed, 8 skipped,
exit 0**. Остаток: browser/staging NOT TESTED.

## 0.30. Storage lock order — 2026-11-24

`ARCADE-STORAGE-LOCK-ORDER-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`bcd99a7`). `put_storage` для user subject берёт User row lock до storage
advisory/row и перепроверяет `is_active`; guest-ветка не изменена. Запись не
может появиться после anonymize/block, FK deadlock cycle устранён. Четыре
parametrized race-теста с anonymize/block; targeted 26/26; full suite
**1121 tests: 1113 passed, 8 skipped, exit 0**. R-056 закрыт. Остаток:
live load/staging E2E NOT TESTED.

## 0.31. Artifact single-pass hash — 2026-11-24

`ARCADE-ARTIFACTS-SINGLE-PASS-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`ee9e9c4`). Original ZIP читается из проверенного `O_NOFOLLOW` handle один
раз: копируется в temp spool с одновременным SHA-256, сравнивается с
`package_hash`, и отдаётся только проверенный spool; mismatch → 404 без
единого байта тела. Double-read/in-place-swap окно устранено. 15 targeted
tests (byte-exact, mutation, chunked, symlink/swap); full suite **1123
tests: 1115 passed, 8 skipped, exit 0**. R-050 закрыт в коде; остаток:
runtime zip не hash-verified, real nginx/volume E2E NOT TESTED.

## 0.32. Runtime hash verification — 2026-11-24

`ARCADE-RUNTIME-HASH-VERIFY-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`8f9f7ac`). CRM runtime download собирает zip через verified-descriptor walk,
накапливает per-file SHA-256 по arcname и сравнивает канонический tree digest
(`name\0hex\n`, `runtime_hash_for`) с `version.runtime_hash` до отдачи;
mismatch → `ArtifactUnavailable`/404 без тела. 17 targeted artifact tests
(valid/mismatch); full suite **1125 tests: 1117 passed, 8 skipped, exit 0**.
R-050 закрыт в коде; остаток: real nginx/volume E2E и нагрузка больших
runtime NOT TESTED.

## 0.33. SDK pending-request abort — 2026-11-24

`ARCADE-SDK-ABORT-PENDING-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`ebe7d30` + test cleanup `b34a288`). При `exit()`/`ba:newSession` SDK
немедленно settle-ит все pending-запросы (`E_TIMEOUT`/cancelled), удаляет их
таймеры и игнорирует late responses; `newSession`-запрос не отменяет сам
себя. Три JS-теста; JS **26/26**; full Python suite **1125 tests: 1117
passed, 8 skipped, exit 0**. Остаток: browser/staging E2E NOT TESTED.

`ARCADE-RUNTIME-BUILD-SCHEMAS-001` — **BLOCKED**: wiring schema generation в
`npm run build` ломает Docker assets stage (`scripts/`/`schemas/` не
копируются, node:22-slim без python3). Drift уже ловится parity-тестом и
`check:schemas`; изменение Dockerfile вне согласованного scope.

## 0.34. AI HQ P0 foundation — 2026-11-24

**AI-HQ-CI-001** (`a0aa34b`) — **IMPLEMENTED / INDEPENDENT REVIEW ACCEPT;
GitHub CI run NOT VERIFIED** (нет `gh`/токена в среде). Добавлены
`redis-throttle` service и `REDIS_THROTTLE_URL` в CI, ruff/mypy расширены на
`autonomy/` и `scripts/`, исправлен `self_check` в FakeRunner, обновлён
sandbox-copy тест, добавлен отдельный диагностический coverage step с
`COVERAGE_FILE=.coverage.autonomy`. Локально: 38 affected tests, mypy 381
файл clean, coverage autonomy/devcontrol 73 %.

**AI-HQ-A1** (`1f46062`) — **COMPLETED / SECURITY-AUDITOR ACCEPT** после
трёх раундов. Developer/QA больше не могут запускать host
pytest/mypy/ruff/npm: разрешены только пять точных команд trusted
main-checkout раннера (`--source-root . --tool pytest|pytest
migrations_check|ruff|mypy|js --timeout 1800`), без wildcard и shell-чейнинга.
Раннер принимает только реальный linked worktree под `.autonomy/worktrees`,
требует `BA_TASK_WORKTREE`, проверяет `.git`-файл/gitdir, копирует без
`.env/certs/creds`; JS запускается в node-only read-only контейнере, Python —
в прежнем secret-free контейнере. `_changed_files` выводит коммитимый набор
из Git, а не из отчёта разработчика; `PROTECTED_PARTS` закрывает
autonomy/devcontrol/scripts/agents/skills/workflows/infra/sdk/schemas/
Dockerfile/Makefile/package/pre-commit/compose; reviewer лишён Bash.
Full suite **1130 tests: 1122 passed, 8 skipped, exit 0**. Остатки: R-040
OS-sandbox, полный suite вместо targeted на каждый запуск, продуктовый
`apps/` исполняется в web-контейнере с секретами (осознанная модель),
динамическая семантика exact-match CLI не проверена.

## 0.35. AI HQ A2 — immutable candidate QA — 2026-11-24

**AI-HQ-A2** (`45a69f1`) — **COMPLETED / SECURITY-AUDITOR ACCEPT**.
Developer changes коммитятся в candidate до QA; QA запускается в отдельном
чистом worktree на точном candidate SHA, не может редактировать код; reviewer
получает полный diff без 40k-усечения; QA/reviewer JSON строгий (malformed →
reject, не merge); коммитимый набор выводится из Git, а не из отчёта
developer; merge только после QA pass и reviewer accept; при любом сбое оба
worktree удаляются, main не меняется. 23 affected tests; strict-verdict и
malformed-review tests; full suite **1132 tests: 1124 passed, 8 skipped,
exit 0**. Остатки: QA/reviewer всё ещё доверенные модели (M1), очень большой
diff может исчерпать argv/context (fail-closed), R-040.

## 0.36. Game session lifecycle — 2026-11-24

**B1a** `ARCADE-SESSION-LIFECYCLE-001` (`7da168a`) — **COMPLETED /
CODE-REVIEW ACCEPT**: stale ACTIVE sessions (idle >30 мин или
`max_session_seconds`) лениво истекают при create/activate до проверки cap;
двухфазный захват session locks исключает deadlock с play-credit; beat task
каждые 5 минут идемпотентно истекает и начисляет popularity credit; при
истечении/close кредит не дублируется. 46 session tests, включая
create-sweep vs beat-task race.

**B1b** `ARCADE-SESSION-PLAY-001` (`35ae98f`) — **COMPLETED / CODE-REVIEW
ACCEPT**: `GET /play/` больше не создаёт/активирует сессию и не ставит
`ba_anon`; страница — shell с CSRF/runtime base. Player.js создаёт и
активирует сессию через существующий POST API, только затем создаёт
HostBridge и ставит iframe `src` с `&s=<sessionId>`; ticket остаётся в памяти
родителя; ошибка create видна в `player-status`. Play-тесты 3/3; e2e ожидание
async `src` исправлено, реальный Playwright E2E **NOT TESTED**.

**B1c** `ARCADE-SESSION-HEARTBEAT-SUBMIT-001` (`f7a3779`) — **COMPLETED /
CODE-REVIEW ACCEPT**: перед submit отправляется финальный heartbeat; 410
всплывает сразу, транзиентный сбой не блокирует попытку result, Idempotency-
Key не изменён.

**B1d** `ARCADE-SESSION-PAGEHIDE-001` (`cb92702`) — pagehide отправляет best-effort close
через same-origin `fetch(..., keepalive:true)` с `X-CSRFToken`; sendBeacon
оставлен только fallback без fetch, потому что form-encoded CSRF не проходит
DRF-аутентификацию close API. Close идемпотентен. JS **31/31**; полный Python
suite **1137 tests: 1129 passed, 8 skipped, exit 0**. Остатки: live beat/Redis
и реальный браузерный E2E NOT TESTED; pagehide не гарантирован при kill
браузера.

## 0.53. Player submit/restart race — 2026-11-25

`ARCADE-SUBMIT-RESTART-001` (`24d9979` + `a81ec48`) — **COMPLETED /
CODE-REVIEW ACCEPT**: игра больше не может запустить следующую сессию,
пока результат предыдущей в пути. Сабмиты одной сессии сериализуются
promise-chain с общим `Idempotency-Key`; `newSession`/`exit` ждут
завершения chain (с перепроверкой, если submit пришёл во время ожидания)
и только затем закрывают сессию/создают новую; два перезапуска
сериализуются. Каждая API-попытка ограничена `AbortSignal.timeout(10s)`,
поэтому зависшая сеть не блокирует restart навсегда. Старые
leaderboard/storage-ответы по-прежнему отбрасываются после смены сессии.
Проверки: обновлённый `player_race` (JS **31/31**), `check:js` clean,
player contract 4 passed. Модели: реализация — `deepseek-flash[1m]`,
review — `code-reviewer` (`deepseek-v4-pro`, text-only), ACCEPT. Остатки
вынесены в `ARCADE-SUBMIT-RESTART-HARDENING-001` (exit vs pending
newSession, тесты exit/двойного restart/позднего submit, молчаливый дроп
граничного submit); реальный browser E2E и staging NOT TESTED.

## 0.52. Nightly rating aggregate recalc — 2026-11-25

`ARCADE-RATINGS-NIGHTLY-001` (`006aaca` + `b24ff78` + `4c5dd02`) —
**COMPLETED / CODE-REVIEW ACCEPT**: ТЗ §2.9 требует ночного пересчёта
агрегатов. `recalculate_all` берёт union игр с голосами и существующими
агрегатами, идёт по возрастанию pk, на каждую игру открывает отдельную
транзакцию с одним advisory lock; при совпадении total/count/average/
wr_score/distribution запись не делается, поэтому `recalculated_at` не
двигается и повторный прогон даёт `updated=0`. Dry-run не берёт локов и не
пишет; ошибка одной игры логируется с `game_id` и не останавливает
остальные, soft-timeout пробрасывается. Добавлены дневная beat-задача
`ratings-nightly-recalc` (acks_late, reject_on_worker_lost, 2400/3000 s) и
команда `recalculate_ratings --dry-run --limit N` с ненулевым exit при
ошибках. Проверки: 12 nightly tests, полный suite **1230 tests: 1217
passed, 13 skipped, exit 0**; ruff/format/mypy clean (387);
`makemigrations --check` без изменений. Модели: реализация —
`deepseek-flash[1m]`, plan — `architect`, review — `code-reviewer`
(`deepseek-v4-pro`, text-only), ACCEPT + delta ACCEPT. Остатки: `--limit`
без offset, 6 запросов на игру, 24-часовой catch-up после timeout; live
beat/worker NOT TESTED.

## 0.51. ZIP worker least-privilege env — 2026-11-25

`ARCADE-ZIP-WORKER-SECRETS-001` (`1c19af5` + `d90af22` + `1cbbec3`) —
**COMPLETED / SECURITY-AUDITOR ACCEPT**: изолированный `zip-worker`,
разбирающий недоверенные ZIP, больше не получает полный `.env`. Удалён
`env_file` в base и staging; воркеру передаются ровно 13 не-секретных
переменных: `DJANGO_SETTINGS_MODULE`, `CELERY_BROKER_URL`, `RUN_*`, четыре
переменные квоты и пять worker-side лимитов/TTL. Значения интерполируются
из `.env`/`.env.staging`, сохраняя паритет брокера и лимитов с web.
Проверки: 11 compose tests (exact allowlist, secret-name denylist, quota
parity, defaults vs `base.py`, overlay non-widening, prod pin); полный
suite **1218 tests: 1205 passed, 13 skipped, exit 0**; ruff/format/mypy
clean (384). Live dev: worker healthy, env — только allowlist и системные
переменные, broker URL hash совпал с web, benign probe ZIP прошёл
web→Redis→zip-worker→`COMPLETED.json`, DB/cache DNS недоступны; артефакты
удалены. Модели: реализация — `deepseek-flash[1m]`, plan — `architect`,
review — `security-auditor` (`deepseek-v4-pro`, text-only). Остатки:
dev-lite `.:/app:ro` (M1), пустой `SECRET_KEY` fail-loud (M3), пароль
брокера при requirepass (M4), Sentry из воркера не отправляется (M5);
live staging/prod NOT TESTED.

## 0.50. Complete i18n reseed for reuse-DB — 2026-11-25

`ARCADE-TEST-DB-SEED-001` (`8e5f507` + `995f5d2`) — **COMPLETED**:
transaction-тесты делают flush, а fixture восстанавливал только i18n
0002/0003, поэтому reuse-DB прогон падал на страницах, которым нужны строки
0004-0012. Теперь seed-модули собираются динамически из
`apps/i18n/migrations/[0-9]*_seed_*.py` в порядке миграций (11 модулей),
вызываются идемпотентные `seed_languages`/`seed_strings` перед каждым
transaction-тестом и после teardown; пустой glob или модуль без известной
функции даёт RuntimeError. Проверки: полный suite **1214 tests: 1201
passed, 13 skipped, exit 0** на reuse-DB без `--create-db` (13:00);
targeted transaction+home 4 passed; ruff/format/mypy clean. Модели:
реализация — `deepseek-flash[1m]`, review — `code-reviewer`
(`deepseek-v4-pro`, text-only), ACCEPT + delta ACCEPT. Остатки: прерывание
после flush до teardown-reseed требует следующего transaction-прогона;
один редкий step-up флейк moderation не воспроизведён; продукт не менялся.

## 0.49. Orphan runtime TTL cleanup — 2026-11-25

`ARCADE-RUNTIME-ORPHAN-001` (`34f237f`) — **COMPLETED / CODE-REVIEW ACCEPT**:
runtime-каталоги, на hash которых не ссылается ни одна `GameVersion`,
удаляются по TTL. `cleanup_orphan_runtimes` сканирует обе раскладки
(`<hash>/` и `host_label/<hash>/`), пропускает symlink, не-hash имена,
каталоги моложе `ZIP_RUNTIME_ORPHAN_TTL_SECONDS` (default 24 ч) и ошибки
rmtree; ссылки читаются из `GameVersion.runtime_hash`. Beat-задача
`cleanup_orphan_runtimes` выполняется раз в сутки (acks_late,
reject_on_worker_lost, time limits 240/300), идемпотентна и логирует
`pipeline.runtime_orphan_removed`. Default worker теперь монтирует
`runtime_data` rw и получает `ZIP_PUBLIC_RUNTIME_ROOT=/app/runtime` — без
этого cleanup был молчаливым no-op (поймано review). Проверки: 4 новых
теста (referenced/expired/fresh/symlink/flat, идемпотентность, beat/task
registration, missing/symlink root) + compose regression; полный suite
**1214 tests: 1201 passed, 13 skipped, exit 0** на свежей БД; ruff/format/
mypy clean (383). Live: worker пересоздан с rw-томом, aged orphan удалён,
событие в логе. Модели: реализация — `deepseek-flash[1m]`, review —
`code-reviewer` (`deepseek-v4-pro`, text-only), reject (missing mount) →
delta accept. §5.5 закрыт; остатки — live beat/staging NOT TESTED,
protect-по-ссылке проверен unit-тестами (dev-БД без `GameVersion`).

## 0.48. Concurrent same-game import — 2026-11-25

`ARCADE-ZIP-CONCURRENT-IMPORT-001` (`03aaf0f`) — **COMPLETED /
CODE-REVIEW ACCEPT**: два одновременных импорта нового `technical_id`
больше не создают две карточки. `_persist` первым делом берёт
`pg_advisory_xact_lock` по lowercased `technical_id`, затем под
`select_for_update` повторно читает `Game` и усыновляет карточку,
созданную параллельным импортом; `created`/`updated` и отчёт
пересчитываются. `IntegrityError` с constraint
`catalog_game_technical_id_key` репортится как новый `V_ID_CONFLICT`,
остальные — `V_VERSION_DUP`. `store_runtime` при проигранной rename-гонке
проверяет хэш существующего target и возвращает идентичный бандл.
Проверки: реальный двухпоточный импорт (ровно одна Game/Version, статусы
created+duplicate), spy на advisory lock, adoption-тест,
constraint-классификация, forced rename-race и tampered-target; полный
suite **1210 tests: 1197 passed, 13 skipped, exit 0** на свежей БД;
ruff/format/mypy clean (383). Модели: реализация — `deepseek-flash[1m]`,
review — `code-reviewer` (`deepseek-v4-pro`, text-only), reject → delta
accept. Остатки: orphan runtime закрыт в `ARCADE-RUNTIME-ORPHAN-001`
(`34f237f`); error-code асимметрия rename-ветки; отчёт может содержать
I_IMPORT_CREATED после rollback (cosmetic); threaded-тест без barrier
(как принятый App F harness); `manifest["id"]` vs get; live staging
NOT TESTED.

## 0.47. Stale ZIP job reaper — 2026-11-25

`ARCADE-ZIP-JOB-REAPER-001` (`1687517`) — **COMPLETED / CODE-REVIEW ACCEPT**:
`reap_stale_extraction_jobs` идемпотентно переводит `ZipExtractionJob` в
RUNNING старше `ZIP_JOB_STALE_SECONDS` (default 600 s; fallback на
`created_at`, если `started_at` пуст) в TIMEOUT с `X_JOB_STALE`,
`finished_at` и `updated_at`; UPDATE защищён `status=RUNNING`, поэтому
повторный reaper и терминальные задания не затрагиваются. Beat-задача
`reap_stale_zip_jobs` выполняется каждые 5 минут (time limits 240/300);
позднее завершение web-импорта остаётся авторитетным и перезаписывает
timeout. 3 reaper tests (stale/recent/exact-TTL/null-started, terminal и
queued не трогаются, идемпотентность, task body, beat entry); полный suite
**1203 tests: 1190 passed, 13 skipped, exit 0** на свежей БД; ruff/format/
mypy clean (383). Модели: реализация — `deepseek-flash[1m]`, review —
`code-reviewer` (`deepseek-v4-pro`, text-only), accept после delta.
Остатки: beat только при включённом profile `beat` (операционно); нет
CANCEL-маркера для queued worker (bounded deadline/cleanup); draft остаётся
`uploaded` до 7-дневного purge; инвариант TTL > wait+deadline не
проверяется на старте; OR-запрос использует status-индекс; новый env не
внесён в BA-ENV (owner-контракт); live beat NOT TESTED.

## 0.46. Reset tokens invalidated on email change — 2026-11-25

`ARCADE-EMAIL-RESET-INVALIDATION-001` (`26d8075`) — **COMPLETED /
SECURITY-AUDITOR ACCEPT**: password-reset ссылка, выданная на старый адрес,
больше не действует после смены/удаления email. Изменение email
инвалидирует `PASSWORD_RESET` и `EMAIL_VERIFY` в той же транзакции, что и
запись `EmailAddress`; удаление делает delete+invalidate атомарно.
`password_reset_confirm` после consume проверяет, что у пользователя есть
verified-адрес, совпадающий с email токена (casefold), и что аккаунт
активен; иначе нейтральный redirect без смены пароля. Токены неактивных
аккаунтов не принимаются. 25 `test_accounts` (смена/удаление инвалидируют
токен, старый пароль остаётся; confirm-mismatch с живым токеном; полный
reset flow); полный suite **1200 tests: 1187 passed, 13 skipped, exit 0**
на свежей БД; ruff/format/mypy clean (382). Модели: реализация —
`deepseek-flash[1m]`, review — `security-auditor` (`deepseek-v4-pro`,
text-only), accept после delta. Остатки: строгий submission-order race
(`ARCADE-EMAIL-RESET-RACE-001`; эффективный порядок линеаризуем, фикс
требует единого lock order); timing-oracle в `password_reset_request`
(pre-existing); single-address assumption; inactive-token остаётся unused
до reactivation; live staging NOT TESTED.

## 0.45. Verified restore-check — 2026-11-25

`ARCADE-RESTORE-CHECK-001` (`cdb567a`) — **COMPLETED / SECURITY-AUDITOR
ACCEPT**: restore-check больше не объявляет SUCCESS по одному числу таблиц.
Отклоняются отсутствующий/пустой/недоступный дамп; SHA-256 сверяется с
успешным `BackupRun` до любых операций с БД и повторно после `pg_restore`;
DROP выполняется с `WITH (FORCE)`; после restore проверяются непустой
`public`, все `REQUIRED_TABLES` (accounts/catalog/gameplay/crm core,
`django_migrations`) и непустая `django_migrations`. В `BackupRun.meta`
пишутся `backup_run_id`, `sha256`, `table_count`, `required_tables`,
`migration_count`; нечисловой SQL-ответ — ошибка; pre-flight OSError
завершает run как failed. 22 unit-теста; полный suite
**1197 tests: 1184 passed, 13 skipped, exit 0** на свежей БД; ruff/format/
mypy clean (382). **Реальный restore на dev** текущим кодом:
`OK verified_at=2026-11-25 01:42:13`, metadata 44 таблицы / 42 миграции /
10 обязательных таблиц, temp DB удалена; staging/production NOT TESTED.
Модели: реализация — `deepseek-flash[1m]`, review — `security-auditor`
(`deepseek-v4-pro`, text-only), accept после delta. Остатки: swap A→B→A
вокруг pg_restore (staff-level FS; закрытие — `/proc/self/fd/N`); нет
advisory-lock между одновременными проверками (spurious visible failure,
не false SUCCESS); проверка структурная, не построчная; роль-суперюзер
БД — owner-gated §5.4; cron использует baked image (нужен rebuild для
нового кода); file-level S608 noqa.

## 0.44. Malformed Content-Length — 2026-11-25

`ARCADE-CONTENT-LENGTH-001` (`ab62a7d`) — **COMPLETED / CODE-REVIEW ACCEPT**:
`SessionResultView` больше не парсит `CONTENT_LENGTH` незащищённым `int()`.
Отсутствующий/пустой заголовок трактуется как 0, нечисловой/отрицательный —
400 `E_INVALID_REQUEST`, превышение лимита — 413 `E_PAYLOAD_TOO_LARGE`;
except-кортеж parenthesized с `# fmt: skip`, чтобы форматтер не переписал
его в PEP 758-форму. Unit-тесты покрывают missing/empty/0/MAX/5000 digits,
non-numeric, negative и oversized; dispatch-level интеграционный тест
проверяет реальный authenticated/CSRF запрос к result-маршруту с
некорректным заголовком. Полный suite **1188 tests: 1175 passed,
13 skipped, exit 0** на свежей БД; ruff/format/mypy clean (382). Модели:
реализация — `deepseek-flash[1m]`, review — `code-reviewer`
(`deepseek-v4-pro`, text-only), reject → delta accept. Попутно исправлен
независимый time-flake `test_credit_window_counts_unique_once_per_30_minutes`
(`116efbd`): фиксированное UTC-полдне вместо `timezone.now()`, иначе прогон
через полночь UTC разносил кредиты по двум строкам `GameDailyStats`.
Остатки: `int()` лоялен к пробелам/`+`/подчёркиваниям/unicode-цифрам (как
Django/DRF), не 500; chunked/без Content-Length отклоняется DRF
(pre-existing); 413 через dispatch не тестировался; live gunicorn/nginx
NOT TESTED.

## 0.43. Blocked votes excluded immediately — 2026-11-25

`ARCADE-RATINGS-BLOCK-001` (`766029e`) — **COMPLETED / SECURITY-AUDITOR
ACCEPT**: `recalculate_user_ratings(user)` пересчитывает все игры
пользователя в детерминированном порядке `game_id`, поэтому multi-game
advisory locks берутся по возрастанию и block/unblock, staff
activation/deactivation и удаление аккаунта не могут образовать
deadlock-цикл. Helper вызывается на каждом реальном переходе `is_active`;
`vote()` внутри транзакции берёт User row lock и повторно проверяет
`is_active` до advisory lock, поэтому block, закоммиченный после быстрой
проверки, отклоняет голос. Оценки остаются в БД и возвращаются в агрегат
при unblock (TS §2.9 п.4). 5 `test_ratings_block` (исключение/восстановление,
детерминированный порядок на non-monotonic UUIDv4, stale-active отказ,
unblock не-голосовавшего, recalculate-фильтр) + 30 related CRM/ratings;
полный suite **1183 tests: 1170 passed, 13 skipped, exit 0** на свежей БД;
ruff/format/mypy clean (382). Модели: реализация — `deepseek-flash[1m]`,
review — `security-auditor` (`deepseek-v4-pro`, text-only), **accept** после
delta. Остатки: thread-based block-vs-vote race test отложен из-за
`ARCADE-TEST-DB-SEED-001`; ночной пересчёт и deploy-backfill для уже
заблокированных — `ARCADE-RATINGS-NIGHTLY-001`; block тяжёлого
голосовавшего — O(votes) запросов под lock; `activate_session`/`heartbeat`
is_active — session residual; live staging NOT TESTED.

## 0.42. Explicit CRM block/unblock — 2026-11-24

`ARCADE-CRM-BLOCK-IDEMPOTENT-001` (`88c2a64`) — **COMPLETED /
SECURITY-AUDITOR ACCEPT**: `/block/` и `/unblock/` больше не вызывают один
toggle. `_set_user_active` под User row lock выставляет запрошенное
состояние: повторный block не разблокирует, повторный unblock не блокирует,
no-op не пишет audit и не повторяет revoke; реальный переход сохраняет
прежний audit `USER_BLOCKED`/`USER_UNBLOCKED` и отзыв SDK-сессий/билетов при
блокировке, tombstone/self guards сохранены. Detail POST принимает только
явные `block`/`unblock`/`delete`; маршруты `toggle/` и `toggle-block/`
удалены. 27 `test_crm_users` (идемпотентность, ровно один audit,
authentication flip, tombstone, block-vs-submit/anonymise/storage/
create-session races); полный suite **1178 tests: 1165 passed, 13 skipped,
exit 0** на свежей БД (прогон ~65 мин из-за нагрузки); ruff/format/mypy
clean (382). Модели: реализация — `deepseek-flash[1m]`, review —
`security-auditor` (`deepseek-v4-pro`, text-only), **accept**.
Остатки: оценки заблокированных исключаются из денормализованного агрегата
только фильтром чтения/ночным пересчётом — следующая задача
`ARCADE-RATINGS-BLOCK-001`; no-op block не повторяет revoke
(теоретическое legacy-окно); `activate_session`/`heartbeat` не
перепроверяют `is_active` под lock (отдельный legacy-срез); tombstone-
сообщение для block сформулировано как «разблокировать»; unblock не входит
в 403/CSRF матрицу; step-up для block не требуется по §2.16.1; live staging
NOT TESTED.

## 0.41. Safe rollback and publication history — 2026-11-24

`ARCADE-ROLLBACK-SAFE-001` (`ecfb419`) — **COMPLETED / SECURITY-AUDITOR
ACCEPT**: `publish_version` и `rollback_version` пишут append-only
`AdminAuditLog` в одной транзакции с переключением `current_version`
(actor/IP, before/after); CRM-view и wizard больше не пишут второй audit.
Rollback разрешён только на версию, которая уже фигурирует в истории
публикаций, проходит validation (0 blockers) и autotest, и совпадает по
score direction/schemaVersion с фактической текущей опубликованной версией
(manifest, не import-time поля `Game`). Статус игры сохраняется:
published/hidden/archived допустимы, hidden/archived не перепубликуются,
draft/review отклоняются; rollback никогда не выставляет `published`.
Новые причины: `V_NOT_PUBLISHED`, `V_GAME_NOT_PUBLISHED`,
`V_SCORE_RULES_CHANGED`. 12 rollback tests + обновлённые CRM audit/step-up
тесты; полный suite **1177 tests: 1164 passed, 13 skipped, exit 0** на
свежей БД; ruff/format/mypy clean (382). Модели: реализация —
`deepseek-flash[1m]`, review — `security-auditor` (`deepseek-v4-pro`,
text-only), reject → delta accept; ложная syntax-находка (PEP 758)
опровергнута `ast.parse` и реальным импортом на Python 3.14.10.
Остатки: concurrency publish-vs-rollback test заблокирован
`ARCADE-TEST-DB-SEED-001` (row locking корректен по static review);
публикации до появления CRM-аудита и dev `probe_seed` не дают истории —
rollback консервативно блокируется; будущий scheduled-publish task обязан
вызывать `publish_version`; смена score rules требует owner-решения об
эпохе и сейчас блокируется; live staging NOT TESTED. Один полный прогон
упал 1165 errors из-за `DuplicateDatabase`/`ObjectInUse` после
остановленного предыдущего прогона; после очистки сессий gate зелёный.

## 0.40. Registration limits and real-Redis atomicity — 2026-11-24

`ARCADE-REGISTRATION-LIMITS-001` (`bbfdcaf`) — **IMPLEMENTED /
SECURITY-AUDITOR ACCEPT; OWNER DECISION REQUIRED**: регистрация ограничена
device 3/сутки + IP 30/сутки (было 3/сутки только по IP). Device key —
хэш CSRF-cookie с fallback `nocookie:<normalized IP>`; слот резервируется до
валидации и возвращается при невалидной форме/ошибке сохранения,
сохраняется при успехе. IPv6 /64 и IPv4-mapped collapse применяются к
device/IP ключам. Review обнаружил блокирующий дефект: pickle-сериализатор
throttle-кэша ломал атомарный INCR на реальном Redis, django-redis
переходил на неатомарный GET/SET; добавлен JSON-сериализатор (закрывает
также real-Redis неатомарность `de08292`), `ConnectionInterrupted` включён
в fail-closed, добавлен real-Redis конкурентный тест (29 seed + 20 потоков
→ ровно один allowed) и view-lifecycle тесты reserve/release.
49 targeted; полный suite **1166 tests: 1153 passed, 13 skipped, exit 0**
на свежей БД; ruff/format/mypy clean (382). Модели: реализация —
`deepseek-flash[1m]`, review — `security-auditor` (`deepseek-v4-pro`,
text-only), reject → delta accept.

**OWNER DECISION REQUIRED — расхождения с Приложением E:** (1) device key
через CSRF ротируется при login, поэтому 3/сутки на устройство фактически
~1/token-cycle; строгий device-лимит требует signed device cookie и
обновления cookie policy/legal. (2) Appendix E требует challenge после 3 и
жёсткий блок 100; реализован hard 30/day без challenge, а denied attempts
сохраняют слоты — burst может временно блокировать NAT. Binding-контроль
сейчас — атомарный IP 30/сутки. Остатки: release get/decr TOCTOU;
production trusted-proxy allowlist; live load/staging NOT TESTED.

## 0.39. Account security throttling — 2026-11-24

`ARCADE-AUTH-THROTTLE-001` (`de08292`) — **COMPLETED / SECURITY-AUDITOR
ACCEPT**: счётчики входа/2FA/восстановления/регистрации переведены с общего
allkeys-lru cache на выделенный `throttle` (noeviction) с socket timeouts
1 s. `login_attempt`/`two_factor_attempt` атомарно резервируют попытку до
аутентификации (Argon2) — 5/15 мин и 10/15 мин на аккаунт; успех очищает
аккаунтный счётчик; IP считает только неудачи (60/15 и 30/15). Password
reset — 3/ч на аккаунт и 20/ч на IP, каждый запрос; регистрация резервирует
слот 3/сутки на IP (device key — следующая задача) и возвращает его при
невалидной форме или ошибке сохранения. Security-critical лимиты (auth и
complaints) при отказе Redis fail-closed: нейтральный 503 для форм и 429
`E_RATE_LIMIT` для complaints; публичные игровые лимиты остаются fail-open.
IPv6 агрегируется /64 общим helper'ом `apps/core/net.py`; reset-бакет
использует `casefold`; неудачный owner-recovery пишет `EVENT_2FA_FAILED`.
43 targeted tests (20-поточный login cap, IPv6 /64, 2FA/reset IP-лимиты,
release, fail-closed формы/complaints); полный suite
**1159 tests: 1146 passed, 13 skipped, exit 0** на свежей БД; ruff/format/
mypy clean (382 файла). Модели: реализация — `deepseek-flash[1m]`, review —
`security-auditor` (`deepseek-v4-pro`, text-only), initial + delta accept.
Остатки: account-lockout DoS — свойство выбранной политики; IP-failure
счётчики неатомарны (кратковременный burst overshoot); TTL-repair через
best-effort delete без Lua; malformed 2FA не увеличивает IP-failures; shared
unknown-IP bucket только при misconfigured deployment; device key регистрации
(`ARCADE-REGISTRATION-LIMITS-001`); challenge O4; live Redis/load/staging
NOT TESTED.

## 0.38. Game API throttling scopes — 2026-11-24

`ARCADE-THROTTLE-001` (`b953419`) — **COMPLETED / SECURITY-AUDITOR ACCEPT**:
create/activate/close больше не делят бакет `sessions`. Create остаётся
subject 30/ч + guest-IP 600/ч; activate и close получили отдельные
subject-бакеты 30/ч (Приложение E не задаёт их ставку; активаций и закрытий
не может быть больше созданий). Results получил вторичный IP-лимит 1200/ч
(subject 60/ч). Complaints приведены к Приложению E: 5/сутки на субъект +
30/сутки на IP вместо 20/сутки subject-only; IP-порог ограничивает rotation
гостевых identity до нормативного значения. 9 targeted tests (включая
seeded-bucket 429 в обе стороны и IP-лимиты); полный suite
**1147 tests: 1134 passed, 13 skipped, exit 0** на свежей БД; ruff/format/
mypy clean. Модели: реализация — `deepseek-flash[1m]`, review —
`security-auditor` (`deepseek-v4-pro`, text-only).
Остатки: authenticated users освобождены от `sessions_ip` (pre-existing;
решение владельца или challenge); heartbeat bucket привязан к URL session_id
и позволяет mint новые бакеты невалидными id; reports остаются fail-open при
отказе throttle-Redis; у throttle cache нет socket timeouts; challenge
Приложения E не реализован (owner O4); DRF list-счётчики неатомарны.
Следующие задачи — `ARCADE-AUTH-THROTTLE-001` (атомарные login/2FA/reset,
fail-closed) и `ARCADE-REGISTRATION-LIMITS-001` (device 3/сутки + IP
30/сутки).

## 0.37. Result verification bypass — 2026-11-24

`ARCADE-RESULT-VERIFICATION-001` (`1fc0e97`) — **COMPLETED /
SECURITY-AUDITOR ACCEPT**: при непустом `verification.profile` результат без
`eventLog` получает `missing_event_log`, без непустого `seed` — `missing_seed`;
оба варианта quarantined, `LeaderboardEntry` не создаётся. Пустой manifest-
profile больше не маскирует game-level profile. Валидные `eventLog`+`seed`
по-прежнему получают heuristic-validated; игры без профиля сохраняют
client-reported политику; `leaderboard_only_verified` не изменён.
25 targeted result tests (missing log, missing/blank seed, valid path);
полный suite **1144 tests: 1131 passed, 13 skipped, exit 0** на свежей БД;
ruff/format/mypy clean. Модели: реализация — `deepseek-flash[1m]`,
независимый review — `security-auditor` (`deepseek-v4-pro`, text-only).
Остатки: heuristic baseline допускает пустой `events` при совпадающем seed;
live staging NOT TESTED.

Примечание о тестовой БД: первый прогон с `--reuse-db` дал 20 падений
catalog/home/profile из-за отсутствующих i18n seed-строк — transaction-тесты
делают flush, а `tests/conftest.py` восстанавливает только миграции
0002/0003. На свежей БД полный suite зелёный; это дефект тестовой
инфраструктуры, не продуктового кода. Отдельная задача — расширить reseed
на все i18n seed-миграции.

## 1. Текущий статус

**Проект находится в состоянии каркаса, не MVP.** Этап 0 формально **не
закрыт**; этап 1 **не завершён**. `BA-STAGE-1.1` — ограниченный срез этапа 1,
**NOT_ACCEPTED**. `BA-FIX-001` остаётся открытой, `BA-FIX-003` принят с
некритичными замечаниями.

Принятие **Documentation Block 1** (BA-DOC-001 + FIX-01/02/03) не означает
принятия технического этапа 0, этапа 1 или `BA-STAGE-1.1`. App F в целом не
готов к продуктовой приёмке: реализованы серверные срезы и runtime A+B
(**IMPLEMENTED / TECHNICAL REVIEW**); серверный session/ticket срез
**APPF-SESSION-001** **ACCEPTED** владельцем 2026-11-20; `BA-APPF-002`
**запущена частично** (DB-001/004/005/006/007 реализованы, DB-002/003/008 —
в App F-срезах), контракты закрыты внутренне в `ADR-APPF-001`.

Технические пакеты **BA-I18N-002** и **BA-STAGE-1.2-E2E** выполнены и не
требуют решения владельца: языковой реестр переживает отказ Redis,
`language_url` не отдаёт 500 при недоступном реестре, широкие
`except Exception` в i18n-middleware/root убраны; browser/E2E проверяет
шесть языков, root redirect, 404, переключатель, 360px и healthz.
R-006/R-007 закрыты regression-тестами; R-003/R-004/R-005 остаются.
BA-STAGE-1.2-E2E зафиксирован как **IMPLEMENTED / AWAITING INDEPENDENT
REVIEW**, а не как приёмка.

**BA-STAGE-2.1** (регистрация, вход и профиль по §2.10) реализован в dev:
модели/миграция аккаунтов, регистрация, вход/выход, подтверждение email,
нейтральное восстановление пароля, смена пароля с инвалидацией сессий,
профиль/настройки, экспорт JSON, запрос удаления с окном 7 дней и Celery-
анонимизация, Argon2id, HIBP-hook и rate limits. Пакет имеет статус
**PARTIAL**, а не Done: отсутствуют утверждённые юридические тексты/версии,
история игр и личные рекорды (модели GameResult/leaderboards ещё не
реализованы; есть только GameSession из APPF-SESSION-001), обработка bounce и полный cleanup игровых данных; анонимная
идентичность подготовлена сервисом, но не подключена к запросам, требующим
субъекта. 2FA персонала в этот пакет не входила.

**BA-STAGE-2.2** (2FA персонала) реализован в dev как **PARTIAL**:
TOTP-секрет, обязательный enrollment для staff, двухшаговый вход,
recovery-коды (10, hash, single-use), защита от replay, отключение через
password+TOTP, инвалидация прочих сессий, уведомление на verified email и
middleware, не пропускающий staff-сессию без подтверждённой 2FA. Owner
recovery и `LoginEvent` добавлены в 2.4; остаются роли/CRM step-up,
уведомления о смене ролей и browser E2E staff-сценариев.

**BA-STAGE-2.3** (browser E2E аккаунтов) — **IMPLEMENTED / AWAITING
INDEPENDENT REVIEW**: 2 E2E-сценария (регистрация → профиль → export →
logout/login → смена пароля → login с новым паролем → deletion request/
cancel; отказ формы без согласия) прошли на dev-стеке. Полный E2E-набор —
13 passed (11 shell + 2 account). Это не приёмка §2.10/2FA: legal texts,
game history/records, bounce/provider и роли/CRM step-up остаются.

**BA-STAGE-2.4** (2FA completion) — **PARTIAL**: добавлены офлайн-код
владельца (только superuser, одноразовый, после использования требует
повторного enrollment), `LoginEvent` без plaintext login/IP, regeneration
recovery-кодов через password+TOTP, события enable/disable/recovery.
Остаются роли и CRM step-up (CRM — stub), уведомления о смене ролей и
шифрование TOTP-секрета; retention закрыт в 2.5.

**BA-STAGE-2.5** (retention cleanup) — **PARTIAL**: Celery Beat
`accounts.cleanup_expired_account_records` удаляет истёкшие
`AnonymousIdentity`/`AccountToken`, `LoginEvent` старше 365 дней и
`NicknameReservation` с истёкшим сроком; reservation теперь использует
`NICKNAME_RESERVATION_DAYS=730`. Не покрыты `SecurityEvent` (App F),
`GameStorage`/`GameSession`, mail-логи, бэкапы и согласия — их модели/
владельцы сроков ещё не реализованы.

**BA-QUALITY-001** (coverage) — добавлен `make coverage`, конфигурация
`coverage.run/report` с порогом 70 % и `fail_under=70`; фактический общий
coverage — **81.65 %** (2594 statements, 476 missed) при 177 passed,
2 skipped. Низкие модули: `hibp.py` 39 %, `health.py` 59 %, `ba_i18n.py`
63 %, `coverage.py` 36 %, `theme/views.py` 40 %, `storage.py` 0 %;
порог по совокупности выполнен, но это не независимая проверка и не
закрывает пробелы по отдельным модулям.

**BA-CATALOG-001** (публичный каталог) — **PARTIAL**: список только
`published`, фильтры по основному жанру/мобильной поддержке/длительности,
поиск по локализованным названию/описанию (минимум 2 символа), сортировка
new/old, локализованный detail с fallback `en`, genre page и HTMX partial.
Не реализованы: дополнительные жанры и теги (в моделях нет M2M), FTS/
`pg_trgm`-ранжирование, рейтинг/популярность/число голосов (нет моделей
ratings/leaderboards), бейдж покрытия локализации, play-кнопка (App F).
5 integration tests.

**BA-CATALOG-002** (жанры/теги) — **IMPLEMENTED / AWAITING INDEPENDENT
REVIEW**: добавлены additive-модели `GameGenre`/`GameTag` (M2M через
таблицы), фильтры по дополнительному жанру и тегам, tag options в форме,
миграция `catalog.0003` применена; 6 integration tests. FTS/`pg_trgm`,
ratings/popularity и play остаются вне пакета.

**BA-CATALOG-003** (FTS/`pg_trgm`) — **PARTIAL**: поиск использует
`SearchVector`/`SearchQuery` с конфигурацией языка (или `simple`),
`TrigramSimilarity` и прежний `icontains` fallback; 7 integration tests.
Вектор вычисляется в запросе, `GameTranslation.search_vector` не
заполняется, отдельного GIN-индекса для выражения нет, `unaccent` в
запросе не применяется — производительность/ранжирование не нормативные.

**BA-CATALOG-004** (persisted vector) — **PARTIAL**: `GameTranslation`
обновляет `search_vector` через post_save (simple, weights A/B/C);
добавлена data-migration `catalog.0004` для backfill существующих строк;
поиск использует stored vector + GIN, query-time FTS/trigram остаётся
fallback. Не реализованы `unaccent`, `SearchRank`-ранжирование, обновление
при bulk/import и проверка плана запроса на объёме.

**BA-CATALOG-005** (unaccent/ranking/bulk) — **IMPLEMENTED / AWAITING
INDEPENDENT REVIEW**: `unaccent()` применяется в persisted vector и
запросе; `SearchRank` задаёт порядок при поиске; Celery Beat
`catalog.refresh_catalog_search_vectors` пересчитывает vector после
bulk/import; backfill-миграция `catalog.0005`; 8 integration tests. План
запроса на объёме и ratings/popularity/play остаются.

## 1.1. AI infrastructure — BA-AUTONOMY-003

**BA-AUTONOMY-003** — **IMPLEMENTED / AWAITING OWNER ACCEPTANCE**.
Основная сессия остаётся Flash; Pro (`architect`, `code-reviewer`,
`security-auditor`) работает в text-only режиме: Flash передаёт бриф,
Pro возвращает план/вердикт без tool-вызовов. Причина — реальный Pro
вызов маршрутизируется, но tool-использование ненадёжно (`leading-only`).
`ANTHROPIC_DEFAULT_OPUS_MODEL` изменён на `deepseek-v4-pro` (backup
`~/.bashrc`); Sonnet/Haiku/subagent default — Flash. Добавлены
`ba-plan`, `bash_guard.py`, guard для `ai-dev`, `NOW.md`; исправлены
указатели `docs/spec` → `technical_specification/`. Текущий полный suite —
185 passed, 2 skipped, coverage 82,34 %; реестровые 81,65 %/177 —
исторический срез BA-QUALITY-001. Детали —
`docs/foundation/BA-AUTONOMY-003_REPORT.md`.

## 1.2. App F: серверный session/ticket срез — APPF-SESSION-001

**APPF-SESSION-001** — **ACCEPTED владельцем 2026-11-20** (OD-STATUS-007);
независимый text-only review `code-reviewer` и `security-auditor`
(deepseek-v4-pro) — **accept**; evidence —
`docs/audits/APPF-SESSION-001_REVIEW_EVIDENCE.md`.

Реализованы `GameSession`, одноразовый launch ticket, активация и heartbeat
по §2.12.1–2.12.4: `POST /api/v1/sessions` (201
`{session_id, ticket, expires_at}`), `/activate` (200 `{context}`),
`/heartbeat` (204). CSRF обязателен и для анонимных; throttle scopes
`sessions`/`heartbeat` с ключом по живой guest-identity (IP — fallback);
лимит «≤3 активных на (субъект, игра)» под advisory-lock и при создании, и
при активации. Subject хранится как `(subject_type, subject_id)` без FK —
временное техническое решение до DB-001. 24 integration tests (включая
3 конкурентных сценария); полный suite — 209 passed, 2 skipped. Детали —
`docs/foundation/APPF-SESSION-001_REPORT.md`.

Найден и закрыт скрытый дефект: свежая БД не мигрировала
(`catalog.0001` citext без зависимости от `core.0001_extensions`); добавлена
только graph-зависимость, schema не менялась. Это осознанное исключение из
правила «применённые миграции не редактировать».

## 1.3. App F: throttle hardening — APPF-SESSION-002

**APPF-SESSION-002** — **IMPLEMENTED / AWAITING OWNER ACCEPTANCE**;
блокеры review сняты. Лимиты приведены к Приложению E: создание сессий
30/час субъект + 600/час IP (/64), heartbeat 3/мин на сессию, structured 429,
отдельный `redis-throttle` (noeviction), `ClientIPMiddleware` для реального
IP из nginx. 37 session tests; отчёт —
`docs/foundation/APPF-SESSION-002_REPORT.md`.

## 1.4. App F: результат и рекорды — APPF-RESULT-001

**APPF-RESULT-001** — **IMPLEMENTED / AWAITING OWNER ACCEPTANCE**;
`POST /api/v1/sessions/{id}/result` с `Idempotency-Key`, `GameResult` +
`LeaderboardEntry`, DB-001/002/003 (CHECK субъекта, триггеры консистентности),
гость 403 без записи, 100-параллельный тест. 19 tests; отчёт —
`docs/foundation/APPF-RESULT-001_REPORT.md`.

## 1.5. App F: публичный leaderboard — APPF-LEADERBOARD-001

**APPF-LEADERBOARD-001** — **IMPLEMENTED / AWAITING OWNER ACCEPTANCE**;
`GET /api/v1/games/{id}/leaderboard?limit=10|100` и `/me/best`, порядок
direction → achieved_at → user_id, строка `me`, только published-игры,
read-throttle 120/min. Review accept; 7 tests; отчёт —
`docs/foundation/APPF-LEADERBOARD-001_REPORT.md`.

## 1.6. App F: хранилище игры — APPF-STORAGE-001

**APPF-STORAGE-001** — **IMPLEMENTED / AWAITING OWNER ACCEPTANCE**;
`GET/PUT /api/v1/games/{id}/storage`, 64 КиБ, revision/If-Match, TTL гостя
90 дней, активная сессия обязательна, DB-008 trigger `pg_column_size`.
12 tests (включая гонку create); review — accept; отчёт —
`docs/foundation/APPF-STORAGE-001_REPORT.md`.

## 1.7. App F: игровое время — APPF-PLAYTIME-001

**APPF-PLAYTIME-001** — **IMPLEMENTED / AWAITING OWNER ACCEPTANCE**;
`UserGamePlaytime`, зачёт приращения credited_ms только для `mode=user`
(гости/preview/autotest исключены), удаление при анонимизации; review
accept; 40 session tests; отчёт —
`docs/foundation/APPF-PLAYTIME-001_REPORT.md`.

## 1.8. App F: оценки игр — APPF-RATINGS-001

**APPF-RATINGS-001** — **IMPLEMENTED / AWAITING OWNER ACCEPTANCE**;
оценки 1–5 после порога playtime, возраст 1 ч, 1/24 ч и 5/30 дней,
20/сутки, транзакционный агрегат под advisory-lock, публичный summary;
review accept; 10 tests; антифрод §2.9.6 (IP/журнал) — owner-gap; отчёт —
`docs/foundation/APPF-RATINGS-001_REPORT.md`.

## 1.9. App F: популярность и close — APPF-POPULARITY-001

**APPF-POPULARITY-001** — **IMPLEMENTED / AWAITING OWNER ACCEPTANCE**;
`GamePlayCredit`/`GameDailyStats`, зачёт при завершении сессии (≥15 с,
mode user/guest, окно 30 мин), `POST /sessions/{id}/close`; review accept;
8 tests; R-032 (guest identity inflation) — owner-gap; отчёт —
`docs/foundation/APPF-POPULARITY-001_REPORT.md`.

## 1.10. ZIP pipeline: безопасный preflight — BA-ZIP-PREFLIGHT-001

**BA-ZIP-PREFLIGHT-001** — **TECHNICALLY ACCEPTED** (agent, OD-TECH-001);
продуктовая приёмка — владелец.
Metadata-only проверка игрового ZIP без распаковки и исполнения:
`apps/pipeline/validation/codes.py` (стабильные коды/severity/лимиты) и
`structure.py` (`preflight_zip`). Проверяются лимиты (25/100/20 МБ,
2000 файлов, 100:1), абсолютные пути/`..`/backslash, NFKC, symlink/
спецфайлы/шифрование, подмена размеров local vs central, дубликаты и
регистро-коллизии, Windows-reserved, allowlist расширений и служебные
файлы; возвращаются SHA-256 и структурированные diagnostics для CRM.
16 unit tests; full suite — 297 passed, 2 skipped; ruff/mypy зелёные;
code-reviewer — accept; security-auditor — **accept** после устранения
M-1/M-2 (остаток O-1…O-5/m-4…m-7 — R-034). Срез не зависит от
BA-SDK-1.1/BA-ENV-1.1/BA-GAME-2.2; изолированная распаковка —
следующий пакет BA-ZIP-EXTRACT-001. R-033 фиксирует границу metadata-only.
Отчёт — `docs/foundation/BA-ZIP-PREFLIGHT-001_REPORT.md`.

## 1.11. ZIP pipeline: безопасная распаковка — BA-ZIP-EXTRACT-001

**BA-ZIP-EXTRACT-001** — **TECHNICALLY ACCEPTED** (agent, OD-TECH-001);
продуктовая приёмка — владелец.
`apps/pipeline/services/unpack.py`: повторный preflight, потоковая
распаковка чанками 64 КиБ, независимый счётчик фактических байт, лимиты
20 МБ/файл и 100 МБ/итог, CRC, канонические пути, запрет file-vs-dir и
prefix-конфликтов, `O_EXCL|O_NOFOLLOW`, атомарный rename, очистка staging.
11 unit tests; full suite — 308 passed, 2 skipped; ruff/mypy зелёные.
CPU/RAM/time/disk/network-изоляция worker — отдельный срез
BA-ZIP-WORKER-001; сервис даёт byte caps и cooperative deadline.
Отчёт — `docs/foundation/BA-ZIP-EXTRACT-001_REPORT.md`.

## 1.12. ZIP pipeline: изолированный extraction worker — BA-ZIP-WORKER-001

**BA-ZIP-WORKER-001** — **TECHNICALLY ACCEPTED** (agent, OD-TECH-001);
продуктовая приёмка — владелец.
Отдельный Compose-сервис `zip-worker` (prefork, очередь `zip`): сеть
`zipnet` только с `redis-broker`; `read_only` rootfs, `cap_drop: ALL`,
`no-new-privileges`, pids 64, mem 512m, cpus 1.0, tmpfs `/tmp` 64m;
`zip_uploads` ro / `zip_artifacts` rw; source через
`O_NOFOLLOW|O_NONBLOCK` + `fstat` + `/proc/self/fd`; per-job flock;
statvfs reserve; ATTEMPTS/quarantine; `cancel_check`; JSON-аудит; cleanup.
22 новых теста; full suite — 330 passed, 2 skipped; ruff/mypy зелёные;
code/security review — **accept**; остатки R-033/R-035/R-036/R-037.
Отчёт — `docs/foundation/BA-ZIP-WORKER-001_REPORT.md`.

## 1.13. BA Dev Control — Telegram-пульт автономной разработки

**BA-DEVCONTROL-001** — **TECHNICALLY ACCEPTED** (agent, 2026-11-21);
live setup — токен владельца и opt-in `--enable-autonomous`. Sandbox
test runner реализован; автономный `/continue` по умолчанию выключен.
Отдельный stdlib-сервис `devcontrol/` (не Django): long polling, owner-only
авторизация, `/status` `/report` `/progress` `/next` `/tasks` `/continue`
`/pause` `/resume` `/stop` `/logs` `/ask`, inline-кнопки. Управляет одной
фоновой сессией через поддерживаемые `claude --bg` / `agents --json` /
`logs` / `stop`; state/events/inbox в `~/.local/state/ba-devcontrol` (0700,
0600, atomic, flock); токен — `creds/telegram.env` (0600, вне Git).
Узкий permissions + `denyInsteadOfPrompting`, без bypass/auto; hooks
Stop/PermissionRequest/SessionEnd. 31 tests; full 360/3 skipped; live probe
`--bg` + Stop hook. Нужны токен владельца и live Telegram-проверка; первый
автономный запуск может требовать одобрения permission-конфигурации.
Отчёт — `docs/foundation/BA-DEVCONTROL-001_REPORT.md`.

## 1.14. ZIP hardening — BA-ZIP-HARDENING-001 (R-035)

**BA-ZIP-HARDENING-001** — **TECHNICALLY ACCEPTED** (agent, 2026-11-21);
code/security review — **ACCEPT**. Закрывает
остаток R-035: method allowlist (stored/deflate), fsync каждого файла и
staging/destination каталогов перед atomic rename, fsync COMPLETED/ATTEMPTS
и audit, раздельные коды read (`X_ARCHIVE_BAD`) / write (`X_IO`). 4 новых
теста; full suite — 369 passed, 3 skipped; benchmark 2000 files — 7.7 с.
Остаток: directory fsync best-effort. Отчёт —
`docs/foundation/BA-ZIP-HARDENING-001_REPORT.md`.

## 1.15. Качество поиска и покрытие — BA-QUALITY-002

**BA-QUALITY-002** — **TECHNICALLY ACCEPTED** (agent, 2026-11-21);
code/security review — **ACCEPT**. Dev-only benchmark
`catalog_benchmark` подтвердил существующий GIN на persisted
`search_vector` (10k: Bitmap Index Scan ~2.4 мс для FTS). Кандидатные
trigram/unaccent GIN не выбраны/невозможны (`unaccent` STABLE), новый
индекс не добавлен. Full OR остаётся Seq Scan (~150 мс на 10k) — residual.
Покрытие: **90.88 %, ни одного модуля <70 %**; 397 passed, 3 skipped.
Отчёт — `docs/foundation/BA-QUALITY-002_REPORT.md`.

## 1.16. R-036 Phase 1 — delivery observability (non-behavioral)

**R-036 Phase 1** — **TECHNICALLY ACCEPTED** (agent, 2026-11-21);
code-reviewer/security-auditor — **ACCEPT**. Добавлены структурированные
события `celery.task.received/failure/retry` и worker
shutdown/process_shutdown; только безопасные поля (task id/name, queue,
redelivered, retries, exception type, worker/pid/exitcode), без args/
kwargs/результата/текста исключения. R-036-контракт зафиксирован в
docstrings и 5 contract tests. Живая проверка worker выявила и исправила
`Consumer.name`-объект и потерю handler после `dictConfig` (fd-2 JSON
handler). Full — **402 passed, 3 skipped**; ruff/format/mypy clean.
Поведение доставки (`acks_late`, `reject_on_worker_lost`,
`acks_on_failure_or_timeout`, `visibility_timeout`) не изменялось.
Phase 2 — **AWAITING OWNER DECISION**; отчёт —
`docs/foundation/R-036_PHASE1_REPORT.md`.

## 1.17. App F / DB-001 — tombstone-анонимизация сессий при удалении

**BA-APPF-002 / DB-001** (approved OD-DB-001; owner chose tombstone) —
**TECHNICALLY ACCEPTED** (agent, 2026-11-21); first review found finished-
session UUID + race; re-review after fix — **ACCEPT**. `GameSession` получает
`SUBJECT_DELETED`; migration `gameplay.0011`; `anonymize_user` блокирует все
сессии пользователя, ставит `subject_type=deleted` + случайный per-session
UUID, created/active закрывает и очищает ticket/binding; finished/expired
состояния сохраняются. Full — **403 passed, 3 skipped**; ruff/format/mypy
clean; migration applied/check clean. Остаток — retention APPF-OD-030.
Отчёт — `docs/foundation/BA-APPF-002_DB001_SESSION_CLEANUP_REPORT.md`.

## 1.18. App F / DB-006 — immutable GameVersion

**BA-APPF-002 / DB-006** (approved OD-DB-006) — **TECHNICALLY ACCEPTED**
(agent; code/security review — **ACCEPT**). `GameVersion` content/hash/version
защищены model `save()` guard и PostgreSQL trigger; `created_by`/
`manual_review_by` только unchanged/→NULL, поэтому `ON DELETE SET NULL` не
ломает каталог. Migrations `catalog.0006`/`0007`; 16 tests; full
**419 passed, 3 skipped**; ruff/format/mypy clean; migration checks clean.
Остатки: 0006/0007 intermediate, strict `manual_review_at`,
`GameVersion.game` CASCADE/DB-004 вне scope. Отчёт —
`docs/foundation/BA-APPF-002_DB006_REPORT.md`.

## 1.19. App F / DB-005 + DB-007 — public name и mode↔subject

**BA-APPF-002 / DB-005** — `GameTranslation.name` ограничен 60 символами
(migration `catalog.0008`); длинное manifest name — будущий импортёр.
**DB-007** — `GameSession` CHECK `ck_gameplay_session_mode_subject`:
user→user, guest→anon, preview→user/anon, autotest→user; `deleted` tombstone
разрешён для любого mode. Migration `gameplay.0012` (финальная, сразу с
deleted exception). 14 targeted tests; full **433 passed, 3 skipped**;
ruff/format/mypy clean; migration checks clean. Существующие
агрегаты уже исключают preview/autotest (`is_test`, popularity только
user/guest, playtime только user). Остатки: tombstone-сессии в старых
popularity-кредитах и возможная смена mode через UPDATE — отдельные
DB-001/mode-immutability срезы; DB-005 precheck не усекает данные. Отчёт —
`docs/foundation/BA-APPF-002_DB005_DB007_REPORT.md`.

## 1.20. App F / DB-004 + DB-001/DB-007 residuals

**DB-004** — `Game.technical_id`/`host_label` immutable после первой
публикации; DELETE `Game` запрещён trigger. Model `save()` + migrations
`catalog.0009`/`0010` (case-sensitive identity guard); DB-008 storage trigger
verified direct test. **DB-001 residual** — при удалении аккаунта
удаляются `GamePlayCredit` пользователя; `GameDailyStats` остаётся
историческим агрегатом. **DB-007 residual** — `GameSession.mode` immutable:
model guard + migration `gameplay.0013`; DB-001 tombstone не меняет mode.
Full **441 passed, 3 skipped**; ruff/format/mypy clean; migration checks
clean. Отчёт — `docs/foundation/BA-APPF-002_DB004_RESIDUALS_REPORT.md`.

## 1.21. App F runtime, SDK и player — срез A+B

**IMPLEMENTED / TECHNICAL REVIEW** (контракт BA-SDK-1.1 v1.1.0 submitted,
не approved). Реализованы `sdk/1.1.0/ba-sdk.js`, host-протокол, player host,
`game_play` с серверным create+activate (ticket не рендерится), no-store,
точный runtime origin, full `runtime_hash`, CSRF relay, guest normalization.
`play.html` использует iframe sandbox; `game_detail` получил Play/Leaderboard links; добавлен heuristic verifier baseline (points/sec, idle gap, event schema, quarantine, heuristic trust).
Full **456 passed, 4 skipped**; JS `node --check` clean. Независимый review —
**INCOMPLETE** (E2E/probe passed; pin `BA_PORTAL_ORIGIN` добавлен, но diff-evidence/JSON-Schema и parentOrigin — residual). Отчёт — `docs/foundation/BA-APPF-002_RUNTIME_SDK_REPORT.md`.

## 2. Статусы работ

| Работа | Статус | Что означает |
|---|---|---|
| Documentation Block 1 (BA-DOC-001 + FIX-01/02/03) | **ACCEPTED** | Документация принята владельцем; техническая приёмка не следует |
| BA-FIX-003 | **ACCEPTED** с некритичными замечаниями | AUD3-001/AUD3-002 закрыты в BA-I18N-002; AUD3-003/005 остаются |
| BA-FIX-001 | **NOT_ACCEPTED** / открыта | Часть A-001/A-003 исправлена; формального закрытия владельцем нет |
| BA-FIX-002 | **PARTIAL** | Первоначальное исправление R-002; не является окончательным устранением |
| BA-I18N-002 | **COMPLETED**; не принят | R-006/R-007 закрыты; 147 tests; R-003/R-004/R-005 остаются |
| BA-STAGE-1.2-E2E | **IMPLEMENTED / AWAITING INDEPENDENT REVIEW** | 11 browser/E2E passed на dev-стеке; CI/обычный suite по умолчанию skip; не приёмка |
| BA-STAGE-2.1 | **PARTIAL**; core §2.10 реализован, не принят | 17 account integration + 4 service tests; blockers: legal texts/versions, game history/records models, bounce, anonymous request wiring |
| BA-STAGE-2.2 | **PARTIAL**; TOTP 2FA персонала реализована, не принята | 9 2FA integration tests суммарно с 2.4; остаются roles/CRM step-up, encryption, E2E staff |
| BA-STAGE-2.3 | **IMPLEMENTED / AWAITING INDEPENDENT REVIEW** | 2 account E2E + 11 shell E2E passed на dev-стеке; не приёмка |
| BA-STAGE-2.4 | **PARTIAL**; owner recovery, LoginEvent, regeneration реализованы | 9 2FA integration tests; roles/CRM step-up остаются |
| BA-STAGE-2.5 | **PARTIAL**; account retention cleanup реализован | 1 retention test; SecurityEvent/GameStorage/mail/backup/consent сроки не покрыты |
| BA-QUALITY-001 | **IMPLEMENTED / AWAITING INDEPENDENT REVIEW** | `make coverage`; 81.65 % при пороге 70 %; низкие модули перечислены |
| BA-CATALOG-001 | **IMPLEMENTED / TECHNICAL REVIEW**; публичный list/detail/genre/filters/search/FTS/tags/ratings/popularity/pagination/SEO | Product acceptance pending; missing rating vote UI and TOP-100 leaderboard pagination; audit — `BA_PRODUCT_ROADMAP_AUDIT.md` |
| BA-CATALOG-002 | **IMPLEMENTED / AWAITING INDEPENDENT REVIEW** | M2M `GameGenre`/`GameTag`, фильтры; 6 integration tests; без FTS/ratings/play |
| BA-CATALOG-003 | **PARTIAL**; FTS+trigram+language config | 7 tests; query-time vector |
| BA-CATALOG-004 | **PARTIAL**; persisted vector/GIN/backfill | 7 tests; unaccent/ranking/bulk добавлены в 005 |
| BA-CATALOG-005 | **IMPLEMENTED / AWAITING INDEPENDENT REVIEW** | unaccent, SearchRank, bulk refresh; 8 tests; нет benchmark |
| BA-STAGE-1.1 | **NOT_ACCEPTED** | Ограниченный срез этапа 1; не самостоятельный нормативный этап |
| BA-FOUNDATION-001 | **COMPLETED**; не принят | Отчёт Partial/Blocked; независимая проверка выявила ограничения; этап 0 не закрыт |
| BA-FOUNDATION-002 | **PARTIAL — внутренние контракты приняты (ADR-APPF-001)** | SDK/ENV v1.1.0 внутренне приняты; design-схема/App J остаются; внешние оригиналы/публикация не требуются для внутренней разработки |
| Предыдущий аудит App F | **COMPLETED** | Отчёт существует; вывод: runtime App F отсутствует, проверены только схемы/валидатор |
| BA-APPF-001 | **COMPLETED**; не принят | Подготовлены 45 проектных решений; 29 Blocker, 17 вопросов владельцу |
| BA-APPF-002 | **PARTIAL / IN_PROGRESS** — DB-001/004/005/006/007 и runtime A+B реализованы; контракты закрыты внутренне (ADR-APPF-001); product acceptance открыта | Не приёмка App F |
| APPF-CONTRACT-CLOSURE-001 | **TECHNICALLY ACCEPTED (Architect/internal)** | ADR-APPF-001: BA-GAME A, BA-SDK/ENV, 64 КиБ/unknown/`sessionId`, DB-001…008, trust/EventLog/storage/leaderboard, retention, roles/2FA/step-up, email adapter, production requirements; внешние действия не выполнялись |
| BA-SDK-1.1 / BA-ENV-1.1 | **INTERNALLY ACCEPTED (Architect)** | v1.1.0 — внутренние контракты; `ba-sdk.js`/JSON Schema и production-конфигурация остаются реализацией/внешним deploy |
| BA-GAME-2.2 | **DECIDED (Architect): A** | A — canonical; B — историческое подмножество; ТЗ не изменялось |
| APPF-RETENTION | **DECIDED (technical/internal)** | Сроки Приложения D обязательны; `[PROP]`-сроки — временные внутренние значения; юридическая проверка ПДн/бэкапов остаётся |
| BA-DB-SCHEMA-002 | **PARTIAL — DB-001…008 закрыты на уровне моделей/миграций** | DB-002/003/008 реализованы в App F-срезах; DB-004/005/006/007 — в catalog/gameplay; документационная синхронизация `DB_SCHEMA.md` — остаток |
| BA-PROD-001 | **REQUIREMENTS RECORDED; external actions pending** | Production baseline в ADR D13; домены/TLS/S3/CDN/Sentry/deploy/credentials — внешние действия владельца |
| BA-AUTONOMY-003 | **IMPLEMENTED / AWAITING OWNER ACCEPTANCE** | Pro text-only plan done; guards; NOW; docs pointers; 185 tests; security review **accept**; owner acceptance pending |
| APPF-SESSION-001 | **ACCEPTED** (владелец, 2026-11-20) | GameSession/ticket/activate/heartbeat §2.12.1–2.12.4; 24 tests (3 конкурентных); полный suite 209; code/security review **accept**; evidence в AUDIT_REGISTER |
| APPF-SESSION-002 | **IMPLEMENTED / AWAITING OWNER ACCEPTANCE** | Throttle Прил. E: subject 30/ч + IP 600/ч, heartbeat 3/мин, redis-throttle, реальный IP; блокеры review сняты |
| APPF-RESULT-001 | **IMPLEMENTED / AWAITING OWNER ACCEPTANCE** | Result API + GameResult + LeaderboardEntry; DB-001/002/003; 19 tests; review |
| APPF-LEADERBOARD-001 | **IMPLEMENTED / AWAITING OWNER ACCEPTANCE** | Публичный leaderboard + me/best; 7 tests; review accept |
| APPF-STORAGE-001 | **IMPLEMENTED / AWAITING OWNER ACCEPTANCE** | Storage 64 КиБ/revision/TTL; 12 tests; review accept |
| APPF-PLAYTIME-001 | **IMPLEMENTED / AWAITING OWNER ACCEPTANCE** | UserGamePlaytime mode=user; 40 session tests; review accept |
| APPF-RATINGS-001 | **IMPLEMENTED / AWAITING OWNER ACCEPTANCE** | Оценки/порог/лимиты/агрегат; 10 tests; review accept; антифрод owner-gap |
| APPF-POPULARITY-001 | **IMPLEMENTED / AWAITING OWNER ACCEPTANCE** | Play credit/daily stats/close; 8 tests; review accept; R-032 owner-gap |
| BA-ZIP-PREFLIGHT-001 | **TECHNICALLY ACCEPTED** (agent); product — owner | Metadata-only ZIP preflight; 16 tests; full 297/2 skipped; review accept; R-033 extraction sandbox — следующий пакет |
| BA-ZIP-EXTRACT-001 | **TECHNICALLY ACCEPTED** (agent); product — owner | Streaming safe extraction; 11 tests; full 308/2 skipped; security review accept; worker isolation — BA-ZIP-WORKER-001 |
| BA-ZIP-WORKER-001 | **TECHNICALLY ACCEPTED** (agent); product — owner | Отдельный `zip-worker` (`zipnet`, prefork, read_only, limits, cancel, audit); 22 new tests; full 330/2 skipped; code/security review accept; R-033/R-035/R-036/R-037 |
| BA-ZIP-HARDENING-001 (R-035) | **TECHNICALLY ACCEPTED** (agent); product — owner | fsync files/dirs, stored/deflate local+central, read/write codes; 54 ZIP tests; full 369/3; 2000 files 7.7s; review accept |
| BA-QUALITY-002 | **TECHNICALLY ACCEPTED** (agent); product — owner | GIN search_vector подтверждён; trigram/unaccent не обоснован; coverage 90.88 %; 397/3; review accept |
| R-036 Phase 1 | **TECHNICALLY ACCEPTED** (agent); Phase 2 — owner | Delivery observability/docstrings/contract tests; 402/3; code/security review accept; delivery behavior unchanged; Phase 2 awaiting owner |
| BA-APPF-002 / DB-001 | **TECHNICALLY ACCEPTED** (agent) | Tombstone all user sessions on deletion; open aborted + ticket/binding cleared; finished/expired history kept; 403/3; review accept; migration 0011 |
| BA-APPF-002 / DB-006 | **TECHNICALLY ACCEPTED** (agent) | GameVersion content immutable via model guard + DB trigger; audit FKs only →NULL; 419/3; code/security review accept; migrations 0006/0007 |
| BA-APPF-002 / DB-005/007 | **TECHNICALLY ACCEPTED** (agent) | Public name 60; mode↔subject CHECK incl. deleted tombstone; 433/3; migrations 0008/0012 |
| BA-APPF-002 / DB-004 + residuals | **TECHNICALLY ACCEPTED** (agent) | Game identity/delete guard; GamePlayCredit cleanup; mode immutable; 441/3; migrations 0009/0010/0013 |
| BA-APPF-002 / runtime A+B | **IMPLEMENTED / TECHNICAL REVIEW** | SDK, host protocol, player host, play view, leaderboard page, heuristic verifier; 456/4; runtime E2E 2 passed; JS host tests 4 passed; review incomplete |
| BA-DEVCONTROL-001 | **TECHNICALLY ACCEPTED** (agent); live setup — token/opt-in | Мониторинг/отчёты/задачи/ask/hooks; sandbox test runner; 31 tests; full 360/3; code/security review accept; Telegram API blocked — нужен proxy/VPN + токен |
| BA-DOC-002 | **COMPLETED**; не принят | Актуализация шести реестров; ожидает проверки владельцем |

Статусы `COMPLETED`, `ACCEPTED`, `PARTIAL` и `NOT_ACCEPTED` не
взаимозаменяемы: завершение работы, техническая готовность и приёмка — разные
события.

## 3. Что фактически готово

- core: UUIDv7/citext, middleware/CSP, JSON-логи, healthz/readyz, storage.
- accounts: `User` + Argon2id, `UserProfile`, `EmailAddress`,
  `NicknameHistory`/`NicknameReservation`, `AccountToken`,
  `AnonymousIdentity`, `UserLegalAcceptance`; регистрация/вход/выход,
  email verification, password reset, профиль, смена пароля, экспорт,
  deletion request/cancel, Celery-анонимизация; BA-STAGE-2.1 — **PARTIAL**.
- 2FA персонала: TOTP, обязательный enrollment, recovery-коды, replay-
  protection, disable через password+TOTP, staff-middleware, owner offline
  code, `LoginEvent` и regeneration; BA-STAGE-2.2/2.4 — **PARTIAL** из-за
  отсутствующих ролей/CRM step-up.
- Retention: Celery cleanup для гостей, токенов, `LoginEvent` и nickname-
  резервов; BA-STAGE-2.5 — **PARTIAL** (глобальные сроки §2.22 не все).
- Coverage: `make coverage`, порог 70 %, фактически 81.65 %; CI-команда
  `pytest --cov=apps` читает конфигурацию; BA-QUALITY-001 — implemented.
- Catalog: published-only list, primary genre/mobile/duration filters,
  localized search (min 2), new/old sort, detail fallback `en`, genre page
  и HTMX partial; BA-CATALOG-001 — **PARTIAL**. Дополнительные жанры и
  теги (M2M), фильтры — BA-CATALOG-002; FTS+trigram — BA-CATALOG-003;
  persisted `search_vector`/GIN — BA-CATALOG-004; `unaccent`/ranking/bulk —
  BA-CATALOG-005.
- ZIP preflight: metadata-only структура/пути/типы/лимиты/коллизии/
  расширения, SHA-256, diagnostics; без распаковки; BA-ZIP-PREFLIGHT-001 —
  **IMPLEMENTED / AWAITING OWNER ACCEPTANCE**. Safe extraction —
  BA-ZIP-EXTRACT-001; изолированный `zip-worker` — BA-ZIP-WORKER-001;
  обе работы ожидают приёмки владельцем.
- Browser E2E: регистрация/вход/смена пароля/deletion window; полный набор
  13 E2E passed; BA-STAGE-2.3 — **IMPLEMENTED / AWAITING INDEPENDENT REVIEW**.
- Публичная i18n-оболочка и языковая маршрутизация BA-STAGE-1.1
  реализованы, но этап не принят.
- catalog: модели/миграции; публичные detail/play/leaderboard — JSON-заглушки.
- i18n: шесть языков, словари, middleware, тесты; BA-I18N-002 добавил
  устойчивый языковой реестр и regression-тесты R-006/R-007; R-002 имеет
  ограниченную доказательную базу, R-003/R-004/R-005 остаются.
- theme: токены → CSS; CRM: backup/restore-check; dev-lite и staging nginx.
- BA-FOUNDATION-002: DRAFT SDK/ENV, message schemas, semantic validator,
  SQL/ERD design, App J mapping; это **не** работающая App F.

## 4. Что не готово

- Skeleton, не функциональность: пустые `apps/analytics`, `apps/content`,
  `apps/moderation` и часть пустых service/template/API-файлов в других
  приложениях — заготовки структуры, а не реализованные модули. Не считать
  их наличие признаком готовности; удалять/заполнять — только по решению
  задачи, не выдавать пустые файлы за stub-реализацию.
- App F runtime: серверные срезы session/ticket, result, leaderboard,
  storage, playtime, ratings и popularity реализованы (частично принят
  только SESSION-001); `sdk/1.1.0/ba-sdk.js`,
  `static/src/js/host_protocol.js` и `static/src/js/player.js` реализованы
  как runtime A+B, но остаются **IMPLEMENTED / TECHNICAL REVIEW**, не
  продуктовая приёмка.
- BA-SDK-1.1/BA-ENV-1.1 v1.1.0 **внутренне приняты Architect** (ADR-APPF-001);
  внешние оригиналы/публикация не требуются для внутренней разработки, но
  JSON Schema/`ba-sdk.js`-актуализация, production-конфигурация и внешние
  действия остаются.
- App F client/runtime: runtime A+B реализует postMessage, origin/source,
  sessionId/requestId, SDK injection и play view, но остаётся
  **IMPLEMENTED / TECHNICAL REVIEW**. Полный EventLog/verifier/replay и
  сквозная продуктовая приёмка не завершены; наличие серверных API само по
  себе не является сквозной системой.
- ZIP pipeline: preflight и потоковая safe-extraction реализованы; OS-level
  sandbox worker, manifest/catalog/locales, SDK injection, runtime bundle и
  публикация — не реализованы.
- Аккаунты §2.10: утверждённые тексты/версии Terms и Privacy, страницы
  `/legal/terms/` и `/legal/privacy/`; история игр, личные рекорды и места;
  обработка bounce/недоставляемых адресов; сквозная проверка удаления
  аккаунта для `GameResult`/`LeaderboardEntry`/`GameRatingVote`/
  `GameStorage`/`UserGamePlaytime` (модели реализованы в App F-срезах);
  подключение `AnonymousIdentity` к первому
  запросу, требующему субъекта; 2FA персонала: офлайн-код восстановления
  владельца, отдельный журнал входов/SecurityEvent, уведомления о смене
  ролей и CRM step-up.
- Каталог: рейтинг/популярность/голоса, бейдж покрытия, публичный play
  runtime, benchmark/план запроса на объёме. Persisted vector/GIN,
  unaccent/ranking/bulk и M2M жанров/тегов есть.
- `/api/v1/` реализован для sessions/activate/heartbeat/result,
  leaderboard/me-best, storage, ratings и close; reports, locales и
  остальные endpoints отсутствуют. Полноценные CRM/2FA/роли, модерация,
  аналитика, ZIP pipeline (кроме preflight), production compose/Nginx/
  monitoring/WAL/PITR/S3 не готовы.
- SQL design частично реализован в Django-моделях/миграциях App F-срезов;
  DB-001/002/003/008 закрыты в коде, DB-004/005 и сквозная схема — до
  импорта/CRM (см. BA-APPF-001).

## 5. Блокирующие вопросы

После `ADR-APPF-001` внутренние контрактные блокеры сняты. Остались только
внешние и product-acceptance пункты; сводка — `OWNER_DECISIONS.md` D.1.

**Внутренние (решены Architect, ADR-APPF-001):**

1. BA-SDK-1.1/BA-ENV-1.1 v1.1.0 внутренне приняты; `sessionId`/64 КиБ/
   unknown-поля/EventLog/trust/storage/leaderboard закрыты.
2. BA-GAME-2.2: canonical = A; B — историческое подмножество.
3. DB-001…DB-008 закрыты; реализованные constraints не переписываются.
4. Retention: сроки Приложения D обязательны; `[PROP]`-сроки — временные
   внутренние значения до юридической проверки.
5. Роли §2.16, staff TOTP 2FA, recovery, step-up, журнал/уведомления.
6. Email: единый адаптер поверх Django SMTP; dev/staging Mailpit.
7. Production requirements зафиксированы письменно (ADR D13).

**Новые внутренние решения, требующие владельца (2026-11-24):**

- `ARCADE-SCHEDULED-PUBLISH-001` — разрешить минимальную миграцию схемы
  (запись target version для отложенной публикации) либо отклонить задачу.
- `ARCADE-RETENTION-HARDENING-001` — разрешить миграцию индексов под
  retention purge; без неё остаются full-table scans на больших объёмах.
- `ARCADE-RUNTIME-BUILD-SCHEMAS-001` — разрешить изменение Dockerfile
  assets stage (COPY `scripts/`/`schemas/`, python3) либо оставить parity
  test/`check:schemas` как достаточный guard.
- R-054 — решить `expires_at` vs `expiresAt` и нужен ли legacy alias
  `session_id` для внешних клиентов.
- R-055 — подтвердить DRAFT-схемы после tightening (limit enum, maxLength)
  как финальный публичный контракт.
- `ARCADE-ACCOUNTS-E2E-002` / `ARCADE-CRM-E2E-001` — подготовить live
  dev DB/browser stack для E2E либо принять эти сценарии как NOT TESTED.
- R-036 Phase 2 (Celery ack/idempotency/visibility) — решение владельца.

**Внешние (не решены и не выполнялись):**

8. Legal texts/versions Terms/Privacy, DSA/EN 301 549, GDPR-основания и
   согласия — владелец/юрист.
9. Email/S3/CDN/Sentry/платные провайдеры, домены/DNS/TLS, hosting,
   credentials и production deploy — владелец/провайдер.
10. Реальный игровой ZIP, лицензии и приёмка полного пути — игровая
    команда/владелец.
11. Продуктовая приёмка срезов App F/Browser Arcade — владелец.
12. Формальное закрытие этапов 0/1/3 — не решено; внутренняя приёмка
    контрактов его не заменяет.

## 6. Решения, необходимые от владельца

**Делегировано и закрыто Architect (ADR-APPF-001):** BA-SDK-1.1,
BA-ENV-1.1, BA-GAME-2.2, DB-001…DB-008, App F trust/EventLog/storage/
leaderboard, retention, роли/2FA/step-up, email adapter, production
requirements. Эти пункты не требуют отдельного ответа владельца для
внутренней разработки; владелец может пересмотреть их через новый ADR.

**Требует внешнего действия/решения владельца:**

1. Утвердить юридические тексты Terms/Privacy/cookies и их версии для
   `TERMS_VERSION`/`PRIVACY_VERSION`; решить публикацию `/legal/*`, DSA/
   EN 301 549 и GDPR-основания.
2. Выбрать и подключить транзакционного email-провайдера (ЕС), настроить
   SPF/DKIM/DMARC и bounce-webhooks.
3. Определить production-домены/TLS, хостинг, S3/CDN, Sentry, monitoring,
   backup и WAL/PITR; выдать credentials и окно deploy.
4. Принять реальный игровой ZIP и лицензии/права; провести приёмку полного
   пути ZIP→CRM→игра→рекорд→обновление.
5. Провести продуктовую приёмку App F и Browser Arcade.
6. Решить судьбу остаточных R-003/R-004/R-005; AUD3-001/AUD3-002 и
   R-006/R-007 закрыты технически в BA-I18N-002.
7. Принять решения 2026-11-24 из §5: scheduled-publish schema, retention
   indexes, Docker assets stage, R-054 expiresAt/alias, R-055 DRAFT schemas,
   live E2E environment, R-036 Phase 2.
7. Определить, когда формально закрывать этап 0/этап 1.
8. Принять или вернуть BA-DOC-002 и обновлённые реестры.
9. Решить, где хранится канонический экземпляр ТЗ в Git.

## 7. Следующий согласованный шаг

**Не начинать этап 1 целиком и не запускать BA-APPF-002.** BA-STAGE-2.1,
2.2, 2.4 и 2.5 доведены до **PARTIAL**; приёмка §2.10/2FA требует решений
владельца по legal texts и email provider (§6.9–6.10), процесса офлайн-
восстановления (§6.11), а также моделей gameplay/leaderboards для истории и
cleanup. Следующий незаблокированный пакет — `BA-QUALITY-002`
(поисковый benchmark/EXPLAIN на объёме, GIN для unaccent-выражения,
подъём покрытия `hibp/health/storage/theme`); он не требует App F.
Рейтинги/популярность/play и CRM-роли/step-up остаются заблокированы
App F и решениями владельца.
Параллельно владелец проверяет `docs/foundation/BA-APPF-001_DESIGN_DECISIONS.md`
и DRAFT-контракты, принимает решения по §6; только затем — отдельное задание
на SQL-исправления/App F. До этого App F не считать готовым к реализации или
приёмке.

**Сверка 2026-11-22:** этот раздел — историческая запись нормативного плана,
а не текущая карта. Код Browser Arcade/App F уже содержит server slices,
runtime A+B, каталог, SEO/i18n, аккаунты, ZIP preflight/extract/worker и CRM
dashboard. Внутренние контракты закрыты в `ADR-APPF-001`; внешние
юридические/платные/инфраструктурные действия и product acceptance остаются
открытыми. Актуальная дорожная карта и три категории —
`docs/foundation/BA_PRODUCT_ROADMAP_AUDIT.md`.

## 8. Ссылки

- [TASK_HISTORY](../tasks/TASK_HISTORY.md)
- [ADR-APPF-001](../decisions/ADR-APPF-001.md)
- [OWNER_DECISIONS](../decisions/OWNER_DECISIONS.md)
- [AUDIT_REGISTER](../audits/AUDIT_REGISTER.md)
- [RISK_REGISTER](../risks/RISK_REGISTER.md)
- [CONTEXT_RECOVERY](../handoff/CONTEXT_RECOVERY.md)
- BA-FOUNDATION-001: `BA-FOUNDATION-001_REPORT.md` (корень; запрошенный
  `docs/foundation/BA-FOUNDATION-001_REPORT.md` отсутствует).
- BA-FOUNDATION-002: `docs/foundation/BA-FOUNDATION-002_REPORT.md`
  (запрошенный `reports/...` заблокирован guard-хуком).
- App F audit: `docs/foundation/BA-AUDIT-APP-F-REPORT.md`.
- App F prep: `docs/foundation/BA-APPF-001_DESIGN_DECISIONS.md`.
- BA-STAGE-2.1 report: `docs/foundation/BA-STAGE-2.1_REPORT.md`.
- BA-STAGE-2.2 report: `docs/foundation/BA-STAGE-2.2_REPORT.md`.
- BA-STAGE-2.4 report: `docs/foundation/BA-STAGE-2.4_REPORT.md`.
- BA-STAGE-2.5 report: `docs/foundation/BA-STAGE-2.5_REPORT.md`.
- BA-QUALITY-001 report: `docs/foundation/BA-QUALITY-001_REPORT.md`.
- BA-CATALOG-001 report: `docs/foundation/BA-CATALOG-001_REPORT.md`.
- BA-CATALOG-002 report: `docs/foundation/BA-CATALOG-002_REPORT.md`.
- BA-CATALOG-003 report: `docs/foundation/BA-CATALOG-003_REPORT.md`.
- BA-CATALOG-004 report: `docs/foundation/BA-CATALOG-004_REPORT.md`.
- BA-CATALOG-005 report: `docs/foundation/BA-CATALOG-005_REPORT.md`.
- Нормативные ТЗ: `technical_specification/ts_site.txt`,
  `technical_specification/ts_game.txt`.

## 9. Git-снимок APPF-SESSION-001

```text
Branch: main
HEAD: f43ab9d (docs: sync App F git snapshot)
Origin: git@github.com:ElkinVA/breaktime-arcade.git (private, SSH)
App F server slices: 10907fd, 57fda8e, 3214abf, f319e18, 9b704d5
APPF-SESSION-001: product c935237, records 16946f6
Checkpoint: 214af0d, tag checkpoint-2026-11-20-pre-autonomy
Tag: ba-autonomy-003 (предыдущий пакет)
ai-dev HEAD: d09a3f1344bf8d45cc019893213e504174c50b6f
ai-dev tag: ai-dev-autonomy-003
Status: clean
Remote: отсутствует
```

## 10. Ограничения доказательной базы

- Отчёт агента, независимый аудит и приёмка владельцем — разные источники.
- Отдельные первичные отчёты BA-FIX-001/002/003 и BA-AUDIT-002/003 в файлах
  не найдены; сведения в реестрах не выдаются за полный лог.
- BA-FOUNDATION-001: отчёт есть в корне; ограничения независимой проверки
  зафиксированы по постановке BA-DOC-002, отдельный файл независимой
  проверки не найден.
- `reports/BA_AUDIT_20261118_162920.zip` — generated-отчёт, в котором
  BA-FIX-001 обозначен как настройка AI-среды; это не отчёт о i18n-фиксах и
  не доказательство приёмки.
- Тесты BA-FIX-003 в документационных задачах не перезапускались; их
  результаты остаются заявленными исполнителем.
- Этап 0 не закрыт; App F реализован частично (серверные срезы + runtime
  A+B в technical review); BA-APPF-002 запущена частично (DB-001/004/005/
  006/007 реализованы, DB-002/003/008 — в App F-срезах); контракты закрыты
  внутренне в ADR-APPF-001, product acceptance остаётся.
- BA-STAGE-2.1: результаты тестов/lint/mypy/check и HTTP-проверок
  зафиксированы в `docs/foundation/BA-STAGE-2.1_REPORT.md`; это self-check
  исполнителя, не независимый аудит и не приёмка §2.10.
- BA-STAGE-2.2/2.4: 9 2FA integration tests; full suite — 177 passed,
  2 skipped (оба E2E-модуля skip без BA_E2E); отчёты —
  `docs/foundation/BA-STAGE-2.2_REPORT.md` и
  `docs/foundation/BA-STAGE-2.4_REPORT.md`.
- BA-STAGE-2.5: 1 retention test; отчёт —
  `docs/foundation/BA-STAGE-2.5_REPORT.md`.
- BA-QUALITY-001: `make coverage` — 81.65 % при пороге 70 %; отчёт —
  `docs/foundation/BA-QUALITY-001_REPORT.md`.
- BA-CATALOG-001…005: 8 integration tests; full suite — 185 passed,
  2 skipped; отчёты — `docs/foundation/BA-CATALOG-001_REPORT.md` …
  `BA-CATALOG-005_REPORT.md`.


## 1.23. AI Control Plane — bounded hardening package

Five large tasks accepted by independent Pro review: isolated worktree
lifecycle/recovery, hard task/wall/token/API budgets, env/worktree isolation,
Telegram notifier and VPS transfer package. Final gate **720 passed,
11 skipped**; ruff/format/mypy clean. Technical debt: R-040 (no OS sandbox),
live Telegram/VPS start not exercised, worktree QA uses sandbox/targeted checks.
No game/App F features changed. Evidence — `docs/foundation/AI_AUTONOMY_EVIDENCE.md`.


## 1.24. Browser Arcade product cycle after AI HQ commissioning

Two real catalog/rating UI tasks were completed through the autonomous cycle:
`ARCADE-RATING-DETAIL-001` (`63b6137`) and `ARCADE-RATING-LIST-001`
(`3c58dcb`). Auto-next worked: the second was claimed and completed after the
first without an owner command. Full gate **776 passed, 11 skipped**.
AI HQ VPS installation and live Telegram delivery remain owner/network
blockers; see `docs/foundation/AI_HQ_COMMISSIONING_REPORT.md`.


`ARCADE-POPULARITY-001` (`f211161`) completed the next product cycle:
30-day popularity indicator/cache and `sort=popular`. Review accepted with a
minor product-behavior divergence from §2.8 (secondary sort key) recorded for
product follow-up. Full gate **776 passed, 11 skipped**.


Catalog follow-ups: `ARCADE-CATALOG-SORTS-001` (`3f5b16a`) and
`ARCADE-POPULARITY-ORDER-001` (`670923f`) completed and accepted.
`ARCADE-I18N-UI-001` hit the old token budget once and is being resumed under
the new policy: token/cost are accounting metrics, not stop conditions.
Full gate **776 passed, 11 skipped**.


`ARCADE-SEO-SITEMAP-001` (`64f1fd9`) added per-language sitemap index and
robots.txt for the public portal. The product queue continues with CRM
dashboard, catalog pagination, leaderboard attempts, SEO meta and empty-search
tasks. Full gate **776 passed, 11 skipped**.


`ARCADE-CATALOG-PAGINATION-001` (`824eb28`) completed catalog pagination with
canonical/noindex and HTMX fragment support. `ARCADE-CRM-DASHBOARD-001`
(`4242a98`) then replaced the CRM stub with real operational counters. Product
queue continues with leaderboard attempts, SEO meta and empty-search. Full gate
**776 passed, 11 skipped**.

## 1.25. Browser Arcade / App F — сверка с ТЗ (2026-11-22)

После завершения текущей продуктовой очереди проведена read-only сверка с
BA-PLAT-4.2/BA-GAME-2.2. Фактический код опережает историческую запись §7,
но нормативные контракты и product acceptance не закрыты. Работы разделены
на A (можно реализовывать), B (внешние юридические/инфраструктурные действия)
и C (реализовано, нужна продуктовая приёмка). Актуальная карта —
`docs/foundation/BA_PRODUCT_ROADMAP_AUDIT.md`. STOP установлен; новых задач
автоматически не запускается. Свежий quality gate: **792 passed, 11 skipped**.

## 1.26. Contract/ADR closure — ARCADE-P0-CONTRACT-CLOSURE-001

`ADR-APPF-001` (`docs/decisions/ADR-APPF-001.md`) фиксирует внутренние
технические решения Architect по делегированию `OD-AUTONOMY-006`:

- canonical BA-GAME-2.2 = **A** (B — историческое подмножество; ТЗ не
  переписывалось);
- BA-SDK-1.1/BA-ENV-1.1 v1.1.0 — **внутренне принятые контракты**; 64 КиБ,
  strict unknown-поля, `sessionId`/`session_id`, EventLog, trust,
  storage/If-Match, leaderboard/`myBest`;
- DB-001…DB-008 закрыты; реализованные constraints не переписываются;
- retention: сроки Приложения D обязательны, `[PROP]`-сроки — временные
  внутренние значения до юридической проверки;
- роли §2.16, staff TOTP 2FA, recovery, step-up, журнал/уведомления;
- email — единый адаптер поверх Django SMTP; production-провайдер не
  подключён;
- production requirements зафиксированы письменно; deploy, домены/TLS,
  S3/CDN/Sentry, paid services и реальный игровой ZIP **не выполнялись**.

Это **не** продуктовая приёмка App F и не закрытие этапов 0/1. Внешние
юридические, платные и инфраструктурные действия остаются за владельцем и
явно отделены в `OWNER_DECISIONS.md` (раздел D.1) и `NOW.md`.

Проверки: `ruff check`/`ruff format --check`/`mypy` — clean; sandbox
integration suite — passed; `test_contract_schemas` — 10 passed. Полная
pytest-коллекция в sandbox ограничена pre-existing copy allowlist
(`scripts/`, `sdk/`, `docs/` не копируются), поэтому часть тестов падает
только на отсутствующих файлах; это ограничение sandbox, не регрессия
документационной задачи.
