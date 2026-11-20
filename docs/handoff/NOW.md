# NOW — Breaktime Arcade

**Дата:** 2026-11-20
**Текущий пакет:** APPF-SESSION-002 — throttle hardening (App F)
**Статус:** APPF-SESSION-001 **ACCEPTED** владельцем 2026-11-20
(Pro text-only review: code-reviewer + security-auditor — **accept**;
evidence — `docs/audits/APPF-SESSION-001_REVIEW_EVIDENCE.md`)

## Активная задача

`GameSession` + одноразовый launch ticket + `POST /api/v1/sessions`,
`/activate`, `/heartbeat` по BA-PLAT-4.2 §2.12.1–2.12.4 и API §2.23.
SDK/iframe, result/leaderboard/storage, GamePlaytime, preview/autotest и
ZIP pipeline в срез не входят.

## Следующий шаг

1. APPF-SESSION-002 — throttle hardening: subject 30/ч + IP 600/ч,
   heartbeat 3/мин на сессию, structured 429, redis-throttle; включает
   тест-дефицит из evidence APPF-SESSION-001.
2. BA-SDK-1.1 и BA-ENV-1.1: финальные версии v1.1.0 подготовлены и вынесены
   владельцу на утверждение (`docs/contracts/*_v1.1.0.md`,
   `docs/foundation/BA-SDK-ENV-1.1_REVIEW.md`).
3. BA-GAME-2.2: сравнительный анализ и рекомендация подготовлены
   (`docs/audits/BA-GAME-2.2_ARCHITECTURE_ANALYSIS.md`); выбор — за владельцем.
4. APPF-SESSION-002 (throttle: subject 30/ч + IP 600/ч, heartbeat 3/мин на
   сессию, redis-throttle) — сразу после фиксации среза.
5. DB-001/005/006/007 утверждены; DB-002/003/004/008 — проектирование и
   реализация техническим руководителем. Далее App F: Result → Leaderboard
   → Storage → SDK/iframe → EventLog.

## Блокеры продукта

- `BA-SDK-1.1` и `BA-ENV-1.1` отсутствуют; DRAFT не нормативны.
- Канонический вариант `BA-GAME-2.2` не выбран.
- `DB-001…DB-008` требуют решений владельца до App F-миграций
  (в срезе subject без FK — временное техническое решение).
- Legal texts/versions, email provider/bounce, CRM roles/step-up.
- Container E2E: Playwright driver без `libatomic.so.1`; host E2E — 13 passed.

## Решения владельца, ожидающие

- Утверждение BA-SDK-1.1 v1.1.0 и BA-ENV-1.1 v1.1.0
  (`docs/contracts/*_v1.1.0.md`).
- Выбор канонического BA-GAME-2.2 после сравнительного анализа.
- Retention/cleanup GameSession по §2.22/Прил. D
  (`docs/decisions/RETENTION_PROPOSAL.md`); AnonymousIdentity уже чистятся
  beat-задачей.
- Отдельный Redis/noeviction для throttle-ключей (сейчас cache
  allkeys-lru может вытеснять счётчики).
- Подтверждение [PROP]-контракта context (`strings`, `heartbeatIntervalSeconds`,
  `trustLevel`) после утверждения BA-SDK-1.1.
- Смена `ANTHROPIC_DEFAULT_OPUS_MODEL` на `deepseek-v4-pro` — уже
  применена (backup `~/.bashrc`), зафиксировано в BA-AUTONOMY-003.

## Последние фактические проверки

```text
pytest tests/integration/test_game_sessions.py -> 24 passed
pytest (full)              -> 209 passed, 2 skipped
make lint                  -> All checks passed; 335 files formatted
make types                 -> Success: no issues found in 317 source files
makemigrations --check     -> No changes detected
migrate --plan             -> No planned migration operations
./verify_stack.sh          -> СТЕК ЗДОРОВ
```

HTTP проверен через `django.test.Client(enforce_csrf_checks=True)`;
live-порт не проверялся (в dev-БД нет опубликованной игры).

## Модели

- План: `architect` / `deepseek-v4-pro`, text-only (0 tool calls).
- Реализация: основная сессия / `deepseek-flash[1m]`.
- Code review: `code-reviewer` / `deepseek-v4-pro`, text-only — **accept**
  (после исправления MAJOR throttle и одного blocker-фикса None-guard).
- Security review: `security-auditor` / `deepseek-v4-pro`, text-only —
  **accept** (F-1…F-6 закрыты/остаточные).
- Факт маршрутизации подтверждается `message.model` в subagent-транскриптах.

## Git

- `ba`: `main`, HEAD `d248d0e` (owner decision package). APPF-SESSION-001:
  product `c935237`, records `16946f6`. Ранее: `cd9c333` (BA-AUTONOMY-003),
  tag `ba-autonomy-003`, checkpoint `214af0d` /
  tag `checkpoint-2026-11-20-pre-autonomy`.
- `ai-dev`: `main`, HEAD `d09a3f1`, tag `ai-dev-autonomy-003`.
- Backup: `~/backups/20261120-pre-autonomy/` (worktree tar + git bundles).

## Активные риски

- v4-pro tool-use ненадёжен (`leading-only`); text-only паттерн обязателен.
- Bash-guard — эвристика, не sandbox; основной контроль — review и
  минимальные права.
- Guest-throttle: ротация identity ограничена IP-бакетом, но допускает
  амплификацию (~30 identity × 30 create/час с IP); владелец может сузить
  IP-потолок.
- Графовая правка `catalog.0001` (зависимость от `core.0001_extensions`) —
  вынужденное исключение из правила о применённых миграциях; schema не
  менялась, история консистентна.
- App F в целом заблокирован нормативными пробелами; нельзя выдумывать
  SDK/ENV.

## Ссылки

`PROJECT_STATUS.md`, `BACKLOG.md`, `CONTEXT_RECOVERY.md`, `TASK_HISTORY.md`,
`OWNER_DECISIONS.md`, `AUDIT_REGISTER.md`, `RISK_REGISTER.md`,
`docs/tasks/APPF-SESSION-001_PLAN.md`,
`docs/foundation/APPF-SESSION-001_REPORT.md`,
`docs/decisions/APPF-OWNER-DECISION-PACKAGE.md`.
