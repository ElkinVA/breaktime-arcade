# BA-TOKEN-OBSERVABILITY-001 — implementation report

**Дата:** 2026-11-23  
**Статус:** **IMPLEMENTED / TESTS PASSING / INDEPENDENT REVIEW ACCEPT**  
**Цель:** metadata-only учёт model invocations без изменения поведения
orchestrator, моделей, бюджета, числа агентов, VPS, Docker, сессий и прав.

## 1. Изменённые файлы

| Файл | Изменение |
|---|---|
| `autonomy/observability.py` | новый модуль: `InvocationMetrics`, `from_run_result`, `record_invocation`, `read_invocations`, `summarize`; provenance; дедупликация по `invocation_id` |
| `autonomy/runner.py` | `RunResult` получил optional `invocation_id`, `started_at`, `finished_at`, `request_count`, `num_turns`; runner парсит optional `request_count`/`num_turns` и пишет их в evidence |
| `autonomy/orchestrator.py` | `_account` пишет `invocations.jsonl` в `store.root`; передаёт `task_id`, `attempt_id=task.run_id`, `retry_count=attempts-1`; ошибки метрик не влияют на task |
| `tests/unit/test_autonomy_observability.py` | 8 тестов: provenance/from runner, JSONL, дедупликация, corrupt marker, нулевая стоимость, отсутствие content, task/attempt, optional counters, runner metadata |
| `docs/audits/BA_TOKEN_OBSERVABILITY_*` | design/schema/implementation report |

Никакие команды `claude`, `subprocess`, model routing, task state,
budget/stop, number of agents, systemd/VPS/Docker не изменялись.

## 2. Что реально доступно

- Claude Code JSON: `modelUsage`, `usage`, `num_turns`, `session_id`,
  `total_cost_usd`, `duration_ms`, `duration_api_ms`, `stop_reason`,
  `is_error` (по схеме CLI).
- `modelUsage`: input/output/cache read/cache creation/cost.
- `autonomy` runner: role, agent, session, evidence, duration, cost.
- State: task usage/attempts/status; `.autonomy/state.json` отсутствует в
  проверенном окружении, поэтому исторических task-записей нет.

## 3. Что является оценочным/недоступным

| Поле | Статус |
|---|---|
| `request_count` | **NOT AVAILABLE** из current CLI result; optional field remains `None`; не подменяется tool calls/`num_turns` |
| `num_turns` | доступно из CLI JSON; это model round-trips, отдельно от request_count |
| provider cache hit/miss | **NOT AVAILABLE** из CLI; Claude `cacheReadInputTokens`/`cacheCreationInputTokens` recorded separately with `usage_source=claude_code` |
| reasoning tokens | optional; только если появится в `modelUsage`/provider |
| provider request/cost invoice | owner-provided aggregate; no task correlation |
| failed/timeout invocation | **NOT RECORDED** by this path; `RunResult` only success; residual |
| accepted_result | nullable; aggregate with `accepted_task_ids` from StateStore |

## 4. Проверки

```text
pytest tests/unit/test_autonomy_observability.py -> 8 passed
pytest autonomy/devcontrol/vps subset         -> 100 passed, 1 skipped
ruff check autonomy tests                     -> All checks passed
ruff format --check                           -> clean
mypy                                           -> Success: no issues found in 359 source files
pytest --create-db (full)                     -> exit 0; 997 tests, 989 passed, 8 skipped
```

Отдельно проверено:

- нет prompt/response/secret в JSONL: тест `"secret" not in json.dumps`;
- дедупликация одинакового `invocation_id` — один учёт;
- `request_count=None` остаётся `None`, `request_count_known=0`;
- task/attempt/retry привязка через `_account`;
- старые `RunResult` без новых полей работают (defaults);
- старый state без `invocations.jsonl` читается как пустой список.

## 5. Как читать метрики

```python
from pathlib import Path
from autonomy.observability import read_invocations, summarize

records = read_invocations(Path(".autonomy"))
summary = summarize(records, accepted_task_ids={"ARCADE-..."})
```

`summary` содержит `totals`, `by_task`, `by_role`, `by_agent`, `by_model`,
`by_session`, `accepted_tasks`, `accepted_cost_usd`.

## 6. Ограничения и остатки

- Exact provider API request count и provider cache hit/miss недоступны без
  контролируемого gateway/usage API; не создаётся фиктивная точность.
- Failed/timeout calls не порождают `RunResult` и не записываются; для
  полного учёта нужен error hook в runner — отдельное изменение.
- `accepted_result` не обновляется задним числом; acceptance — join с
  task state (`COMPLETED`) при агрегации.
- Legacy evidence (`result`) не изменялся; новый JSONL не содержит
  prompt/response content. Если политика требует убрать legacy result —
  отдельное решение.
- Interactive/CLI sessions не попадают в `execution_channel=orchestrator`;
  их расход остаётся в provider billing/транскриптах.

## 7. Независимый review

`code-reviewer` — **ACCEPT** (read-only, current files + tests; exact git
diff не передавался). Findings:

- исправлено: `include_corrupt` marker больше не считается invocation;
- исправлено: дубликат `invocation_id` — first record wins, без тихой
  замены;
- исправлено: `request_count_known` добавлен в каждый bucket;
- исправлено: нулевая стоимость сохраняется как `0.0`, не `None`;
- принято как residual: `propose`/`run` могут писать JSONL параллельно
  (append одной строкой; `RUN_LOCK` не добавлен, чтобы не менять
  поведение orchestration);
- `status=error` пока недостижим через `_account` (failed/timeout
  invocation не создаёт `RunResult`);
- не покрыты тестами: reasoning tokens (поле отсутствует в CLI JSON);
  provider fields остаются None по дизайну.

Полный suite — см. §4; execution behavior не изменялся.

## 8. Git

- Commit: `feat(autonomy): add metadata-only invocation observability`
  (hash — в `git log`; файл не может содержать собственный hash).
- В коммит входят только `autonomy/`, `tests/unit/`, `docs/audits/`,
  `docs/tasks/TASK_HISTORY.md`, `docs/risks/RISK_REGISTER.md`,
  `docs/status/`, `docs/handoff/NOW.md`.
- `git status` после коммита проверяется.
