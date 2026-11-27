# NOW — Breaktime Arcade

**Дата:** 2026-11-27

## CRM browser E2E (2026-11-27)

- **ARCADE-CRM-E2E-001** — **COMPLETED / QA PASS / REVIEWER ACCEPT**
  (`0eca6a0`): host Playwright suite для staff login + 2FA, dashboard,
  games list/card/versions, step-up, complaint resolve и audit log.
  Host CRM E2E **2/2**; без `BA_E2E` — module-level clean skip.
- `make lint` — 516 formatted; `make types` — 412; standard suite
  **1366 passed / 17 skipped**. Full local `make e2e` остаётся 31/1 из-за
  unrelated LR-3 stale published runtime; CRM acceptance не блокируется,
  skip/маскировки нет.
- Autonomy cycle сначала упал на `ruff format` нового теста; файл
  отформатирован и проверен вручную, затем независимые QA/Reviewer
  приняли `0eca6a0`. Reviewer сначала ошибочно принял Python 3.14 PEP 758
  `except A, B:` за Python-2 синтаксис; после проверки вердикт исправлен
  на ACCEPT.
- Evidence:
  `.autonomy/evidence/crm-e2e-001-evidence-2026-11-27.json`,
  `qa-independent-crm-e2e-001-2026-11-27.json`,
  `reviewer-independent-crm-e2e-001-2026-11-27.json`,
  `crm-e2e-001-integration-evidence-2026-11-27.json`.
  Report: `docs/foundation/ARCADE-CRM-E2E-001_REPORT.md`.

## Accounts browser E2E (2026-11-27)

- **ARCADE-ACCOUNTS-E2E-002** — **COMPLETED / QA PASS / REVIEWER
  ACCEPT** (`5442127`): export download, password change, deletion
  request/cancel, staff 2FA enrollment/verify/disable added to host
  Playwright runner. Accounts E2E **5/5**; baseline shell/account
  scenarios **13/13**; standard suite **1366 passed / 17 skipped**.
- Full local `make e2e`: **31 passed, 1 failed**. The only failure is the
  later LR-3 `test_host_loss...`: published `whos_undercover_live` dev
  runtime lacks `#claim-host`; reseed is rejected by
  `V_VERSION_DUP`/`V_PUBLISHED_UPDATE_BLOCKED`. It is outside the
  baseline 13, not skipped or masked; follow-up requires runtime
  republish/fresh DB.
- Evidence:
  `.autonomy/evidence/accounts-e2e-002-evidence-2026-11-27.json`,
  `qa-independent-accounts-e2e-002-2026-11-27.json`,
  `reviewer-independent-accounts-e2e-002-2026-11-27.json`,
  `accounts-e2e-002-integration-evidence-2026-11-27.json`.
  Report: `docs/foundation/ARCADE-ACCOUNTS-E2E-002_REPORT.md`.

## Player start-error i18n (2026-11-27)

- **ARCADE-PLAYER-ERROR-I18N-001** — **COMPLETED / QA PASS /
  REVIEWER ACCEPT**; product acceptance owner. Play page injects
  `{% ba_t 'gameplay.start_error' %}` through `data-start-error`;
  `player.js` uses it as the fallback with no hardcoded Russian.
  Migration `0013` seeds published en/ru rows; other active locales use the
  English fallback and the coverage badge remains truthful.
- Product candidate: `e0c6230` (tree `874631d`); operational evidence fix:
  `8d55edc`; integration merge: `377fa6f`. Candidate and fix remain
  separate commits; no history rewrite.
- Integrated trusted checks: pytest, `makemigrations-check`
  (`python manage.py makemigrations --check --dry-run` → `No changes
  detected`), ruff (515 formatted), mypy (412), js (47/47) — all exit 0.
  Independent QA pass; Reviewer ACCEPT (only three non-blocking minors).
- Evidence: `.autonomy/evidence/qa-independent-player-i18n-2026-11-27.json`,
  `.autonomy/evidence/reviewer-independent-player-i18n-2026-11-27.json`,
  `.autonomy/evidence/player-i18n-integration-evidence-2026-11-27.json`.
