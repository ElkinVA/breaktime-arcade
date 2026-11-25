# NOW — Breaktime Arcade

**Дата:** 2026-11-24

## Актуальная сводка автономного цикла (2026-11-24)

- HEAD `26d8075` (email reset tokens) после `cdb567a` (restore-check),
  `ab62a7d` (Content-Length) + `116efbd` (test flake), `766029e` (ratings
  block), `88c2a64` (CRM block/unblock), `ecfb419` (safe rollback),
  `bbfdcaf`, `de08292`, `b953419`, `1fc0e97`, B1/CI; этот docs-коммит
  обновляет реестры, затем `origin/main` синхронизируется push.
- Последний полный gate: **1200 tests: 1187 passed, 13 skipped, exit 0** на
  свежей БД; JS **31/31**; ruff/format clean, mypy 382 файла clean.
  Real restore-check на dev PASS (44/42/10). Прогоны ~50-60 мин из-за
  нагрузки хоста; перед gate проверять отсутствие orphaned
  pytest/test_ba-сессий. Reuse-DB issue — `ARCADE-TEST-DB-SEED-001`.
- AI HQ: 26 прежних COMPLETED + AI-HQ-CI-001 (CI run NOT VERIFIED) +
  AI-HQ-A1 (security accept); 5 BLOCKED. Cost accounting — только фактический
  modelUsage, не stop-condition; см. `.autonomy/state.json`.
- P0 result integrity (`1fc0e97`): verification-profile results without
  `eventLog`/`seed` are quarantined and excluded from the leaderboard
  (`ARCADE-RESULT-VERIFICATION-001`); security-auditor accept, delta accept.
- P0/P1 throttling (`b953419` + `de08292` + `bbfdcaf`): session scopes
  разделены; results IP 1200/ч; complaints 5/сутки + 30/сутки IP; account
  counters в noeviction cache, атомарные login/2FA/reset, fail-closed
  auth+complaints, IPv6 /64, socket timeouts; registration device 3/сутки +
  IP 30/сутки; JSON-сериализатор throttle-кэша восстановил атомарный INCR
  на реальном Redis (`ARCADE-THROTTLE-001`, `ARCADE-AUTH-THROTTLE-001`,
  `ARCADE-REGISTRATION-LIMITS-001`). Остатки — account-lockout DoS policy,
  IP-failure burst race, CSRF device rotation, hard 30/day без challenge,
  authenticated sessions_ip exemption, heartbeat invalid-id buckets,
  DRF counters non-atomic.
- P1 accounts (`26d8075`): смена/удаление email инвалидирует
  password-reset/verify токены атомарно; confirm перепроверяет
  current/verified email и active (`ARCADE-EMAIL-RESET-INVALIDATION-001`).
  Остаток: submission-order race — `ARCADE-EMAIL-RESET-RACE-001`.
- P1 backup/DR (`cdb567a`): restore-check проверяет SHA-256 до/после
  restore, отклоняет пустой/повреждённый дамп, проверяет обязательные
  таблицы и `django_migrations`, пишет контрольные данные в metadata
  (`ARCADE-RESTORE-CHECK-001`); real dev restore PASS; staging/prod NOT
  TESTED.
- P1 API robustness (`ab62a7d`): malformed/negative `Content-Length` →
  400, oversized → 413, никогда 500 (`ARCADE-CONTENT-LENGTH-001`);
  code-reviewer accept после delta; dispatch-level тест добавлен.
- P1 CRM accounts (`88c2a64` + `766029e`): block/unblock явные
  идемпотентные, no-op без audit, toggle-маршруты удалены
  (`ARCADE-CRM-BLOCK-IDEMPOTENT-001`); оценки заблокированных немедленно
  исключаются из агрегатов и возвращаются при unblock, vote под User-lock
  перепроверяет `is_active` (`ARCADE-RATINGS-BLOCK-001`). Остаток:
  ночной recalc/backfill — `ARCADE-RATINGS-NIGHTLY-001`.
- P0/P1 publication safety (`ecfb419`): publish/rollback audit атомарен с
  переключением; rollback только на ранее опубликованную версию с
  validation/autotest/score gates; hidden/archived сохраняются
  (`ARCADE-ROLLBACK-SAFE-001`); security-auditor reject → delta accept.
- P0 A1/A2 закрыли прикладные host-exec каналы и доверие к worktree:
  exact sandbox commands, task-bound source-root, protected surfaces,
  immutable candidate до QA, чистый QA SHA, полный diff, strict verdicts,
  Git-derived commit file set. Остаток R-040 (OS-sandbox), model-trust QA/
  reviewer и продуктовый `apps/` в web-контейнере.
- Безопасная READY-очередь прежнего реестра исчерпана; owner-директива
  2026-11-24 задаёт новую P0/P1-очередь: §3.4 throttle scopes и account
  limits, §4.1 изоляция импорта черновика, §4.2 безопасный rollback,
  §4.3 разделение autotest, §5 CRM/backup/ZIP, §6 rank/Content-Length.
  Работать по этапам B→C→D, не смешивая с schema/public-contract
  изменениями без владельца.
- Открыто нужны решения владельца: scheduled-publish schema, retention
  indexes, Docker assets stage, R-054 expiresAt/alias, R-055 DRAFT schemas,
  live E2E, R-036 Phase 2; challenge/PoW после IP-порогов (owner O4) и
  политика `sessions_ip` для authenticated пользователей; signed device
  cookie + cookie policy и семантика «жёсткого блока 100» для регистрации
  (`ARCADE-OWNER-THROTTLE-DIVERGENCE-001`).
- BLOCKED: `ARCADE-ACCOUNTS-E2E-002`, `ARCADE-CRM-E2E-001`,
  `ARCADE-RETENTION-HARDENING-001`, `ARCADE-SCHEDULED-PUBLISH-001`,
  `ARCADE-RUNTIME-BUILD-SCHEMAS-001`.
