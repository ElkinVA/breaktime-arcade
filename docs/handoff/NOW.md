# NOW — Breaktime Arcade

**Дата:** 2026-11-20
**Текущий пакет:** App F server slices: SESSION-002, RESULT-001,
LEADERBOARD-001, STORAGE-001, PLAYTIME-001, RATINGS-001, POPULARITY-001;
ZIP pipeline: BA-ZIP-PREFLIGHT-001, BA-ZIP-EXTRACT-001
**Статус:** SESSION-001 **ACCEPTED**; остальные срезы и ZIP preflight —
**IMPLEMENTED / AWAITING OWNER ACCEPTANCE**, independent review
(code-reviewer/security-auditor, deepseek-v4-pro, text-only). ZIP preflight:
code-reviewer/security-auditor — **accept**; M-1/M-2/m-1/m-3/m-6
исправлены; остаток O-1…O-5/m-4…m-7 — R-034 (non-blocking).

## Активная задача

App F последовательно: Result → Leaderboard → Storage → SDK/iframe →
EventLog. Реализованы: result API (`POST /sessions/{id}/result`,
GameResult, LeaderboardEntry, DB-001/002/003), публичный leaderboard
(`limit=10|100`, me/best), storage (`GET/PUT`, 64 КиБ, revision/If-Match,
TTL гостя, активная сессия + 60/min). Throttle — Приложение E
(subject 30/ч + IP 600/ч, heartbeat 3/мин, redis-throttle, реальный IP).

ZIP pipeline: **BA-ZIP-PREFLIGHT-001** — metadata-only `preflight_zip`
(25/100/20 МБ, 2000 файлов, 100:1, пути/типы/коллизии/расширения,
NFKC/symlink/encryption/forged sizes, SHA-256, diagnostics) без
распаковки; 16 tests. Выполнен **BA-ZIP-EXTRACT-001** — потоковая
safe-extraction: повторный preflight,
64 КиБ чанки, независимый byte count, лимиты 20/100 МБ, CRC, канонические
пути, prefix-конфликты, `O_EXCL|O_NOFOLLOW`, атомарный rename, cleanup;
11 tests. **IMPLEMENTED / AWAITING OWNER ACCEPTANCE**; security-review —
**accept** (MINOR-1…6/A/B исправлены; R-035). OS-level
CPU/RAM/time/disk/network sandbox — **BA-ZIP-WORKER-001**.

## Следующий шаг

1. BA-ZIP-WORKER-001 — OS-level sandbox для extraction worker
   (CPU/RAM/time/disk/network, отмена, аудит); затем manifest/catalog/
   locales — после BA-GAME-2.2. SDK/iframe/host protocol — после
   утверждения BA-SDK-1.1 v1.1.0 и BA-GAME-2.2; EventLog/verifier —
   после схем сообщений.
2. Серверные API-срезы App F (sessions/result/leaderboard/storage,
   playtime, ratings) готовы к приёмке владельцем.
3. Ожидают владельца: утверждение BA-SDK-1.1/BA-ENV-1.1 v1.1.0, выбор
   BA-GAME-2.2, retention-сроки, антифрод §2.9.6 (IP/журнал), challenge
   (O4), production-настройки.

## Блокеры продукта

- `BA-SDK-1.1`/`BA-ENV-1.1`: финальные версии подготовлены, не утверждены.
- Канонический `BA-GAME-2.2` не выбран; анализ и рекомендация — A.
- Retention GameSession/GameResult/Storage — сроки не утверждены.
- Challenge после IP-порога не реализован (до O4 — 429).
- Legal texts/versions, email provider/bounce, CRM roles/step-up.
- Container E2E: Playwright driver без `libatomic.so.1`; host E2E — 13 passed.

## Решения владельца, ожидающие

- Утверждение BA-SDK-1.1/BA-ENV-1.1 v1.1.0.
- Выбор канонического BA-GAME-2.2 (рекомендация — A).
- Retention-сроки (`docs/decisions/RETENTION_PROPOSAL.md`).
- Challenge mechanism (PoW/CAPTCHA, ЕС) и узкий `TRUSTED_PROXY_IPS` для
  staging/prod.