- Task status changed through `StateStore.transition`; previous QA failure
  history remains in `last_error`/`qa_failures`.

## Email reset race + sandbox checks (2026-11-27)

- **ARCADE-EMAIL-RESET-RACE-001** — **COMPLETED / CODE REVIEW ACCEPT /
  SECURITY REVIEW ACCEPT / SANDBOX FULL SUITE GREEN**; product acceptance
  owner. `_update_email` и POST `password_reset_confirm` сериализуются на
  `User.objects.select_for_update()`; email-change notice отправляется после
  коммита. Коммиты `401df05` + `11ea832`; новый race suite **4/4**.
- **AUTONOMY-SANDBOX-CHECKS-001** (`71177d2`) — trusted sandbox не копировал
  `ruff.toml`/`mypy.ini`, поэтому два первых запуска задачи падали на
  environment-конфигурации (ruff: 430 ошибок defaults; затем 4 ошибки
  `.claude/hooks` вне `make lint`). Конфигурации добавлены, sandbox ruff
  приведён к `make lint`; review ACCEPT.
- Полный sandbox suite: **1359 passed, 11 skipped, exit 0**
  (1370 collected). Ruff: **515 formatted**; mypy: **412**; `make lint/types`
  на main clean. Без schema/migrations.
- Bounded-run после `resume` дошёл до кандидата, но упал на двух новых
  race-тестах: `force_login` в потоке email-change блокировался на
  `update_last_login` о lock reset-confirm. Тест исправлен аутентификацией
  до старта конкурирующей транзакции; кандидат принят технически.
- **ARCADE-RATINGS-OFFSET-001** — **COMPLETED / CLEAN BOUNDED-RUN /
  QA+REVIEWER ACCEPT** (`cef14b5`): `recalculate_ratings --offset`,
  детерминированные pk-страницы, тесты offset/limit и invalid offset.
  Orchestrator run завершился `status=completed`; service `Result=success`;
  queue COMPLETED 28. Это подтверждает end-to-end autonomy-loop (developer
  Flash, QA/reviewer Pro) после починки trusted sandbox.
- `ARCADE-SUBMIT-RESTART-CLEANUP-001` — **BLOCKED /
  PROTECTED_PATH_SCOPE**: developer предложил менять `sdk/1.1.0/ba-sdk.js`;
  `sdk/` защищён и требует решения владельца. Задача не обходилась.
- **Gate verification:** `autonomy pause` → `autonomy run --max-tasks 1`
  вернул `status=paused`, `OWNER_ACTION_REQUIRED`, без claim/current;
  очередь не изменилась; gate затем очищен через `resume`.
- Full suite на merged main: **1363 passed, 17 skipped, exit 0**
  (666.30 s); ruff 515 formatted, mypy 412. Main запушен в origin
  (`dcc6070`); CI run не проверен из этой среды (`gh` отсутствует).
- **Timer остаётся OFF:** `systemctl --user enable --now
  ba-autonomy-orchestrator.timer` заблокирован auto-mode permission
  harness; владельцу нужно выполнить команду вручную. Отчёты:
  `docs/foundation/AUTONOMY_SANDBOX_CHECKS_FIX.md`,
  `docs/foundation/ARCADE-EMAIL-RESET-RACE-001_REPORT.md`.

## Product vision mapping (2026-11-26)

- Новые требования владельца сопоставлены с текущей архитектурой:
  `docs/foundation/OWNER_PRODUCT_VISION_MAPPING_2026-11-26.md`.
- Текущий план не переориентирован. Уже есть гостевой запуск, каталог,
  профиль/рекорды, per-game ratings, i18n, ZIP/SDK/Host Bridge, базовая
  SEO-инфраструктура.