- Возобновление: `.venv/bin/python -m autonomy.orchestrator status` →
  `propose` → отфильтровать задачи, требующие schema/contract/infra/E2E →
  `run --max-tasks 1`; после каждой задачи обновить реестры, PROJECT_STATUS
  и этот файл. Не запускать schema/contract/infra изменения без решения
  владельца. Следующий независимый P1-срез — reaper зависших
  `ZipExtractionJob(RUNNING)` с TTL (без схемы), затем конкурентный импорт
  и §5.3 audit events (новые action-константы требуют owner-согласования
  миграции). Stage C §4.1/§4.3 остаются owner-gated.

**Текущий этап: ARCADE-P5 ARCHER — IMPLEMENTED / LIVE DEV E2E PASS /
PRO REVIEW ACCEPT; PRODUCT + STAGING + PRODUCTION NOT ACCEPTED.**
Archer v1.3.3 опубликован на dev (`/en/games/archer/`), 60-секундный
результат 156 сохранён (rank 3), leaderboard 321/214/156; update/rollback
проверены. Fresh gate **981 passed, 12 skipped**, Browser E2E **18 passed**.
Отчёты — `ARCHER_GAME_SPEC.md`, `ARCHER_PROGRESS.md`,
`ARCHER_ACCEPTANCE_REPORT.md`, `ARCHER_OWNER_ACTION_LIST.md`.
Исходный `index4(1).html` отсутствует в рабочей среде — порт не
подтверждён. Staging/production **NOT TESTED**.

**Текущий этап: P4 OPERATIONAL HARDENING + FIRST REAL GAME — IMPLEMENTED /
PRO REVIEW ACCEPT; PRODUCT ACCEPTANCE OWNER.** Neon Snake v1.0.0 собран,
импортирован через живой `zip-worker`, опубликован, запущен в iframe,
результат сохранён (rank 1), leaderboard 200; v1.1.0 update и rollback
проверены. Quota/retention — `0ba8bfe`/`16fb095`; A3/A4/A6 — документы
`docs/audits/R-041_SYNC_WAIT_ANALYSIS.md`,
`docs/audits/ZIP_WORKER_REVIEW_EVIDENCE.md`,
`docs/runbook/staging_verification.md`. Fresh gate **966 passed, 12 skipped**;
Browser E2E **18 passed**. Отчёты — `ARCADE_P4_ACCEPTANCE_REPORT.md`,
`ARCADE_P4_OWNER_ACTION_LIST.md`, журнал — `ARCADE_P4_PROGRESS.md`.
Staging live **NOT TESTED** (нет `.env.staging`); hard FS quota/load —
NOT TESTED. Продуктовая/юридическая приёмка игры — владелец.

**Сверка фактического состояния:** код Browser Arcade/App F опережает
исторические формулировки ниже. Внутренние контракты BA-SDK-1.1/
BA-ENV-1.1/BA-GAME-2.2 закрыты Architect в `ADR-APPF-001` (2026-11-22);
product acceptance и внешние юридические/платные/инфраструктурные действия
не закрыты. Актуальная карта и три категории работ —
`docs/foundation/BA_PRODUCT_ROADMAP_AUDIT.md`. STOP снят владельцем
2026-11-22; P0/P1/P2 выполнены. Новые внешние/платные/юридические действия
по-прежнему требуют владельца.

**Текущий пакет:** P2 CRM/pipeline закрыт:
`ARCADE-P2-PIPELINE-001` (`059b7fa`), `ARCADE-P2-CRM-GAMES-001`
(`f938315`), `ARCADE-P2-CRM-WIZARD-001` (`de1c975`),
`ARCADE-P2-CRM-ROLES-001` (`6dd54d7`), `ARCADE-P2-MODERATION-001`
(`03061c0`), `ARCADE-P2-CONTENT-ANALYTICS-001` (`11c9805`).
P0 — `ADR-APPF-001` (`7c56f93`); P1 — рейтинги/TOP-100 (`51a08d0`) и
SEO/CLDR/a11y (`a167a47`). Полный fresh gate: **917 passed, 12 skipped**.
Модели: Developer/QA — `deepseek-flash[1m]`; Architect/Reviewer —
`deepseek-v4-pro`; каждый пакет имеет evidence и независимый review.

