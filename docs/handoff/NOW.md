# NOW — Breaktime Arcade

**Дата:** 2026-11-20
**Текущий пакет:** APPF-SESSION-002 (throttle) + APPF-RESULT-001 (результат)
**Статус:** APPF-SESSION-001 **ACCEPTED** (владелец, 2026-11-20);
APPF-SESSION-002 и APPF-RESULT-001 — **IMPLEMENTED / AWAITING OWNER
ACCEPTANCE**, independent review (code-reviewer/security-auditor,
deepseek-v4-pro, text-only).

## Активная задача

App F последовательно: Result → Leaderboard → Storage → SDK/iframe →
EventLog. Result-срез реализован: `POST /api/v1/sessions/{id}/result`,
`GameResult`, `LeaderboardEntry`, DB-001/002/003. Throttle приведён к
Приложению E (subject 30/ч + IP 600/ч, heartbeat 3/мин на сессию,
redis-throttle, реальный IP из nginx).

## Следующий шаг

1. Storage: `GET/PUT /api/v1/games/{id}/storage` (ETag/revision, If-Match,
   64 КиБ, 256 ключей, TTL гостя 90 дней), затем публичный Leaderboard API.
2. SDK/iframe/host protocol — после утверждения BA-SDK-1.1 v1.1.0 и
   BA-GAME-2.2; EventLog/verifier — после схем сообщений.
3. Ожидают владельца: утверждение BA-SDK-1.1/BA-ENV-1.1 v1.1.0, выбор
   BA-GAME-2.2, retention-сроки, механизм challenge (O4), Redis/TLS
   production-настройки.

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
pytest (full)              -> 241 passed, 2 skipped
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