- Future-only пункты (avatar/site rating/collections/social/ads/SEO
  analytics/AI factory) добавлены в BACKLOG как DEFERRED; минимальный
  SEO-acceptance — `ARCADE-SEO-TECH-ACCEPTANCE-001` (audit only, не начат).
  Mass/low-quality SEO pages и game factory сейчас не создаются.

## Owner checkpoint & notifications (2026-11-26)

`AUTONOMY-CHECKPOINT-001` — **IMPLEMENTED / CODE+SECURITY REVIEW ACCEPT /
FULL GATE GREEN / CI #163 SUCCESS**; timer OFF.
- `OWNER_ACTION_REQUIRED` gate отдельно от STOP; `pause/checkpoint/
  resume/status`; проверка до claim/каждого model-call/merge; malformed
  gate fail-closed; STOP приоритетнее.
- Статусы `RUNNING/WAITING_FOR_NEXT_RUN/PAUSED_FOR_OWNER/
  MILESTONE_COMPLETED/BLOCKED/STOPPED_ERROR` + `STOPPED`; RUNNING только
  по flock+PID; systemd/timer/next-run/log paths.
- Windows toast best-effort для pause/milestone/critical; sanitized 0600
  `.autonomy/reports/last_run_report.json`; Telegram paused/milestone.
- Focused **28 passed**; autonomy/control suite pass; full gate
  **1355 passed, 17 skipped, exit 0**; ruff/mypy clean (412); real
  pause/status/resume и toast; CI **#163 success**.
- Отчёт: `docs/foundation/AUTONOMY_CHECKPOINT_POLICY_REPORT.md`.

## Autonomy heartbeat (2026-11-26)

- Owner approved 30-минутный WSL systemd user timer для существующего
  `autonomy.orchestrator` (Pro architect/reviewer + Flash developer/QA,
  текущие лимиты). Units `autonomy/vps/wsl/*` связаны в
  `~/.config/systemd/user`; `daemon-reload` выполнен.
- **Timer НЕ включён.** Текущий credential file система принимает;
  bounded-run использовал architect `deepseek-v4-pro` и developer
  `deepseek-flash[1m]`. После исправления trusted sandbox задача
  `ARCADE-EMAIL-RESET-RACE-001` технически завершена; повторный bounded-run
  для проверки autonomy-loop и gate ещё required.
- `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic`; историческая
  journal-запись с секретом относится к старому `export`-файлу; в Git
  секрет не попал. WSL должен быть запущен; Windows/WSL autostart не
  настраивался.
- **Статус:** PARTIAL / AUTH VERIFIED / TIMER OFF; owner review перед
  включением timer и успешный bounded-run обязательны.
  `docs/tasks/AUTONOMY-CONTINUATION-001_PLAN.md`,
  `docs/status/BACKLOG.md`.

## Player submit/restart hardening (2026-11-26)

- **ARCADE-SUBMIT-RESTART-HARDENING-001** (`80eabad`): exit отменяет
  queued `newSession` и закрывает replacement, созданный в гонке;
  `HostBridge.markExited()` делает `exited` терминальным
  (`sendResult`/`sendSession` не переоткрывают); boundary submit
  получает `E_SESSION_FINISHED` вместо silent drop; redundant
  `setSession` удалён.
- **Проверки:** JS **45/45**, `check:js` clean, player/SDK contracts
  **15 passed**; exact-commit CI **#159** (`80eabad`) — **success**
  (quality, frontend, e2e, image, django-next), включая full Python gate:
  https://github.com/ElkinVA/breaktime-arcade/actions/runs/45837754405
- **Статус:** COMPLETED / CODE-REVIEW ACCEPT + DELTA ACCEPT / CI #159
  SUCCESS. Остатки: duplicate close (idempotent 204), exit-during-create
  test gap, `E_SESSION_FINISHED` часто гасится SDK `cancelPending`, 30-s
  heartbeat после exit. Browser E2E/staging NOT TESTED; продуктовая
  приёмка владельца.

## Live Room LR-3 (2026-11-26)