**Product acceptance 2026-11-22:** E2E 18 passed; live ZIP→publish,
public runtime, App F session/result/leaderboard/storage, rating,
rollback, CRM pages, SEO/a11y проверены. P3 закрыт:
`ARCADE-P3-ZIP-WORKER-INTEGRATION-001` (`9017254`, Pro-reviewed) —
web не распаковывает ZIP, live worker job completed, source cleaned.
Fresh gate 930 passed, 12 skipped. Отчёт —
`docs/foundation/PRODUCT_ACCEPTANCE_REPORT.md`; действия владельца —
`docs/foundation/OWNER_ACTION_LIST.md`. Остаются external production
blockers: real game/rights, email, legal, domains/TLS, S3/hosting/DR,
production deploy; staging live `.env.staging` NOT TESTED.
R-036 Phase 1 (delivery observability, non-behavioral),
BA-APPF-002 / DB-001 (tombstone-анонимизация сессий при удалении),
BA-APPF-002 / DB-006 (immutable GameVersion),
BA-APPF-002 / DB-005+007 (name 60, mode↔subject),
BA-APPF-002 / DB-004 + residuals (Game identity/delete, mode immutable),
BA-APPF-002 / runtime A+B (SDK, host, player),
BA-QUALITY-002, BA-ZIP-HARDENING-001 (R-035),
BA-DEVCONTROL-001 (Telegram Dev Control) и BA-ZIP-WORKER-001
(изолированный extraction worker);
App F server slices: SESSION-002, RESULT-001, LEADERBOARD-001, STORAGE-001,
PLAYTIME-001, RATINGS-001, POPULARITY-001; ZIP: PREFLIGHT-001, EXTRACT-001,
WORKER-001
**Статус:** SESSION-001 **ACCEPTED**; App F-срезы — **IMPLEMENTED /
AWAITING OWNER ACCEPTANCE**. ZIP preflight/extract/worker — **TECHNICALLY
ACCEPTED** агентом (OD-TECH-001, 2026-11-20); продуктовая приёмка остаётся
за владельцем. BA-ZIP-WORKER-001: plan + implementation review
(code-reviewer/security-auditor, deepseek-v4-pro, text-only) — **ACCEPT**;
остатки R-033/R-035/R-036/R-037 (non-blocking). R-036 Phase 1 —
**IMPLEMENTED / TECHNICALLY ACCEPTED** (agent; delivery behavior unchanged);
Phase 2 — **AWAITING OWNER DECISION**. BA-APPF-002 / DB-001 session
tombstone — **TECHNICALLY ACCEPTED** (agent; owner chose tombstone);
review accept; migration 0011. DB-006 GameVersion immutability —
**TECHNICALLY ACCEPTED** (agent; code/security review ACCEPT).
DB-005/007 — **TECHNICALLY ACCEPTED** (agent; code/security review ACCEPT).
DB-004 + residuals — **TECHNICALLY ACCEPTED** (agent; code/security review ACCEPT) (Game identity/delete,
GamePlayCredit cleanup, mode immutable). Runtime A+B — **IMPLEMENTED /
TECHNICAL REVIEW** (SDK/host/player/play view; review incomplete).

**ARCADE-P0-CONTRACT-CLOSURE-001** — **TECHNICALLY ACCEPTED (Architect/
internal)**: `ADR-APPF-001` фиксирует BA-GAME A, внутреннюю приёмку
BA-SDK-1.1/BA-ENV-1.1 v1.1.0, 64 КиБ/strict unknown/`sessionId`, DB-001…008,
App F trust/EventLog/storage/leaderboard, retention, roles/2FA/step-up,
email adapter и production requirements. Это не product acceptance и не
закрытие этапов; внешние юридические/платные/инфраструктурные действия не
выполнялись (см. `OWNER_DECISIONS.md` D.1).

## Активная задача

App F последовательно: Result → Leaderboard → Storage → SDK/iframe →
EventLog. Реализованы: result API (`POST /sessions/{id}/result`,
GameResult, LeaderboardEntry, DB-001/002/003), публичный leaderboard
(`limit=10|100`, me/best), storage (`GET/PUT`, 64 КиБ, revision/If-Match,
TTL гостя, активная сессия + 60/min). Throttle — Приложение E
(subject 30/ч + IP 600/ч, heartbeat 3/мин, redis-throttle, реальный IP).

ZIP pipeline: **BA-ZIP-PREFLIGHT-001** — metadata-only `preflight_zip`;
**BA-ZIP-EXTRACT-001** — streaming safe extraction (11 tests);
**BA-ZIP-WORKER-001** — отдельный Compose-сервис `zip-worker`: сеть
`zipnet` только с `redis-broker`; prefork 1; `read_only`, cap_drop ALL,
no-new-privileges, pids/mem/cpus/tmpfs; `zip_uploads` ro / `zip_artifacts`
rw; O_NOFOLLOW|O_NONBLOCK + fstat + `/proc/self/fd`; per-job flock;
statvfs 150 МБ; ATTEMPTS/quarantine; CANCEL + `cancel_check`; JSON-аудит;
cleaner. 22 new tests; full 330 passed, 2 skipped. Отчёт —
`docs/foundation/BA-ZIP-WORKER-001_REPORT.md`.

**BA-DEVCONTROL-001** — отдельный stdlib-сервис `devcontrol/`
(@breaktime_arcade_dev_bot): owner-only long polling, команды/кнопки,
одна фоновая сессия через `claude --bg`/`agents --json`/`logs`/`stop`,
state/events/inbox в `~/.local/state/ba-devcontrol`, узкий permissions,
hooks Stop/PermissionRequest/SessionEnd. 31 tests; full 360/3 skipped;
live `--bg` probe + Stop hook прошли. **BA-DEVCONTROL-002**: sandbox
test runner (`devcontrol/sandbox/run_tests.py`) — test-only DB/Redis/
Mailpit, копия без `.env`/certs/creds, internal network, no docker.sock/
egress; реальный прогон `tests/unit/test_plural.py` — 7 passed, exit 0,
без остатков. Статус — **TECHNICALLY ACCEPTED** (agent, 2026-11-21);
live setup — токен владельца (setup_token.py) и opt-in
`--enable-autonomous`; автономный `/continue` выключен по умолчанию.
Code/security review — **ACCEPT**. Отчёт —
`docs/foundation/BA-DEVCONTROL-001_REPORT.md`, README —
`devcontrol/README.md`.

**R-036 Phase 1** — **TECHNICALLY ACCEPTED** (agent, 2026-11-21):
`apps/core/celery_observability.py` (received/failure/retry/worker
shutdown; только безопасные поля), R-036 docstrings, 5 contract tests.
Живая проверка worker: `celery.task.received` для
`crm.backup_status_alert`; full 402/3; code/security review **ACCEPT**.
Поведение доставки не изменялось. Phase 2 — **AWAITING OWNER DECISION**.
Отчёт — `docs/foundation/R-036_PHASE1_REPORT.md`.

**BA-APPF-002 / DB-001** — **TECHNICALLY ACCEPTED** (agent, 2026-11-21;
owner chose tombstone): все сессии пользователя при удалении получают
`subject_type=deleted` + случайный per-session UUID; created/active
закрываются и очищают ticket/binding; finished/expired состояния
сохраняются. Migration `gameplay.0011`; full 403/3; first review reject,
re-review accept. Отчёт —
`docs/foundation/BA-APPF-002_DB001_SESSION_CLEANUP_REPORT.md`.

