# BA-TOKEN-EFFICIENCY-METRICS — метрики и доказательная база

**Дата:** 2026-11-23  
**Связанный отчёт:** [BA_TOKEN_EFFICIENCY_AUDIT_REPORT.md](BA_TOKEN_EFFICIENCY_AUDIT_REPORT.md)  
**Режим:** read-only; метрики не являются биллингом, если это явно не указано.

## 1. Источники

| Источник | Период | Что даёт | Ограничение |
|---|---|---|---|
| DeepSeek API (owner-provided) | 22–23.11.2026 | Flash/Pro requests, cache hit/miss, output, cost | нет task_id/agent_id/session_id |
| Claude Code JSONL (`~/.claude/projects/...ba`) | 16–23.11.2026 | model, usage, sessionId, tool counts, context size | только локальная машина; не billing; model metadata |
| Git/state | 2026-11-23 | HEAD, clean tree | `.autonomy` отсутствует |
| Code inspection | текущий | prompt/agent/runner paths | статический анализ |

Ключевые ограничения: провайдерская выгрузка и локальные транскрипты — **разные
периоды и машины**. Не смешивать их суммы.

## 2. Провайдерская выгрузка (owner-provided)

| Метрика | Flash | Pro | Итого |
|---|---:|---:|---:|
| Requests | 7 968 | 576 | 8 544 |
| Cache hit tokens | 1 890 338 176 | n/a | — |
| Cache miss tokens | 8 031 088 | n/a | — |
| Output tokens | 3 868 282 | n/a | — |
| Cost | — | — | ≈ $11,75 |
| Avg input/request | 238 249 | n/a | — |
| Avg output/request | 485 | n/a | — |
| Cost/request (arithmetic) | — | — | ≈ $0,001375 |

`n/a` — в выгрузке нет токенов Pro; не выводить их из общей суммы.

## 3. Локальные транскрипты: агрегат

8 JSONL, 77,106,352 bytes; assistant usage entries — 8,942.

| Метрика | Значение |
|---|---:|
| Requests | 8 942 |
| input_tokens | 8 684 309 |
| cache_read_input_tokens | 3 234 696 192 |
| cache_creation_input_tokens | 0 |
| output_tokens | 11 745 201 |
| tool_use | 5 579 |
| tool_result | 5 567 |
| Модель metadata | deepseek-flash 8 940; synthetic 2 |
| Compaction boundaries | 8 (по всем файлам) |

**Важно:** 3,234B cache read — локальные записи, не провайдерские 1,890B.
Период/машина/сессии отличаются; это доказательство структуры расхода, не
сверка счёта.

## 4. Локальные транскрипты: сессии

| Session | Requests | Cache read | Output | Median input/request | Max input/request | Compactions |
|---|---:|---:|---:|---:|---:|---:|
| `2b3837d2-e04` | 3 777 | 1 271 534 080 | 5 823 381 | 294 153 | 752 999 | 4 |
| `5d4c9f64-10e` | 3 874 | 1 593 131 776 | 2 979 867 | 465 559 | 753 265 | 2 |
| `402395a8-d88` | 611 | 234 748 672 | 1 584 458 | 362 145 | 750 776 | 1 |
| `39d90d68-5ed` | 542 | 121 215 232 | 840 124 | 232 269 | 389 403 | 0 |
| `627b1af9-662` | 136 | 19 048 704 | 523 961 | 154 018 | 245 710 | 0 |
| `921dc119-c92` | 2 | 0 | 60 | 13 407 | 13 407 | 0 |
| `ccf7843e-34f` | 2 | 0 | 4 | 12 486 | 12 486 | 0 |
| `6e39a78a-4aa` | 2 | 0 | 0 | 0 | 0 | 0 |

Две крупнейшие сессии:

- **85,56%** всех локальных requests (7 651 / 8 942);
- **88,56%** cache read (2 864 665 856 / 3 234 696 192);
- **74,95%** output (8 803 248 / 11 745 201).

`input/request` = `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`.

## 5. Контекст и tool output

| Session | tool_result count | tool_result chars | Avg chars | Max chars |
|---|---:|---:|---:|---:|
| `2b3837d2-e04` | 2 636 | 4 556 766 | 1 729 | 22 590 |
| `5d4c9f64-10e` | 2 215 | 2 287 259 | 1 033 | 33 510 |
| `402395a8-d88` | 391 | 666 124 | 1 704 | 19 400 |
| `39d90d68-5ed` | 261 | 279 595 | 1 071 | 16 148 |
| `627b1af9-662` | 71 | 229 677 | 3 235 | 17 873 |