- **Idempotency:** `RoomCreateRequest` + migration `0002`; SDK 1.2 create
  `requestId`, host bridge, `live.js`; atomic room/member/request create;
  same subject+payload replay, different subject/payload 409, deleted
  room 410, expired record 409; TTL 7 дней; anonymous cookie-loss key не
  является access token.
- **Races:** 12 PostgreSQL concurrency tests; найден и исправлен
  `read_room` vs cleanup race (`Room.DoesNotExist` → `E_ROOM_NOT_FOUND`).
- **Load/recovery/host-loss:** load baseline и бюджеты в
  `docs/foundation/LIVE_ROOM_LR3_LOAD_BASELINE.md`; restart и повторный
  Celery expire в `LIVE_ROOM_LR3_RECOVERY.md`; `#claim-host` + real
  125-s browser E2E (4 contexts) в committed test. Локальный host-loss
  **NOT VERIFIED**: published dev runtime старше source, in-container
  topology без nginx, ad-hoc current-source прогон упёрся в 30/30
  `sessions` throttle. Exact-commit CI **#157** (fresh DB +
  `make undercover-live-seed`) e2e job **success**, включая host-loss.
- **Observability:** safe structured events; 4 negative log-redaction
  tests; unknown command names сворачиваются в `other`.
- **Reviews/QA:** code-reviewer ACCEPT (must-fix race assertion fixed;
  delta ACCEPT), security-auditor ACCEPT (M1 residual), QA PASS WITH
  RESERVATIONS; 32 targeted + 26 existing/guard executed, load point
  reproduced.
- **Evidence:** idempotency 13, races 12, observability 4, recovery 3,
  Live Room 25, loadtest guard 1; JS 40/40; ruff/mypy clean; full gate
  **1324 passed, 17 skipped, exit 0** (640.78 s). Exact-commit CI run
  **#157** на `e3c9d21` — **success** (quality, frontend, e2e, image,
  django-next), e2e включает host-loss:
  `https://github.com/ElkinVA/breaktime-arcade/actions/runs/45828666386`.
  LR-3 технически подтверждён, но **product acceptance владельца
  остаётся**, Live Room не production-ready.

## Live Room LR-2b + CI restore (2026-11-26)

- **CI Stage 1:** commit **`f89ece6`** восстановил Landlock-доступ к
  interpreter roots и тестовый `checks_runner`; GitHub Actions run
  **#154** на этом коммите завершился success (quality, frontend, e2e,
  image, django-next):
  `https://github.com/ElkinVA/breaktime-arcade/actions/runs/45786462804`.
- **LR-2b:** новый картридж `games-src/whos_undercover_live` 1.0.0
  (SDK `^1.2`): create/join по коду, lobby readiness, приватный reveal,
  clues, secret vote, tie, Mr. White guess, final reveal/replay,
  reconnect, stale retry с тем же requestId (до трёх коллизий), en/ru +
  fallback-бейдж, server-side `E_BALANCE`/`E_UNDERCOVER`/`E_PLAYERS`.
- **E2E:** три Playwright-сценария с 4–5 независимыми browser contexts:
  civilian win + replay, истинная ничья 2:2 + раунд 2, Mr. White крадёт
  игру; проверяется отсутствие чужих слов на reveal screen.
- **Проверки:** rooms integration **25 passed**; package **5 passed**;
  browser **3 passed** (финальный source-harness — 3 passed); JS **40/40**;
  full Python gate **1291 passed, 17 skipped, exit 0 (814 s)**;
  ruff/format clean; mypy clean (406). Code commit пакета — **`2c9d8f7`**.
- **Independent review:** code-reviewer ACCEPT (critical Mr. White input
  bug найден и исправлен; tie-сценарий исправлен); security-auditor ACCEPT
  без must-fix; delta-подтверждение — в отчёте
  `docs/foundation/UNDERCOVER_LIVE_LR2B_REPORT.md`.
- **CI exact commit:** code commit **`2c9d8f7`**; GitHub Actions run
  **#155** `https://github.com/ElkinVA/breaktime-arcade/actions/runs/45801918631`
  — **completed success** (quality, frontend, e2e, image, django-next).