**BA-APPF-002 / DB-006** — **TECHNICALLY ACCEPTED** (agent; code/security
review ACCEPT): model `save()` guard + PostgreSQL trigger защищают content/
hash/version; `created_by`/`manual_review_by` только unchanged/→NULL;
`ON DELETE SET NULL` проходит. Migrations `catalog.0006`/`0007`; 16 tests;
full 419/3. Отчёт —
`docs/foundation/BA-APPF-002_DB006_REPORT.md`.

**BA-APPF-002 / DB-005 + DB-007** — **TECHNICALLY ACCEPTED** (agent):
`GameTranslation.name` ограничен 60; `GameSession` CHECK user→user,
guest→anon, preview→user/anon, autotest→user, deleted tombstone allowed.
Migrations `catalog.0008`, `gameplay.0012`; 14 tests; full 433/3.
Отчёт — `docs/foundation/BA-APPF-002_DB005_DB007_REPORT.md`.

**BA-APPF-002 / DB-004 + residuals** — **TECHNICALLY ACCEPTED** (agent; code/security review ACCEPT):
Game identity immutable после публикации и DELETE forbidden; GamePlayCredit
удаляется при удалении аккаунта; GameSession.mode immutable. Migrations
`catalog.0009`/`0010`, `gameplay.0013`; 7 tests; full 441/3. Отчёт —
`docs/foundation/BA-APPF-002_DB004_RESIDUALS_REPORT.md`.

**BA-APPF-002 / runtime A+B** — **IMPLEMENTED / TECHNICAL REVIEW**:
`ba-sdk.js`, host protocol, player host, `game_play` server-side
create+activate, exact runtime origin/full hash, no-store, CSRF relay,
guest normalization + eventLog validation + heuristic verifier; 11 added tests; full 456/4; JS syntax clean; runtime E2E 2 passed; JS host tests 4 passed; CI frontend job.
Code/security review — **INCOMPLETE** (diff evidence, JSON-Schema, parentOrigin residual). Отчёт — `docs/foundation/BA-APPF-002_RUNTIME_SDK_REPORT.md`.

## Следующий шаг

1. Владелец: `python3 devcontrol/setup_token.py --verify` (или без
   `--verify`, чтобы сохранить токен при недоступной сети), затем
   `python3 devcontrol/bot.py` или `./devcontrol/install_service.sh`;
   live `/start`/`/status`. **Telegram API из WSL и Windows сейчас
   недоступен (TCP 443 timeout), локального прокси нет** — нужен VPN или
   HTTP-прокси, покрывающий WSL2; поддержан `TELEGRAM_PROXY` (R-038).
2. Владелец выбрал **A** (OD-DEVCONTROL-002): sandbox test runner
   реализован; после токена включить opt-in `--enable-autonomous`.
   Остаточный host-user риск не-тестовых действий (git/static/status)
   принимается opt-in; тесты — только в sandbox. R-038/R-039.
3. Продуктовая приёмка владельцем ZIP PREFLIGHT/EXTRACT/WORKER
   (техническая приёмка агентом уже выполнена, OD-TECH-001).
4. R-035 — **TECHNICALLY ACCEPTED** (agent): fsync файлов/staging/
   destination, method allowlist stored/deflate (central+local), read/write
   коды; code/security review accept; отчёт
   `docs/foundation/BA-ZIP-HARDENING-001_REPORT.md`.
5. BA-QUALITY-002 — **TECHNICALLY ACCEPTED** (agent); code/security review
   accept; full OR 10k ~150 мс — residual. R-036 Phase 1 — **TECHNICALLY
   ACCEPTED** (agent; code/security review **ACCEPT**):
   observability/docstrings/5 contract tests, live `celery.task.received`,
   full 402/3; поведение доставки не изменялось. Phase 2 (idempotency +
   точечный reject, visibility timeout, worker) — **AWAITING OWNER
   DECISION** (`docs/foundation/R-036_ACKS_LATE_ANALYSIS.md`,
   `docs/foundation/R-036_PHASE1_REPORT.md`).
6. R-037/R-038: retention `zip_uploads`; live Telegram/Dev Control.
7. DB-001/004/005/006/007 + runtime A+B реализованы; probe/E2E handshake
   passed. Следующий шаг — повторный code/security review с diff-evidence.
   Внутренние контракты закрыты `ADR-APPF-001`; product acceptance и
   внешние действия остаются.
   BA-DOC-README-001 требует разрешения на защищённые файлы. Phase 2 R-036
   не начинать до решения владельца.
8. manifest/catalog/locales — после внутреннего принятия BA-GAME A
   (ADR-APPF-001); EventLog/verifier — после схем сообщений и реализации
   verifier/replay.

## Блокеры продукта

**Внутренние контракты — закрыты Architect (ADR-APPF-001):**
- BA-SDK-1.1/BA-ENV-1.1 v1.1.0 — внутренне приняты; 64 КиБ/strict
  unknown/`sessionId`/EventLog/trust/storage/leaderboard закрыты.
- BA-GAME-2.2 canonical = A; B — историческое подмножество.
- Retention: сроки Приложения D обязательны; `[PROP]`-сроки — временные
  внутренние значения; юридическая проверка ПДн/бэкапов остаётся.
- Roles/2FA/step-up и email adapter решены технически.

**Внешние блокеры (не выполнялись):**
- Legal texts/versions Terms/Privacy, DSA/EN 301 549, GDPR/consent.
- Email/S3/CDN/Sentry/платные провайдеры, домены/TLS, hosting, deploy.
- Реальный игровой ZIP/лицензии; продуктовая приёмка App F.
- Container E2E: Playwright driver без `libatomic.so.1`; host E2E — 13 passed;
  локально нужны `LD_LIBRARY_PATH` (libasound) и Liberation Sans.