- Приёмка APPF-SESSION-002 и APPF-RESULT-001.

## Последние фактические проверки

```text
pytest tests/integration/test_game_sessions.py -> 37 passed
pytest tests/integration/test_game_results.py  -> 19 passed
pytest tests/integration/test_leaderboard_api.py -> 7 passed
pytest tests/integration/test_game_storage.py  -> 12 passed
pytest tests/integration/test_game_ratings.py  -> 10 passed
pytest tests/integration/test_game_popularity.py -> 8 passed
pytest tests/unit/test_zip_preflight.py -> 16 passed
pytest tests/unit/test_zip_extract.py -> 11 passed
pytest (full)              -> 308 passed, 2 skipped, 1 warning
ruff check apps config tests -> All checks passed
ruff format --check        -> 344 files already formatted
mypy                       -> Success: no issues found in 320 source files
makemigrations --check     -> No changes detected
migrate --plan             -> No planned migration operations
./verify_stack.sh          -> СТЕК ЗДОРОВ (redis-throttle healthy)
XFF: запросы через nginx из web/worker -> разные IP-бакеты (172.19.0.3/5)
```

## Модели

- План/ревью: `architect`, `code-reviewer`, `security-auditor` /
  `deepseek-v4-pro`, text-only (0 tool calls).
- Реализация: основная сессия / `deepseek-flash[1m]`.
- Факт маршрутизации подтверждается `message.model` в subagent-транскриптах.

## Git

- `ba`: `main`; пакет — `fa8a1a7` (BA-ZIP-PREFLIGHT-001), docs-фиксация —
  `5870685`; актуальный HEAD — `git log -1`. Origin — приватный
  `git@github.com:ElkinVA/breaktime-arcade.git` (SSH), ветка tracking
  `origin/main`, теги `ba-autonomy-003` и
  `checkpoint-2026-11-20-pre-autonomy` запушены. App F server slices:
  `10907fd` (result/throttle), `57fda8e` (leaderboard/storage),
  `3214abf`/`f319e18` (playtime/ratings), `9b704d5` (popularity/close),
  `f43ab9d` (Git snapshot); ранее `3584eff` (accept SESSION-001 + SDK/ENV).
  ZIP preflight — `fa8a1a7`; отчёт — `docs/foundation/
  BA-ZIP-PREFLIGHT-001_REPORT.md`.
- `ai-dev`: `main`, HEAD `d09a3f1`, tag `ai-dev-autonomy-003`.
- Backup: `~/backups/20261120-pre-autonomy/`.

## Активные риски

- v4-pro tool-use ненадёжен (`leading-only`); text-only паттерн обязателен.
- Bash-guard — эвристика, не sandbox.
- Fail-open throttle при отказе redis-throttle; рестарт сбрасывает счётчики.
- NAT: 600/ч на IP — компромисс; challenge не реализован.
- Retention JSONB/результатов не утверждён; R-030 residual.
- App F в целом заблокирован SDK/ENV/BA-GAME и retention.

## Ссылки

`PROJECT_STATUS.md`, `BACKLOG.md`, `CONTEXT_RECOVERY.md`, `TASK_HISTORY.md`,
`OWNER_DECISIONS.md`, `AUDIT_REGISTER.md`, `RISK_REGISTER.md`,
`docs/tasks/APPF-SESSION-002_PLAN.md`,
`docs/tasks/APPF-RESULT-001_PLAN.md`,
`docs/foundation/APPF-SESSION-002_REPORT.md`,
`docs/foundation/APPF-RESULT-001_REPORT.md`,
`docs/foundation/BA-ZIP-PREFLIGHT-001_REPORT.md`,
`docs/runbook/FULL_DEPLOYMENT_FROM_ZERO.md`,
`docs/decisions/APPF-OWNER-DECISION-PACKAGE.md`.
