# NOW — Breaktime Arcade

**Дата:** 2026-11-20
**Текущий пакет:** App F server slices: APPF-SESSION-002, RESULT-001,
LEADERBOARD-001, STORAGE-001
**Статус:** SESSION-001 **ACCEPTED**; остальные срезы **IMPLEMENTED /
AWAITING OWNER ACCEPTANCE**, independent review (code-reviewer/
security-auditor, deepseek-v4-pro, text-only) — accept.

## Активная задача

App F последовательно: Result → Leaderboard → Storage → SDK/iframe →
EventLog. Реализованы: result API (`POST /sessions/{id}/result`,
GameResult, LeaderboardEntry, DB-001/002/003), публичный leaderboard
(`limit=10|100`, me/best), storage (`GET/PUT`, 64 КиБ, revision/If-Match,
TTL гостя, активная сессия + 60/min). Throttle — Приложение E
(subject 30/ч + IP 600/ч, heartbeat 3/мин, redis-throttle, реальный IP).

## Следующий шаг

1. SDK/iframe/host protocol — после утверждения BA-SDK-1.1 v1.1.0 и
   BA-GAME-2.2; EventLog/verifier — после схем сообщений.
2. Серверные API-срезы App F (sessions/result/leaderboard/storage) готовы
   к приёмке владельцем; storage требует активную игровую сессию
   (семантика §2.22 «через родительскую сессию»).
3. Ожидают владельца: утверждение BA-SDK-1.1/BA-ENV-1.1 v1.1.0, выбор
   BA-GAME-2.2, retention-сроки (включая sliding TTL гостя и очистку
   anon-storage), challenge (O4), production-настройки.

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
pytest (full)              -> 260 passed, 2 skipped
make lint                  -> All checks passed; 336 files formatted
make types                 -> Success: no issues found in 317 source files
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

- `ba`: `main`, HEAD — коммиты APPF-SESSION-002/RESULT-001 (см. `git log`);
  предыдущий `3584eff` (accept SESSION-001 + SDK/ENV v1.1.0).
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
`docs/decisions/APPF-OWNER-DECISION-PACKAGE.md`.