## Решения владельца, ожидающие

**Закрыто внутренне (Architect, ADR-APPF-001; не требует ответа для
внутренней разработки):** BA-SDK-1.1, BA-ENV-1.1, BA-GAME-2.2, DB-001…008,
retention, roles/2FA/step-up, email adapter, production requirements.

**Требует владельца/внешнего действия:**
- Юридические тексты/версии Terms/Privacy/cookies, DSA/EN 301 549, GDPR.
- Транзакционный email-провайдер (ЕС), SPF/DKIM/DMARC, bounce-webhooks.
- Домены/TLS, хостинг, S3/CDN, Sentry, monitoring, WAL/PITR, credentials,
  production deploy.
- Реальный игровой ZIP и лицензии; продуктовая приёмка App F.
- Узкий `TRUSTED_PROXY_IPS`; challenge PoW — реализация (временно 429).
- Приёмка APPF-SESSION-002, APPF-RESULT-001, ZIP PREFLIGHT/EXTRACT/WORKER.
- R-036 Phase 2: менять ли глобальный `acks_late`/`reject_on_worker_lost`
  после аудита идемпотентности; приемлемая задержка redelivery и отдельный
  backup/restore worker.

## Последние фактические проверки

```text
2026-11-22 ADR gate (sandbox) -> integration suite passed; test_contract_schemas
                              10 passed; ruff/format/mypy clean; full pytest
                              collection in sandbox blocked by pre-existing copy
                              allowlist (scripts/sdk/docs not copied), not by this
                              documentation change
pytest tests/unit/test_zip_worker.py + compose + extract + preflight -> 49 passed
pytest (full)              -> 456 passed, 4 skipped, 1 warning
coverage                   -> 90.88 %, no module < 70 %
ZIP tests                  -> 54 passed; 2000 files fsync 7.7s
benchmark 10k              -> GIN search_vector FTS 2.4 ms; full OR 150 ms;
                              trigram index not used; unaccent STABLE
pytest tests/unit/test_devcontrol.py -> 31 passed (1 host-only skip in web)
Telegram API from WSL/Windows: TCP 443 timeout; proxy/VPN required
ruff check apps config tests -> All checks passed
ruff format --check        -> 371 files already formatted
mypy                       -> Success: no issues found in 338 source files
R-036 live                 -> celery.task.received task=crm.backup_status_alert,
                              queue=celery, redelivered=false, retries=0
DB-001                     -> all user sessions tombstoned; open aborted,
                              ticket/binding cleared; finished/expired kept;
                              migration 0011 applied; submit_result -> E_OWNERSHIP
DB-006                     -> GameVersion trigger+save guard; audit FKs only
                              →NULL; user.delete SET_NULL; migrations 0006/0007
DB-005/007                 -> name max 60; mode/subject CHECK incl. deleted
                              tombstone; migrations 0008/0012
DB-004/residuals           -> Game identity/delete guard; GamePlayCredit
                              cleanup; mode immutable; migrations 0009/0010/0013
Runtime A+B/E2E             -> play view active session + exact runtime URL; probe handshake/storage E2E 2 passed;
                              SDK/host/player node --check; review incomplete
docker compose config --quiet -> OK
./verify_stack.sh          -> СТЕК ЗДОРОВ (zip-worker healthy)
E2E queue: web uploads -> enqueue_extraction -> zip-worker ->
  artifacts/<uuid>/COMPLETED.json; audit received(0) -> extract(1, limits)
  -> complete(1); regular worker receipt отсутствует
zip-worker network: redis-broker 0; db/cache/api.deepseek.com -> gaierror
zip-worker volumes: artifacts rw, uploads ro; uid/gid 10001; read_only=true;
  pids=64; mem=512m; cpus=1.0; cap_drop=ALL; no-new-privileges
queues: worker default/default + celery/celery; zip-worker zip/zip
host E2E (13 сценариев, после локальной настройки) -> 13 passed
```

### Локальная сверка 2026-11-23 (Claude)

- **Git:** `HEAD` = `origin/main`; актуальный hash — `git log -1`;
  незакоммиченных изменений нет; локальных неотправленных коммитов нет.
- **Pytest:** полный fresh-прогон завершился без падений — **981 passed**.
  Исторический P5-отчёт указывает 13 package-тестов, фактическая текущая
  коллекция — 14; отчёт не переписывался по ограничению задачи.
  Пропуски: 7 тестов `tests/integration/test_autonomy_worktree.py` и 1 тест
  `tests/unit/test_devcontrol.py::test_sandbox_copy_excludes_secrets` —
  в контейнере `web` отсутствует `git`; ещё 4 module-level skip в
  `tests/e2e/*` — `BA_E2E` не включён. Итого отчётные **12 skipped**;
  ранее наблюдавшиеся 8 — те же 8 git-skip, без 4 E2E-модулей.
- **Локальная инфраструктура:** PostgreSQL принимает соединения; Redis
  cache/broker/throttle — `PONG`; Celery worker — `pong` (1 node online);
  `zip-worker` и `zip-volume-init` в текущем стеке **не запущены**;
  `web` запущен и healthy.
- **Dev-БД:** `Game.objects.count() = 0`; **26 неприменённых миграций**;
  поэтому `/en/games/archer/`, `/play/`, `/leaderboard/` локально 404.
  Миграции не применялись; данные не восстанавливались.
- **Окружение:** `.env` и `certs/` присутствуют; required core env names
  (`DJANGO_SECRET_KEY`, `DATABASE_URL`, `POSTGRES_*`, `REDIS_*`,
  `CELERY_BROKER_URL`, `DJANGO_ALLOWED_HOSTS`, `SESSION_BINDING_KEY`,
  `BA_SDK_DEFAULT_VERSION`, `BA_GAMES_FRAME_SRC`, `ZIP_MAX_BYTES`) заданы;
  `S3_ENDPOINT`/`SENTRY_DSN` не заданы (dev). `.env.staging` присутствует,
  но staging не валидировался.
