# BA-TOKEN-OBSERVABILITY-001 — design

**Дата:** 2026-11-23  
**Статус:** **IMPLEMENTED**; execution behavior orchestrator не изменён.  
**Связанные документы:** [audit](../audits/BA_TOKEN_EFFICIENCY_AUDIT_REPORT.md),
[metrics](../audits/BA_TOKEN_EFFICIENCY_METRICS.md),
[implementation](BA_TOKEN_OBSERVABILITY_IMPLEMENTATION_REPORT.md),
[schema](BA_TOKEN_OBSERVABILITY_METRICS_SCHEMA.md).

## 1. Цель

Добавить достоверный, metadata-only учёт model invocation на уровнях
task/attempt/agent/role/session/invocation, не меняя маршрутизацию моделей,
жизненный цикл задач, бюджеты, число агентов, VPS, Docker или секреты.

## 2. Проверенные источники

| Источник | Что реально доступно | Что недоступно |
|---|---|---|
| Claude Code `--output-format json` | `session_id`, `modelUsage`, `usage`, `num_turns`, `total_cost_usd`, `duration_ms`, `duration_api_ms`, `stop_reason`, `is_error` (поля схемы CLI) | точный `request_count` провайдера; `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` в явном виде; reasoning tokens — только если провайдер/CLI их отдаст |
| `modelUsage` | `inputTokens`, `outputTokens`, `cacheReadInputTokens`, `cacheCreationInputTokens`, `costUSD` (camelCase); возможные snake_case-варианты | provider invoice; точное разделение cache hit/miss как в DeepSeek billing |
| `RunResult` (исходный) | role/model/agent/session/model_usage/usage/evidence/duration/total_cost | invocation_id, timestamps, request_count, num_turns |
| `autonomy` evidence | `modelUsage`, `usage`, результат; legacy | invocation-level JSONL; не содержит task_id |
| `StateStore` | task usage, attempts, status, review/QA counters | request/cache counts; task-level invocation list |
| DeepSeek API usage | агрегаты requests/cache hit/miss/output/cost | task_id/agent_id/session_id; per-request correlation |
| Dev Control | session metadata `claude agents --json`; state | per-invocation usage; при отсутствии сессии — ничего |

**Вывод:** exact provider request count и provider cache hit/miss нельзя
получить из текущего CLI JSON без gateway/usage API. Не подменять
`request_count` числом tool calls. `num_turns` — это число model round-trips
внутри turn, отдельное поле.

## 3. Схема

Одна JSONL-запись на успешный role invocation:

```text
task_id, attempt_id, agent_id, role, session_id, invocation_id, model,
reported_models, execution_channel, request_count, num_turns,
input_tokens, cache_hit_tokens, cache_miss_tokens, output_tokens,
reasoning_tokens, estimated_cost_usd, started_at, finished_at,
status, accepted_result, retry_count, usage_source,
provider_request_count, provider_cache_hit_tokens,
provider_cache_miss_tokens
```

- `request_count` — **None**, если CLI не отдаёт точное значение; не
  выводить из `num_turns`.
- `cache_hit_tokens` = Claude-reported `cacheReadInputTokens`;
  `cache_miss_tokens` = `inputTokens + cacheCreationInputTokens`;
  `usage_source=claude_code`. Это не DeepSeek invoice.
- `estimated_cost_usd` = Claude-reported cost (`modelUsage.costUSD` или
  `total_cost_usd`); source фиксируется.
- `reported_models` — фактически встреченные ключи `modelUsage`; `model` —
  запрошенная ролью модель.
- `execution_channel=orchestrator`; интерактивные сессии в этот JSONL не
  попадают.
- `accepted_result` — nullable; acceptance выводится из `StateStore`
  (COMPLETED) при агрегации, а не угадывается при invocation.
- `retry_count` = `max(0, task.attempts - 1)` на момент invocation;
  `attempt_id` = `task.run_id`.
- Никаких prompt/response/content/headers/API keys.

## 4. Источники и происхождение

Каждая запись содержит `usage_source` и пустые provider-поля, пока
провайдерский источник не подключён. Если позже добавить gateway/usage API,
заполнять `provider_*`, не смешивая с Claude-reported.

## 5. Разделение потоков

- **Orchestrator:** `autonomy/runner.py` → `RunResult` →
  `autonomy/orchestrator.py::_account` → `invocations.jsonl`.
- **Interactive/CLI sessions:** не инструментируются этим изменением;
  остаются в транскриптах/provider billing. Нельзя складывать их суммы в
  `by_task`.
- **Provider invoice:** отдельный источник; correlation только по
  task_id/agent_id, если появится gateway.

## 6. Ограничения

- `request_count` exact отсутствует в CLI JSON; documented, not fabricated.
- Failed/timeout invocations не создают `RunResult`; их нельзя записать
  этим путём (нужен отдельный runner error hook) — residual.
- Provider cache hit/miss и reasoning недоступны без gateway/CLI поля.
- `accepted_result` requires join with task state; per-invocation field
  nullable.
- Legacy evidence still contains model result text; new invocations.jsonl
  does not. No prompt/response content added here.

## 7. Совместимость

- `RunResult` новые поля имеют defaults; старые тесты/фейки работают.
- `StateStore` schema не менялась; старый state читается.
- `invocations.jsonl` отсутствует у старых запусков; `read_invocations`
  возвращает пустой список.
- Ошибка записи метрик не меняет task outcome (`contextlib.suppress`).