Tool results сами по себе не доминируют по объёму, но каждый result остаётся
в истории и повторно отправляется в последующих tool-rounds. В длинной
сессии это часть накопленного 294k–753k контекста.

## 6. Документы, которые читают агенты

| Документ | Chars | ~Tokens (chars/4) | Кто обязан читать |
|---|---:|---:|---|
| `CLAUDE.md` | 11 161 | 2 790 | project instructions |
| `.claude/README.md` | 7 946 | 1 986 | человек/агент по контексту |
| `NOW.md` | 26 822 | 6 705 | architect (mandatory) |
| `PROJECT_STATUS.md` | 67 196 | 16 799 | architect (mandatory) |
| `BACKLOG.md` | 18 248 | 4 562 | architect (mandatory) |
| `OWNER_DECISIONS.md` | 53 950 | 13 487 | architect (mandatory) |
| `TASK_HISTORY.md` | 74 724 | 18 681 | по необходимости |
| `AUDIT_REGISTER.md` | 52 078 | 13 019 | по необходимости |
| `RISK_REGISTER.md` | 32 693 | 8 173 | по необходимости |
| `ADR-APPF-001.md` | 37 990 | 9 497 | по необходимости |

Mandatory architect bundle: **166 216 chars ≈ 41,5k tokens** на один
planning call, без кода и tool output. Оценка токенов приблизительная.

## 7. Per-task / per-agent метрики

Точный учёт **отсутствует**:

- `.autonomy/state.json` отсутствует, поэтому нет task attempts/usage;
- в провайдерской выгрузке нет task_id/agent_id/session_id;
- `RunResult`/`StateStore` не сохраняют request_count, cache hit/miss;
- локальные транскрипты не содержат task_id и не соответствуют billing
  периоду.

| Метрика | Flash | Pro | Всего |
|---|---:|---:|---:|
| API requests/task | N/A | N/A | N/A |
| Cache hit/task | N/A | N/A | N/A |
| Cache miss/task | N/A | N/A | N/A |
| Output/task | N/A | N/A | N/A |
| Cost/task | N/A | N/A | N/A |
| Retry calls/task | N/A | N/A | N/A |
| Tasks without progress | N/A | N/A | N/A |
| Cost/accepted task | N/A | N/A | N/A |

`metrics.py` умеет считать `tokens_per_accepted_task` и
`cost_usd_per_accepted_task`, но только при наличии state; сейчас state нет.
`repeated_file_reads` явно помечен `not_available_from_cli_json`.

## 8. Модель/маршрутизация

- Локальные metadata: 8 940 Flash requests, 0 Pro; провайдер: 576 Pro.
- Это **не** доказывает неправильную маршрутизацию: Pro-вызовы могли идти
  на другом ПК/в removed worktree.
- `autonomy/runner.py` назначает Pro для architect/reviewer и Flash для
  developer/QA; проверка `_actual_model_matches` есть, но evidence
  отсутствует.
- Для аудита нужен per-agent `modelUsage` + provider correlation.

## 9. Что нужно мерить (целевая схема)

На каждый model request/role invocation сохранять **без prompt content**:

```text
task_id, agent_id, session_id, role, model,
request_count, prompt_cache_hit_tokens, prompt_cache_miss_tokens,
completion_tokens, reasoning_tokens (если доступно),
estimated_cost, retry_count, task_status, accepted_result,
started_at, finished_at
```

Источники: `autonomy/runner.py` (`RunResult`, `_write_evidence`),
`autonomy/state.py` (`Task.usage`, `record_usage`), `autonomy/metrics.py`,
Claude Code JSON (`modelUsage`/usage), при необходимости — контролируемый
прокси провайдера. API-ключи, заголовки и prompt content не логировать.

## 10. Вывод по метрикам

Метрики подтверждают **концентрацию расхода в нескольких длинных сессиях**
и отсутствие task-level атрибуции. Провайдерские средние 238k input/request
совместимы с локальными median 294k/465k у двух длинных сессий, но точная
связь с 7 968/576 запросами без task correlation не доказана.