- **Archer personal best:** fallback `isRecord || isPersonalBest` в коде
  есть; серверный `is_personal_best`/`myBest` покрыт API-тестами. Остаётся
  UI-асинхронность `myBest` (при ошибке/не-record может остаться «—»);
  это cosmetic residual, не ошибка score/rank. SDK-контракт не менялся.
- **App F Runtime Review:** `APPF-RUNTIME-REVIEW-001` —
  **IMPLEMENTED / INDEPENDENT REVIEW ACCEPT**; исправлены stale-response
  guard, newSession close, idempotency key, host validation; 79 targeted
  tests, 7 JS tests, full suite — см. `docs/foundation/
  APPF-RUNTIME-REVIEW-001_REPORT.md`. Product acceptance — владелец.
- **Delta 2026-11-23:** stale-response и Idempotency-Key reuse тесты
  (`tests/js/player_race.test.mjs`), независимый review ACCEPT после
  исправления vacuous deferred-ответов; постоянный
  `tests/integration/test_migrations_check.py`. Отчёт —
  `docs/foundation/APPF-RUNTIME-REVIEW-001_DELTA_TESTS.md`.
- **План следующей задачи:** `docs/tasks/APPF-RUNTIME-REVIEW-001_PLAN.md`.

### AI Headquarters — проверка 2026-11-23

- **A, переход между задачами:** `Orchestrator.run` умеет bounded-цикл
  нескольких задач; VPS unit запускает `--max-tasks 1`. **PASS (код),
  NOT TESTED live.**
- **B, продолжение после сессии:** автоматического запуска следующей
  сессии нет; `devcontrol` `/continue` — ручной, hooks только фиксируют
  события. **FAIL.**
- **C, постоянная фоновая работа:** `.autonomy` отсутствует; user units
  `ba-autonomy-orchestrator`/`ba-devcontrol` не установлены; timers — 0;
  background-сессий нет. **FAIL.**
- **D, восстановление:** `StateStore.recover_running`, `RUN_LOCK`,
  worktree cleanup и retry limits есть; autonomy tests **94 passed,
  1 skipped**. **PASS (код), NOT TESTED live.**
- **E, Telegram:** `api.telegram.org:443` — connection timeout; process и
  state отсутствуют. **FAIL/NOT TESTED.**
- Минимальное исправление (timer для существующего orchestrator) оформлено
  в `docs/tasks/AUTONOMY-CONTINUATION-001_PLAN.md`; статус — **BLOCKED,
  требуется решение владельца**, параллельная система не создавалась.

### Token observability 2026-11-23

`BA-TOKEN-OBSERVABILITY-001` — **IMPLEMENTED / INDEPENDENT REVIEW ACCEPT**.
`autonomy/observability.py` пишет metadata-only `invocations.jsonl`:
task/attempt/agent/role/session/invocation, model/reported models,
Claude-reported input/output/cache/cost, optional `num_turns`; exact
`request_count`/provider cache/cost недоступны из CLI и остаются None.
8 tests; autonomy subset 100/1; full suite exit 0; execution behavior,
модели, бюджет и число агентов не менялись. Отчёт —
`docs/audits/BA_TOKEN_OBSERVABILITY_IMPLEMENTATION_REPORT.md`.

`BA-TOKEN-OBSERVABILITY-002` — **IMPLEMENTED / INDEPENDENT REVIEW ACCEPT**
(minor fixes applied). Schema v2: `invocation_started`/`invocation_finished`,
failed/timeout/cancelled/interrupted, reconciliation по owner pid / PID reuse
/ boot_id, unknown usage = null + `usage_known=false`; runner — единственный
писатель lifecycle, `_account` — success-only state/budget. Реальный control
run (5 сценариев, 5 started/5 finished); 30 observability tests; full suite
**1019 tests: 1011 passed, 8 skipped, exit 0**. Остаток: usage timeout/cancel/interrupted неизвестен, provider
invoice не коррелируется, SIGKILL child, нет ротации. Отчёт —
`docs/audits/BA_TOKEN_OBSERVABILITY_002_IMPLEMENTATION_REPORT.md`.

`BA-TOKEN-EFFICIENCY-OPTIMIZATION-001` — **IMPLEMENTED**. Architect brief
(168 145→5 011 chars, −97.0 %); реальная пара planning calls: input
132 148→59 430 (−55.0 %), cost 1.617→1.205 USD (−25.5 %), output +48.8 %,
num_turns 32→39; оба proposal валидны (4/3 задачи). Один запуск на фазу —
индикативно. Модели/маршрутизация/budget не менялись. Отчёт —
`docs/audits/BA_TOKEN_EFFICIENCY_OPTIMIZATION_REPORT.md`.

`ARCADE-RETENTION-001` — **COMPLETED / AI HQ REVIEWER ACCEPT** (`8e42426`):
daily retention tasks for sessions/credits/drafts/guest storage; 8 tests +
migration guard; targeted ruff/mypy clean; full suite **1028/1020/8**. QA tooling fixed after attempt 1
(host mypy, migration guard). Остатки: no purge indexes, ProtectedError
race retry, live beat NOT TESTED.

`ARCADE-CATALOG-SLUG-301-001` — **COMPLETED / AI HQ REVIEWER ACCEPT**
(`cf0936c`): slug-history registry + 301 для старых URL, 5 tests +
migration guard, full suite **1033/1025/8**. Остатки: cross-language
negative test, shared fallback constant, concurrent get_or_create race.

