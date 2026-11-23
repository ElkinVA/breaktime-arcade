# BA-TOKEN-OBSERVABILITY-METRICS-SCHEMA

**Дата:** 2026-11-23  
**Формат:** append-only JSONL, одна строка на role invocation.  
**Путь:** `.autonomy/invocations.jsonl` (локальное состояние, вне Git).  
**Запрещено:** prompt content, response content, HTTP headers, API keys,
cookies, tokens, stack traces, произвольные tool outputs.

**Schema v2 (BA-TOKEN-OBSERVABILITY-002):** журнал содержит события
`invocation_started` и `invocation_finished`; token/cost-поля могут быть
`null` при `usage_known=false`; добавлены `request_count_known`, `status`,
`error_type`, `exit_code`, `duration_seconds`, `inferred`, `reconciled_at`.
Legacy-записи без `event` остаются читаемыми как authoritative terminal.
Полная схема — `docs/audits/BA_TOKEN_OBSERVABILITY_002_DESIGN.md`.

## 1. Record

| Поле | Тип | Null | Источник | Смысл |
|---|---|---:|---|---|
| `task_id` | string | да | orchestrator | task, к которой относится вызов; `None` для architect proposal |
| `attempt_id` | string | да | `Task.run_id` | уникальный id попытки; `None` для proposer |
| `agent_id` | string | нет | `RunResult.agent` | имя agent definition |
| `role` | string | нет | `RunResult.role` | architect/developer/qa/reviewer |
| `session_id` | string | да | Claude Code JSON | session id |
| `invocation_id` | string | нет | runner UUID | уникальный invocation; ключ дедупликации |
| `model` | string | нет | requested role model | запрошенная модель |
| `reported_models` | array[string] | нет | keys(`modelUsage`) | фактически отчитавшиеся модели |
| `execution_channel` | string | нет | local | `orchestrator` |
| `request_count` | int | да | CLI `request_count`, если есть | точное число API requests; **не** выводить из tool calls/num_turns |
| `num_turns` | int | да | CLI `num_turns` | model round-trips внутри turn; отдельная метрика |
| `input_tokens` | int | нет | Claude `usage` | обычные input tokens |
| `cache_hit_tokens` | int | нет | Claude `cacheReadInputTokens` | Claude-reported cache read |
| `cache_miss_tokens` | int | нет | `input + cacheCreation` | Claude-reported, не provider invoice |
| `output_tokens` | int | нет | Claude `usage` | output |
| `reasoning_tokens` | int | да | `modelUsage` field, если есть | reasoning, только при наличии |
| `estimated_cost_usd` | float | да | Claude `costUSD`/`total_cost_usd` | reported cost, не invoice |
| `started_at` | ISO-8601 | да | runner wall clock | начало invocation |
| `finished_at` | ISO-8601 | да | runner wall clock | конец invocation |
| `status` | string | нет | runner | `ok`/`error` (successful RunResult) |
| `accepted_result` | bool | да | join с task state | null на invocation; вычисляется агрегатором |
| `retry_count` | int | нет | `attempts-1` | номер повторной попытки |
| `usage_source` | string | нет | local | сейчас `claude_code` |
| `provider_request_count` | int | да | provider gateway | зарезервировано; сейчас null |
| `provider_cache_hit_tokens` | int | да | provider gateway | зарезервировано; сейчас null |
| `provider_cache_miss_tokens` | int | да | provider gateway | зарезервировано; сейчас null |

## 2. Пример (без содержимого)

```json
{
  "task_id": "ARCADE-EXAMPLE-001",
  "attempt_id": "018f...",
  "agent_id": "autonomy-developer",
  "role": "developer",
  "session_id": "018f...",
  "invocation_id": "018f...",
  "model": "deepseek-flash[1m]",
  "reported_models": ["deepseek-flash[1m]"],
  "execution_channel": "orchestrator",
  "request_count": null,
  "num_turns": 4,
  "input_tokens": 12,
  "cache_hit_tokens": 100,
  "cache_miss_tokens": 16,
  "output_tokens": 3,
  "reasoning_tokens": null,
  "estimated_cost_usd": 0.04,
  "started_at": "2026-11-23T09:00:00+00:00",
  "finished_at": "2026-11-23T09:00:01+00:00",
  "status": "ok",
  "accepted_result": null,
  "retry_count": 0,
  "usage_source": "claude_code",
  "provider_request_count": null,
  "provider_cache_hit_tokens": null,
  "provider_cache_miss_tokens": null
}
```

Значения примера — иллюстрация типов; не фактические данные.

## 3. Агрегация

`autonomy.observability.summarize(records, accepted_task_ids=...)` возвращает:

```text
totals:
  invocations, request_count_known,
  input_tokens, cache_hit_tokens, cache_miss_tokens, output_tokens,
  reasoning_tokens, estimated_cost_usd, retry_count
by_task / by_role / by_agent / by_model / by_session:
  invocations, request_count, request_count_known, input_tokens,
  cache_hit_tokens, cache_miss_tokens, output_tokens, reasoning_tokens,
  estimated_cost_usd, retry_count
accepted_tasks, accepted_cost_usd
```

Правила:

- дедупликация по `invocation_id`;
- `request_count` суммируется только если он известен; `request_count_known`
  показывает, у скольких записей он есть;
- `accepted_task_ids` передаются из `StateStore` (status COMPLETED);
- интерактивные сессии в этот файл не попадают; их нельзя смешивать с
  `by_task`;
- `accepted_cost_usd` — сумма invocation costs по task_id, принятым
  владельцем/орchestrator-статусом; происхождение остаётся Claude-reported.

## 4. Cache hit/miss

`cache_hit_tokens`/`cache_miss_tokens` — **Claude-reported** значения из
`modelUsage`; они не равны DeepSeek billing cache hit/miss, если провайдер
считает иначе. Для провайдерской точности заполнять `provider_*` из
контролируемого gateway/usage API.

## 5. Model attribution

`model` — запрошенная модель; `reported_models` — ключи `modelUsage`.
Расхождение (`model` not in `reported_models`) видно, но не исправляется
этим слоем. `autonomy/runner.py::_actual_model_matches` остаётся проверкой
роли.

## 6. Совместимость и retention

- `RunResult` fields optional/defaults; старые fake runners работают.
- `.autonomy/invocations.jsonl` отсутствует у старых state — агрегатор
  возвращает пустой результат.
- `read_invocations` пропускает повреждённые строки; `include_corrupt`
  возвращает счётчик.
- Retention/удаление не вводятся этим изменением; файл локален и не в Git.
- Секреты/содержимое не хранить; при экспорте — только агрегаты.
