# AI development system — технический аудит и план исправления

**Дата:** 2026-11-21
**Статус:** аудит выполнен; реализация control plane — в `autonomy/`.
**Границы:** конфигурация Claude Code/DeepSeek, model routing, subagents,
skills, hooks, Dev Control, очередь/состояние. Игровые функции не меняются.

## 1. Фактическая конфигурация

Проверено по `~/.bashrc`, переменным окружения, `.claude/` и транскриптам
Claude Code (без вывода секретов):

| Параметр | Факт |
|---|---|
| API endpoint | `https://api.deepseek.com/anthropic` |
| Основная модель | `deepseek-flash[1m]` |
| `ANTHROPIC_DEFAULT_OPUS_MODEL` | `deepseek-v4-pro` |
| `ANTHROPIC_DEFAULT_SONNET_MODEL` | `deepseek-flash[1m]` |
| `ANTHROPIC_DEFAULT_HAIKU_MODEL` | `deepseek-flash` |
| `CLAUDE_CODE_SUBAGENT_MODEL` | `deepseek-flash` |
| Claude Code | 2.1.329 |

Агенты в `.claude/agents/`: `architect`, `code-reviewer`,
`security-auditor` — `deepseek-v4-pro`; `developer`, `qa-engineer` —
`deepseek-flash`. Skills — 8; hooks — project pre-tool guards; Dev Control —
31 tests, state in `~/.local/state/ba-devcontrol`.

## 2. Фактические вызовы моделей

Транскрипты: `/home/elkinva/.claude/projects/-home-elkinva-projects-ba/`.

- Основная сессия: **3 931 assistant-вызов, все `deepseek-flash`**; ни одного
  Pro-вызова в main loop.
- Subagents: 21 JSONL; **20 — `deepseek-v4-pro`**, 1 — Flash built-in
  (`claude-code-guide`). У Pro-агентов есть реальные `Read`/`Grep` и
  `SubagentHandback`; meta `pickedEffortModel` показывает Flash, но
  `message.model`/`modelUsage` — Pro. Это важно: meta-поле не является
  доказательством; смотреть надо `modelUsage`.
- Отдельная CLI-проба `claude -p --model deepseek-v4-pro --agent architect
  --permission-mode plan --allowedTools Read,Grep,Glob`: 3 turn, 2 файла
  прочитаны, `modelUsage.deepseek-v4-pro` input 15 243 / output 2 243,
  `permission_denials: []`, `is_error: false`. Pro **умеет** читать файлы в
  таком режиме.

Вывод: маршрутизация моделей существует, но **Pro вызывается только вручную**
(через Agent/CLI); автоматического Architect → queue → Developer → QA →
Reviewer цикла нет.

## 3. Почему Pro почти не используется

1. Main session запущена на Flash и сама выбирает задачи/пишет код.
2. Skills (`ba-development`, `ba-plan`, `ba-code-review`) лишь **инструктируют**
   вызвать Pro; ни один hook/runner не проверяет факт вызова.
3. `architect`/reviewers имеют text-only prompt; в большинстве вызовов
   Pro отвечал без чтения репозитория (только `SubagentHandback`).
4. Нет **task manager/queue**: выбор задачи — эвристика в NOW/BACKLOG.
5. `CLAUDE_CODE_SUBAGENT_MODEL=deepseek-flash` и meta `pickedEffortModel`
   создают впечатление Flash даже для Pro-агентов; фактический `modelUsage`
   надо проверять отдельно.
6. `ba-plan` ранее требовал остановки после плана; `ba-development` не
   связывает план с исполнением автоматически.

## 4. Почему «продолжай» повторяет работу

`docs/handoff/NOW.md` и `BACKLOG.md` — **проза**, а не очередь. Нет:

- уникального task ID/status/attempts;
- claim/lock текущей задачи;
- completed-set и fingerprint-дедупликации;
- зависимостей и BLOCKED-причин;
- durable current/run/session state;
- автоматического перехода после review;
- восстановления после падения процесса.

Поэтому новая сессия перечитывает регистры, заново интерпретирует «следующий
шаг» и может снова выбрать уже сделанное. Dev Control управляет **одной
фоновой сессией**, но не очередью задач: `/continue` запускает сессию, а не
атомарно выдаёт следующую задачу; state содержит только сессию/heartbeat.

## 5. Архитектурные дефекты

1. Нет durable task queue/state machine.
2. Нет enforced model routing: Pro не обязан участвовать в решении/review.
3. Нет независимой проверки, что Architect реально читал репозиторий.
4. Нет auto-handoff Architect → Developer → QA → Reviewer.
5. Нет retry limit/BLOCKED transitions.
6. Нет recovery после перезапуска/остановки.
7. Нет защиты от повторного выполнения COMPLETED.
8. Нет evidence с фактическими modelUsage/session_id.