`ARCADE-CRM-SEO-DIAGNOSTICS-001` — **COMPLETED / AI HQ REVIEWER ACCEPT**
(`f5474d8`): CRM `/crm/seo/` screen with empty descriptions, duplicate
titles, missing alt, incomplete translations, per-language summary; 11 tests;
full suite **1044/1036/8**. Остаток: large-catalog performance/staging/prod
NOT TESTED.

`ARCADE-SDK-ABORT-PENDING-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`ebe7d30` + `b34a288`): exit/newSession immediately settle pending SDK
requests and clear timers, late responses ignored; JS 26/26; full suite
**1125/1117/8**. `ARCADE-RUNTIME-BUILD-SCHEMAS-001` — **BLOCKED** (Docker
assets stage lacks scripts/schemas/python3; drift guarded by parity test).

`ARCADE-RUNTIME-HASH-VERIFY-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`8f9f7ac`): per-file SHA-256 + canonical tree digest vs `runtime_hash`
до отдачи; 17 targeted tests; full suite **1125/1117/8**. R-050 закрыт;
real nginx/volume E2E NOT TESTED.

`ARCADE-ARTIFACTS-SINGLE-PASS-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`ee9e9c4`): ZIP один раз копируется в spool с SHA-256, отдаётся только
проверенный spool; 15 targeted tests; full suite **1123/1115/8**. R-050
закрыт в коде; runtime zip не hash-verified, E2E NOT TESTED.

`ARCADE-STORAGE-LOCK-ORDER-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`bcd99a7`): put_storage User lock + is_active до storage locks; 4 race
tests; full suite **1121/1113/8**; R-056 закрыт. Live load/staging NOT
TESTED.

`ARCADE-CRM-MODERATION-PAGINATION-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`07a287a` + `380cd11`): обе очереди по 50, full-set summary, filters и обе
page-позиции сохраняются; 13 targeted tests; full suite **1117/1109/8**.

`ARCADE-SESSION-LOCK-ORDER-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`92ef3b1` + `f871f06`): submit_result/heartbeat берут User lock до
GameSession; 3 concurrency tests; full suite **1116/1108/8**. R-051 закрыт;
R-056 put_storage остаётся; live load/staging NOT TESTED.

`ARCADE-RUNTIME-SCHEMA-SINGLE-SOURCE-001` — **COMPLETED / AI HQ REVIEW
ACCEPT** (`f9a75d4` + `d1c4e6f`): host registry генерируется из
`schemas/messages/*.json`, parity test + unsupported-keyword guard; JS
23/23; full suite **1113/1105/8**. R-053 закрыт, R-055 (schema tightening)
остаётся; build не генерирует автоматически.

`ARCADE-ARTIFACTS-STREAMING-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`8d22aee` + `167ece6`): SHA-256 original ZIP до отдачи, chunked streaming,
temp-file runtime zip; 13 targeted tests; full suite **1112/1104/8**.
Остаток R-050: double-read in-place swap, runtime zip не hash-verified, E2E
NOT TESTED.

`ARCADE-SESSION-API-CAMELCASE-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`16068f4` + reviewer-prompt `3a91997`): POST sessions → `{sessionId,ticket,
expires_at}`, player.js без dual-handling; JS 23/23; full suite
**1109/1101/8**. E2E NOT TESTED; R-054 (expires_at/alias) остаётся.

`ARCADE-SDK-MYBEST-001` — **COMPLETED / AI HQ REVIEW ACCEPT** (`20f379c`):
host bestOnly → `{entries,myRank}`, SDK myBest извлекает value/achievedAt;
JS 23/23; full suite **1109/1101/8**; R-052 закрыт. Остаток: nickname null
(schema-legal), browser E2E NOT TESTED.

`ARCADE-RUNTIME-JSONSCHEMA-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`855caa1` + tooling `3e037c4`): schema-driven host/SDK validation,
`E_MESSAGE_INVALID`, 19/19 JS tests; full suite **1109/1101/8**. Остатки:
R-052 `myBest` mismatch, R-053 schema mirroring; browser/staging NOT TESTED.

`ARCADE-ARTIFACTS-TOCTOU-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`75d0159`): O_NOFOLLOW + fstat/inode, dir_fd tree walk; 10 targeted tests;
full suite **1109/1101/8**. Остаток R-050: memory peak, runtime zip не
hash-verified, real nginx/volume E2E NOT TESTED.

`ARCADE-SESSION-RACE-001` — **COMPLETED / AI HQ REVIEW ACCEPT after malformed
review retry** (`2ac43e1`): create_session берёт User row lock и перепроверяет
is_active; anonymize_user — тот же lock. 2 concurrency tests; full suite
**1105/1097/8**. Остаток R-051 (pre-existing lock-order inversion); live
SDK/staging NOT TESTED.

`ARCADE-APPF-RACE-TESTS-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`7af18bb`, test-only): 8 тестов на конкурентный result/leaderboard, rating
limits, storage If-Match и Idempotency-Key; full suite **1103/1095/8**.
Остаток: service-level scope; live browser/staging NOT TESTED.

`ARCADE-CATALOG-GENRE-PAGINATION-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`0c4e64d`): genre page использует общий paginate/clamp/canonical/noindex,
сохраняет sort/filters; 5 targeted tests; full suite **1095/1087/8**.
Остаток: live HTTP/nginx/staging NOT TESTED.

`ARCADE-CRM-GAME-RECORDS-001` — **COMPLETED / AI HQ REVIEW ACCEPT after one
reject** (`db8a835` + `551e73e`): read-only records/epochs tab in CRM game
card, public ordering parity, pagination 25, role guard. Первый review
поймал пустую колонку даты (ISO в `|date`); retry исправил и добавил
HTML-проверку. 5 targeted tests; full suite **1090/1082/8**. Остаток:
live browser/staging NOT TESTED.