- **Модели:** Flash `deepseek-flash[1m]` — реализация/тесты; Pro
  `code-reviewer`/`security-auditor` (`deepseek-v4-pro`, text-only) —
  независимые проверки.
- **Остатки:** LR-3 load/crash/observability; host-loss E2E с реальным
  120-секундным окном; server-side create idempotency; продуктовая
  приёмка 5-мин forfeit и 120-с host claim. Live Room не выдаётся за
  production-ready.

## Live Room LR-0/LR-1/LR-2a (2026-11-26)

- Package commits **`c6daf09`** (backend), **`ecd4346`** (SDK 1.2
  transport), **`80fbcc2`** (bridge/nested-JSON hardening). Backend and
  transport are independently reviewed (code + security ACCEPT).
- Owner decision: **APPROVED — CONTINUOUS FULL PRODUCT DEVELOPMENT**
  (`docs/decisions/OWNER_DECISIONS.md` A.13). Live Room — главный следующий
  платформенный приоритет.
- `docs/decisions/ADR-LIVE-ROOM-001.md`: PostgreSQL server authority, HTTP
  polling, no Channels; SDK room protocol planned as additive 1.2.
- Backend `apps/rooms`: create/join/leave, lobby ready/start, private
  role/word delivery, sanitized snapshots, reveal/clues/secret vote/tie/
  Mr. White/win/restart, idempotent requestId + required expectedVersion,
  TTL 30 min/2 h/30 min idle, beat expiry + 24 h cleanup, host transfer and
  stale-host claim (120 s), account-deletion scrub, CSRF + throttles +
  `private, no-store`.
- Independent security/code review found and we fixed: mid-game leave
  deadlock (now forfeit/resolve), host single point (leave transfers; stale
  host can be claimed; 5-min stale members are auto-forfeited on read), idle
  TTL beat coverage, replay/expiry order, expired/abandoned role disclosure,
  repeat leave idempotency, error-path anonymous cookie, anonymisation second
  scan.
- **LR-2a transport:** schemas `ba:room`/`ba:room:data`, `sdk/1.2.0`
  `room.create/join/state/command/leave`, host bridge via CSRF/session API,
  tested camelCase mapping, separate room rate bucket, stable requestId,
  nested-JSON 400 guard. SDK 1.1 and Pass & Play remain unchanged.
- Tests: rooms **20 passed**; accounts **25 passed**; JS **40/40**; full gate
  **1281 passed, 15 skipped, exit 0 (617 s)**; ruff/format clean (501), mypy
  clean (406). Residual 5-min stale forfeit needs LR-2 product/UX sign-off.
- **Not implemented:** Live Room game UI, two-browser E2E, load/staging.
  **LR-2b was the next READY package (delivered in ARCADE-LIVE-ROOM-003)**;
  Live Room is not marketed as ready.

## Актуальная сводка автономного цикла (2026-11-25)