## 6. План исправления

### Этап 1 — control plane (этот пакет)

`autonomy/`:

- `state.py` — JSON state + `fcntl` lock + atomic write; задачи, статусы,
  attempts, dependencies, completed fingerprints, recovery.
- `runner.py` — реальный `claude -p` с точным `--model`, `--agent`,
  `--permission-mode`, `--allowedTools`; проверка `modelUsage` (Pro/Flash);
  evidence JSON.
- `orchestrator.py` — Architect Pro → queue → Developer Flash → QA Flash →
  Reviewer Pro → COMPLETED/RETRY/BLOCKED; auto-next; stop file.
- Agents `autonomy-architect`, `autonomy-developer`, `autonomy-qa`,
  `autonomy-reviewer`.
- CLI: `run`, `propose`, `enqueue`, `status`, `recover`.
- Unit tests: dedup, dependencies, recovery, retry/block, model parsing,
  forbidden non-AUTONOMY tasks.

### Этап 2 — доказательство

- Real Pro Architect call (CLI) with `modelUsage` evidence.
- Real Flash Developer edit of a **control-plane test/doc**, not a game feature.
- Real Flash QA check.
- Real Pro Reviewer diff verdict.
- Auto-next/idle report; restart recovery; completed dedup.

### Этап 3 — интеграция

- Подключить orchestrator к Dev Control event/status (без Telegram live).
- После проверки — использовать как единственный путь выбора задач.
- Owner decision: BA-SDK/ENV/BA-GAME, staging/prod, product acceptance.

## 7. Acceptance criteria

- Pro Architect reads repo and returns at least one concrete task with
  acceptance criteria.
- The task is persisted and claimed exactly once.
- Flash Developer executes it; evidence contains Flash `modelUsage`.
- QA executes real checks; Reviewer Pro sees the diff and returns verdict.
- Accepted task becomes COMPLETED; next task is selected automatically.
- Restart with a RUNNING task recovers to READY or BLOCKED.
- Re-enqueue of COMPLETED task/fingerprint is rejected.
- No `--dangerously-skip-permissions`; protected files untouched.
- `make check`, ruff, mypy, autonomy unit tests green.

## 8. Live control-plane evidence (2026-11-21)

- **Architect (Pro):** CLI session `79aef134-e1a8-42a0-9ec9-ac8d292ac2bc`,
  agent `autonomy-architect`, `modelUsage.deepseek-v4-pro`,
  input 87 927 / output 16 459 / thinking 12 909; returned 4 concrete
  `AUTONOMY-*` tasks with acceptance criteria. Evidence:
  `.autonomy/evidence/architect-*.json`.
- **Developer (Flash):** session `d149cd69-f49f-490f-8081-69ed130c6c0c`,
  `modelUsage.deepseek-flash[1m]`/`deepseek-flash`; added
  `tests/unit/test_hooks_guard.py`; evidence
  `.autonomy/evidence/developer-*.json`.
- **QA (Flash):** session `e650e7a6-75ca-43d2-b2de-a0a4ce949b04`,
  `modelUsage.deepseek-flash`; real `make test` = 652 passed, 4 skipped;
  `make check` = 0.
- **Reviewer (Pro), first attempt:** session
  `b56e4714-203d-447b-9ea1-01d1826912a9`, `modelUsage.deepseek-v4-pro`;
  independently read the hooks/test file, found the deliverable
  untracked/uncommitted, verdict **reject**; task moved to retry.
- **Second attempt:** Developer Flash session
  `12cb4074-d3d1-4bc2-8fb2-0c93003d34a7` reported the deliverable file;
  QA Flash session `5e34badd-...` ran `make check` = 657 passed, 4 skipped;
  the orchestrator committed `24cd6fd`; Reviewer Pro session
  `36f8fac4-b3a8-442e-a875-a56c50c28410` independently read the committed
  diff and **accepted** (minor residuals only).
- **Auto-next:** after `AUTONOMY-GUARD-TESTS-001` became COMPLETED, the
  orchestrator claimed `AUTONOMY-CONFIG-CONTRACT-001` (RUNNING) without a
  new owner command. The protected-hook task `AUTONOMY-GUARD-HARDEN-001` is
  BLOCKED with `OWNER_APPROVAL_REQUIRED`.

The control plane records every command, session, modelUsage and verdict in
the evidence JSON; a role whose actual model does not match is failed closed.
Queue state survives in `.autonomy/state.json`; completed IDs/fingerprints
are never re-enqueued.

## 9. Stop conditions

- Pro model usage absent or misrouted.
- Developer attempts game/App F features during the owner freeze.
- Protected file edit, secret access, destructive command.
- Review rejects after max attempts → BLOCKED with reason.
- No useful tasks → idle report, not simulated work.