`ARCADE-ARTIFACTS-DOWNLOAD-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`f8c3a52` + `91c9c0f`): staff-only ZIP/runtime/report downloads, step-up для
ZIP/runtime, hash-derived paths, nosniff/no-store. 6 targeted tests; full
suite **1085/1077/8**. Остаток R-050: TOCTOU при write-доступе к artifact
root; runtime zip не hash-verified; real nginx/volume E2E NOT TESTED.

`ARCADE-R049-SESSION-REVOCATION-001` (`a9e7d2b`) +
`ARCADE-R049-TOMBSTONE-CREDENTIALS-001` (`08ab9c7`) — **COMPLETED / AI HQ
REVIEW ACCEPT**: block абортирует created/active SDK-сессии и сжигает
tickets; tombstone очищает password/TOTP/recovery. Full suite
**1079 tests: 1071 passed, 8 skipped, exit 0**. Остаток: узкая гонка
create_session с revoke; live SDK/staging NOT TESTED.

`ARCADE-CRM-RATINGS-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`c577416` + fixes): фильтры game/value/visibility, overall average и
per-value distribution; 25 targeted tests; full suite **1075/1067/8**.
Остаток: строки сверх 100 не пагинируются (disclosed); staging/prod
NOT TESTED.

`ARCADE-CRM-TAXONOMY-001` — **COMPLETED / AI HQ REVIEW ACCEPT**
(`98b848c` + fixes): genre/tag CRUD, translations, delete guards, queue;
9 tests; full suite **1072/1064/8**. Остаток: rollback image orphan;
staging/prod NOT TESTED.
`ARCADE-CRM-USERS-001` — **COMPLETED / CODE REVIEW ACCEPT; SECURITY DELTA
RESOLVED** (`4095ed8` + fixes): CRM customer list/detail/search/block/delete/
export; step-up for export/delete, staff-target/tombstone guards, pagination.
R-049 residue (block SDK sessions, tombstone credentials) закрыт задачами
`a9e7d2b`/`08ab9c7`; live HTTP/CSRF not tested; full suite **1064/1056/8**.
`ARCADE-SLUG-HISTORY-HARDENING-001` — **COMPLETED / AI HQ REVIEWER ACCEPT**
(`bf33191`): race-safe history insert, shared fallback constant,
cross-language negative and concurrent tests; no schema change; full suite
**1046/1038/8**.

## Модели

- План/ревью: `architect`, `code-reviewer`, `security-auditor` /
  `deepseek-v4-pro`, text-only (0 tool calls).
- Реализация: основная сессия / `deepseek-flash[1m]`.
- Факт маршрутизации подтверждается `message.model` в транскриптах.

## Git

- `ba`: `main`; P5 acceptance — `42296fa`; последующие docs/plan-коммиты —
  `git log -1`. ZIP preflight — `fa8a1a7`, extract — `4c44009`,
  worker — `8cc4747`, hardening — `d36e4c6`; рабочее дерево чистое.
  Origin — приватный `git@github.com:ElkinVA/breaktime-arcade.git`.
- `ai-dev`: `main`, HEAD `d09a3f1`, tag `ai-dev-autonomy-003`.
- Backup: `~/backups/20261120-pre-autonomy/`.

## Активные риски

- v4-pro tool-use ненадёжен (`leading-only`); text-only паттерн обязателен.
- Bash-guard — эвристика, не sandbox.
- Fail-open throttle при отказе redis-throttle; рестарт сбрасывает счётчики.
- NAT: 600/ч на IP — компромисс; challenge не реализован.
- Retention JSONB/результатов не утверждён; R-030 residual.
- R-033: нет жёсткой ФС-квоты; общий broker (вариант A).
- R-035: fsync родительского каталога/audit, method allowlist — deferred.
- R-036: Phase 1 observability выполнена/принята; глобальный `acks_late` —
  платформенный риск, Phase 2 awaiting owner; residual — нет throttling
  fd-2-канала.
- R-037: retention `zip_uploads` вне scope.
- R-038: Dev Control live Telegram не проверен; auto-mode может потребовать
  одобрения permissions; mid-turn injection нет (inbox на границе задачи).
- App F в целом заблокирован SDK/ENV/BA-GAME и retention.

## Ссылки

`PROJECT_STATUS.md`, `BACKLOG.md`, `CONTEXT_RECOVERY.md`, `TASK_HISTORY.md`,
`docs/decisions/ADR-APPF-001.md`, `OWNER_DECISIONS.md`,
`AUDIT_REGISTER.md`, `RISK_REGISTER.md`,
`docs/tasks/BA-ZIP-WORKER-001_PLAN.md`,
`docs/foundation/BA-ZIP-WORKER-001_REPORT.md`,
`docs/foundation/BA-DEVCONTROL-001_REPORT.md`, `devcontrol/README.md`,
`docs/foundation/BA-QUALITY-002_REPORT.md`,
`docs/foundation/R-036_ACKS_LATE_ANALYSIS.md`,
`docs/foundation/R-036_PHASE1_REPORT.md`,
`docs/foundation/BA-APPF-002_DB001_SESSION_CLEANUP_REPORT.md`,
`docs/foundation/BA-APPF-002_DB006_REPORT.md`,
`docs/foundation/BA-ZIP-HARDENING-001_REPORT.md`,
`docs/foundation/BA-ZIP-PREFLIGHT-001_REPORT.md`,
`docs/foundation/BA-ZIP-EXTRACT-001_REPORT.md`,
`docs/tasks/APPF-SESSION-002_PLAN.md`,
`docs/tasks/APPF-RESULT-001_PLAN.md`,
`docs/foundation/APPF-SESSION-002_REPORT.md`,
`docs/foundation/APPF-RESULT-001_REPORT.md`,
`docs/runbook/FULL_DEPLOYMENT_FROM_ZERO.md`,
`docs/decisions/APPF-OWNER-DECISION-PACKAGE.md`.
