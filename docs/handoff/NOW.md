# NOW — Breaktime Arcade

**Дата:** 2026-11-20
**Текущий пакет:** BA-QUALITY-002, BA-ZIP-HARDENING-001 (R-035),
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
остатки R-033/R-035/R-036/R-037 (non-blocking).

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
   accept; full OR 10k ~150 мс — residual. R-036 — **ANALYSIS COMPLETED /
   AWAITING OWNER DECISION** (`docs/foundation/R-036_ACKS_LATE_ANALYSIS.md`):
   Phase 1 (observability/docstrings/tests) без изменения поведения возможна;
   Phase 2 (idempotency + точечный reject) — после решения владельца.
6. R-037/R-038: retention `zip_uploads`; live Telegram/Dev Control.
7. Следующий независимый срез — **R-036 Phase 1** (docstrings/контрактные
   тесты/наблюдаемость без изменения поведения); Phase 2 — после решения
   владельца. Другие READY: BA-APPF-002 (частично; DB-002/003/004/008
   делегированы), BA-DOC-README-001 (защищённые файлы).
8. manifest/catalog/locales — после BA-GAME-2.2; SDK/iframe/host protocol —
   после утверждения BA-SDK-1.1 v1.1.0 и BA-GAME-2.2; EventLog/verifier —
   после схем сообщений.

## Блокеры продукта

- `BA-SDK-1.1`/`BA-ENV-1.1`: финальные версии подготовлены, не утверждены.
- Канонический `BA-GAME-2.2` не выбран; анализ и рекомендация — A.
- Retention GameSession/GameResult/Storage — сроки не утверждены.
- Challenge после IP-порога не реализован (до O4 — 429).
- Legal texts/versions, email provider/bounce, CRM roles/step-up.
- Container E2E: Playwright driver без `libatomic.so.1`; host E2E — 13 passed;
  локально нужны `LD_LIBRARY_PATH` (libasound) и Liberation Sans.

## Решения владельца, ожидающие

- Утверждение BA-SDK-1.1/BA-ENV-1.1 v1.1.0.
- Выбор канонического BA-GAME-2.2 (рекомендация — A).
- Retention-сроки (`docs/decisions/RETENTION_PROPOSAL.md`).
- Challenge mechanism (PoW/CAPTCHA, ЕС) и узкий `TRUSTED_PROXY_IPS`.
- Приёмка APPF-SESSION-002, APPF-RESULT-001, ZIP PREFLIGHT/EXTRACT/WORKER.
- R-036: менять ли глобальный `acks_late` после аудита идемпотентности.

## Последние фактические проверки

```text
pytest tests/unit/test_zip_worker.py + compose + extract + preflight -> 49 passed
pytest (full)              -> 397 passed, 3 skipped, 1 warning
coverage                   -> 90.88 %, no module < 70 %
ZIP tests                  -> 54 passed; 2000 files fsync 7.7s
benchmark 10k              -> GIN search_vector FTS 2.4 ms; full OR 150 ms;
                              trigram index not used; unaccent STABLE
pytest tests/unit/test_devcontrol.py -> 31 passed (1 host-only skip in web)
Telegram API from WSL/Windows: TCP 443 timeout; proxy/VPN required
ruff check apps config tests -> All checks passed
ruff format --check        -> 348 files already formatted
mypy                       -> Success: no issues found in 321 source files
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

## Модели

- План/ревью: `architect`, `code-reviewer`, `security-auditor` /
  `deepseek-v4-pro`, text-only (0 tool calls).
- Реализация: основная сессия / `deepseek-flash[1m]`.
- Факт маршрутизации подтверждается `message.model` в транскриптах.

## Git

- `ba`: `main`; HEAD `678fcbe` (= `origin/main` на момент проверки).
  ZIP preflight — `fa8a1a7`, extract — `4c44009`; **BA-ZIP-WORKER-001
  в рабочем дереве не закоммичен** (изменения: worker.py, tasks.py,
  unpack.py, settings, compose, Dockerfile, entrypoint, tests, docs).
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
- R-036: анализ выполнен; глобальный `acks_late` — платформенный риск,
  Phase 2 awaiting owner.
- R-037: retention `zip_uploads` вне scope.
- R-038: Dev Control live Telegram не проверен; auto-mode может потребовать
  одобрения permissions; mid-turn injection нет (inbox на границе задачи).
- App F в целом заблокирован SDK/ENV/BA-GAME и retention.

## Ссылки

`PROJECT_STATUS.md`, `BACKLOG.md`, `CONTEXT_RECOVERY.md`, `TASK_HISTORY.md`,
`OWNER_DECISIONS.md`, `AUDIT_REGISTER.md`, `RISK_REGISTER.md`,
`docs/tasks/BA-ZIP-WORKER-001_PLAN.md`,
`docs/foundation/BA-ZIP-WORKER-001_REPORT.md`,
`docs/foundation/BA-DEVCONTROL-001_REPORT.md`, `devcontrol/README.md`,
`docs/foundation/BA-QUALITY-002_REPORT.md`,
`docs/foundation/R-036_ACKS_LATE_ANALYSIS.md`,
`docs/foundation/BA-ZIP-HARDENING-001_REPORT.md`,
`docs/foundation/BA-ZIP-PREFLIGHT-001_REPORT.md`,
`docs/foundation/BA-ZIP-EXTRACT-001_REPORT.md`,
`docs/tasks/APPF-SESSION-002_PLAN.md`,
`docs/tasks/APPF-RESULT-001_PLAN.md`,
`docs/foundation/APPF-SESSION-002_REPORT.md`,
`docs/foundation/APPF-RESULT-001_REPORT.md`,
`docs/runbook/FULL_DEPLOYMENT_FROM_ZERO.md`,
`docs/decisions/APPF-OWNER-DECISION-PACKAGE.md`.