- HEAD `16af4f9` (game language fix) после `776d87c` (Who's Undercover?),
  `ef242eb`, `331a1a6`, `f17d239`, `3c997d6`, `dba59fb`, `9fc9096`,
  `16dba6d`, AI HQ `f303b01`/`86b21d6`/`b3f42ce`; этот docs-коммит
  обновляет реестры, затем `origin/main` синхронизируется push.
- Последний полный Python gate: **1261 passed, 15 skipped, exit 0** на
  reuse-DB без `--create-db` (12:13); ruff/format clean (488), mypy clean
  (394). JS suite **31/31 + 12/12 game core**, browser E2E **25/25**.
  Перед gate проверять отсутствие orphaned pytest/test_ba.
- ZIP Redis isolation: `ARCADE-REDIS-BROKER-ISOLATION-001` (`9fc9096`) —
  **COMPLETED / code-review ACCEPT**; отдельный `redis-zip`, zip-worker не
  видит default broker; publisher-only app с explicit connection; live
  dispatcher/extraction доставлены; стоимость — один Redis 96 МБ + volume.
- CI browser E2E: `ARCADE-CI-BROWSER-E2E-001` (`dba59fb` + `3c997d6` +
  `331a1a6`) — **COMPLETED / code-review ACCEPT**; GitHub job ставит
  openssl certs/Chromium, поднимает dev stack, сеет probe runtime и
  запускает `make e2e`, cleanup всегда; локально **22 passed** за 34.5 с;
  hosted run **NOT EXECUTED**. `probe-seed` публикует runtime от UID 10001.
  Критические сценарии `ARCADE-GAME-E2E-CRITICAL-001` (`f17d239` +
  `c1e3940` + `71a7274`) — **COMPLETED / code-review ACCEPT** (guest/auth
  submit, leaderboard, restart, exit/return).
- Browser publish gate: `ARCADE-BROWSER-AUTOTEST-RUNNER-001`
  (`a1388da` + `16dba6d`) — **COMPLETED / code-review ACCEPT после reject**;
  Chromium вынесен в secretless `browser-autotest` (autotestnet, без
  .env/БД/Redis/edge), единый deadline, prod требует `playwright=true`;
  live positive 3/3 и negative page error; prod-style image build OK.
  Staging browser gate выключен до browser-testable topology; prod nginx
  game hosts/TLS остаются owner deploy gate.
- Player UX: `ARCADE-PLAYER-HEADER-001` (`ef242eb`) — локализованное
  название игры в шапке, ограничение ширины и перенос на мобильном;
  product acceptance pending. Локализация ошибок старта и продуктовая
  restart-кнопка остаются.
- Who's Undercover? Pass & Play (`ARCADE-UNDERCOVER-PASSPLAY-001`, 1.0.1) —
  **COMPLETED / code-review ACCEPT**: 4–12 игроков, 10 колод en/ru,
  Undercover/Mr. White, privacy handoff, тайное голосование, все победы,
  replay, timer/sound/projector, 360 px; JS 12/12, E2E 3/3, full browser 25.
  ZIP импортирован/опубликован через pipeline; Live Room — P1 platform
  room contract, не выдаётся за готовое. Язык игры теперь фиксируется
  cookie на play page (`ARCADE-GAME-LANGUAGE-COOKIE-001`).
- AI HQ OS sandbox (`ARCADE-AI-HQ-OS-SANDBOX-001`, `f303b01`/`86b21d6`/
  `b3f42ce`) — **COMPLETED / security-auditor ACCEPT**; private user+mount
  namespace + Landlock, fail-closed 125; остатки abstract AF_UNIX/netns,
  gitdir ro и live unattended run.
- Внешний аудит 2026-11-25 разобран: `docs/audits/EXTERNAL_AUDIT_2026-11-25.md`.
  Приняты и исправлены P1 импортов, browser gate, empty eventLog и P2
  pagehide; дополнительно probe_seed guard, validation-gate
  schedule_publish, точная граница eventLog и общая константа. Draft
  isolation §4.1 и PB `is_public` — owner-gated.
- Локальная инфраструктура 2026-11-25: staging-стек остановлен
  (`make staging-down`) из-за исчерпания RAM/swap; volumes/данные не
  удалялись, для staging-проверок поднять `make staging-up`. Host после
  остановки: ~1.9 ГБ available.
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
- Refactor (`c7bc92e` + `40264c2`): `_rank` из submit/read-side вынесен в
  общий `entry_rank`; полный tie-break и сверка с `annotate_rank` покрыты
  тестом; поведение/query shape не изменились
  (`ARCADE-LEADERBOARD-RANK-UNIFY-001`). Остаток — `previous` без
  `is_public`-фильтра.
- P1 rank (`df8cad6` + `910f268`): для non-PB результата rank — место
  лучшей строки пользователя (не гипотетическое место прогона), `is_record`
  только для PB-#1; добавлены PB-not-first и lower-is-better тесты; review
  ACCEPT (`ARCADE-RANK-NONPB-001`). Остатки — объединение `_rank` и
  `is_public`-фильтр (`ARCADE-LEADERBOARD-RANK-UNIFY-001`).
- P1 result payload (`ea47229` + `0a0dbfb`): eventLog лимит 2 MiB считается
  в UTF-8 байтах; lone surrogate даёт структурированную 400-ошибку, не 500
  (`ARCADE-EVENTLOG-BYTES-001`); review ACCEPT, delta ACCEPT. Остатки —
  граница 2 MiB и дублирование константы.
- P1 player (`24d9979` + `a81ec48`): submit/restart — сабмиты одной сессии
  сериализованы, `newSession`/`exit` ждут chain перед закрытием, перезапуски
  сериализованы, каждая API-попытка с 10 s timeout; JS 31/31; code-reviewer
  ACCEPT (`ARCADE-SUBMIT-RESTART-001`). Остатки — hardening follow-up;
  browser E2E/staging NOT TESTED.
- P1 ratings (`006aaca` + `b24ff78` + `4c5dd02`): ночной пересчёт
  агрегатов оценок — union голосов/агрегатов, pk order, транзакция+advisory
  lock на игру, skip-if-unchanged, per-game failure isolation; daily beat
  2400/3000, команда `recalculate_ratings --dry-run --limit`; ревью ACCEPT
  (`ARCADE-RATINGS-NIGHTLY-001`). Остатки M1 offset, M3 6 queries, M4
  24-часовой catch-up; live beat/worker NOT TESTED.
- Test infra (`8e5f507` + `995f5d2`): fixture восстанавливает все i18n
  seed-миграции 0002-0012 после transaction-flush; discovery динамический,
  fail-loud; reuse-DB gate зелёный без `--create-db`
  (`ARCADE-TEST-DB-SEED-001`).
- P1 ZIP pipeline (`1687517` + `03aaf0f` + `34f237f`): reaper зависших
  RUNNING jobs (TTL 600 s, beat 5 мин, X_JOB_STALE), сериализация импорта
  одной игры (advisory lock technical_id, adoption, `V_ID_CONFLICT`,
  runtime rename race) и ref-aware TTL-очистка runtime-бандлов без ссылки
  `GameVersion` (сутки; worker получил rw `runtime_data`) —
  `ARCADE-ZIP-JOB-REAPER-001`, `ARCADE-ZIP-CONCURRENT-IMPORT-001`,
  `ARCADE-RUNTIME-ORPHAN-001`; §5.5 закрыт по runtime/import. Live worker
  recreation и удаление aged orphan проверены; live beat/staging NOT TESTED.
- P0/P1 ZIP security (`1c19af5` + `d90af22` + `1cbbec3`): изолированный
  `zip-worker` больше не получает полный `.env`; 13-ключевой non-secret
  allowlist, паритет брокера/лимитов через интерполяцию, staging без
  `env_file`, prod-оверлей запинен (`ARCADE-ZIP-WORKER-SECRETS-001`);
  security-auditor ACCEPT; live dev probe E2E PASS, staging/prod NOT
  TESTED. Остатки M1/M3–M5 в TASK_HISTORY.
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
  владельца. `ARCADE-RUNTIME-ORPHAN-001`,
  `ARCADE-ZIP-WORKER-SECRETS-001` и `ARCADE-RATINGS-NIGHTLY-001`
  завершены. Приоритет после аудита: (1) owner-решения по draft isolation
  §4.1 и PB `is_public`; (2) `ARCADE-CI-BROWSER-E2E-001` и staging на
  ресурсах с реальным RAM/swap; (3) §6.2 Neon restart/seed, §6.3 Archer RNG,
  §6.4/6.6 SDK serializer/score type (публичный контракт), §6.10 player
  error messages (i18n data-миграция); (4) мелкие follow-up
  `ARCADE-SUBMIT-RESTART-HARDENING-001`, eventLog boundary, ratings offset.
  Stage C §4.1/§4.3 — owner-gated.

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
