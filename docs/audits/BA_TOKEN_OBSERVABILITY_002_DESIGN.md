# BA-TOKEN-OBSERVABILITY-002 — проектирование учёта failed/timeout/cancelled/interrupted invocations

**Дата:** 2026-11-23  
**Статус:** **APPROVED / IMPLEMENTED (2026-11-23)** — согласовано владельцем,
реализация и evidence — `docs/audits/BA_TOKEN_OBSERVABILITY_002_IMPLEMENTATION_REPORT.md`.  
**Основа:** BA-TOKEN-OBSERVABILITY-001 (`autonomy/observability.py`,
`.autonomy/invocations.jsonl`, `usage_source=claude_code`).  
**Ограничение:** документ описывает согласованный scope; архитектурные
расширения сверх §13 не выполнялись.

## 1. Текущие пробелы

### 1.1. Учёт только успешных запусков

`autonomy/runner.py::ClaudeRunner.run` создаёт `invocation_id`, вызывает
`claude -p` и возвращает `RunResult` только при успехе. Все остальные исходы
завершаются исключением:

| Исход | Код | Что происходит сейчас |
|---|---|---|
| timeout | `runner.py:130-131` | `subprocess.TimeoutExpired` → `RunnerError`; `RunResult` нет, evidence нет, в JSONL ничего |
| API error / non-zero exit | `runner.py:170-171` | evidence уже записан (обычно с `modelUsage`; crash может обнулить cost), но `RunResult` нет; `_account` не вызывается |
| невалидный JSON | `runner.py:192-210` | `RunnerError` до evidence; usage неизвестен |
| model mismatch | `runner.py:172-173` | evidence записан, usage известен; `RunResult` нет |
| Ctrl+C | `runner.py:121-129` | `KeyboardInterrupt` (BaseException) проходит мимо `except Exception` в orchestrator; terminal-записи нет |
| SIGTERM / SIGKILL / падение VPS | — | процесс исчезает; стартовой записи тоже нет, потому что она не пишется |
| ошибка запуска (`OSError`) | `runner.py:121` | исключение; ничего не записано |

`autonomy/orchestrator.py::_account` (`orchestrator.py:412-438`) вызывается
только после успешного возврата `RunResult`. Поэтому расход неуспешного
запуска не виден ни в `state.json`, ни в `invocations.jsonl`.

### 1.2. Нет стартовой записи

`invocations.jsonl` сейчас содержит только terminal-записи успешных
invocations (`observability.py:134-144`). Если процесс умер до возврата
`RunResult`, от запуска не остаётся ничего. Нельзя отличить «не запускался»
от «запускался и умер».

### 1.3. Recovery не связан с наблюдаемостью

`StateStore.recover_running` (`state.py:430-449`) возвращает RUNNING/QA/REVIEW
в READY/BLOCKED, но не знает, какие именно model invocations были активны.
`orchestrator._run_once` вызывает его на старте (`orchestrator.py:631`), после
чего задача может быть перезапущена — при этом старый расход остаётся
неучтённым.

### 1.4. Что уже есть и можно переиспользовать

- `invocation_id` генерируется в runner (`runner.py:118`) и попадает в
  `RunResult` и evidence.
- `task_id`/`attempt_id`/`retry_count` уже передаются в `_account`
  (`orchestrator.py:678-684` и др.), но только на успехе.
- JSONL append + fsync + дедупликация по `invocation_id` уже реализованы
  (`observability.py:134-166`, `177-290`).
- `usage_known`/`request_count_known` пока отсутствуют; `request_count`
  остаётся `None`, если CLI его не отдал.
- `state.json` уже хранит `runs[]` со статусом `started` и usage
  (`state.py:255-263`), но это task-run, а не invocation, и usage туда
  попадает только через успешный `record_usage`.

## 2. Изучение готовых практик

### 2.1. Claude Code hooks (официальная документация)

Проверены события, указанные в задании, по официальному справочнику
(https://code.claude.com/docs/en/hooks) и по встроенному справочнику
установленной версии CLI **2.1.329** (встроенный каталог содержит 33
события, включая `SessionEnd`, `StopFailure`, `SubagentStop`,
`PostToolUseFailure`).

| Событие | Когда срабатывает | Вход | Применимость к нашему `claude -p --agent` | Даёт token usage? |
|---|---|---|---|---|
| `SessionStart` | старт сессии; matchers `startup`, `resume`, `clear`, `compact`, `fork` | session_id, transcript_path, cwd, source | Да, сессия создаётся и в print mode | Нет |
| `SessionEnd` | завершение сессии; matchers `clear`, `resume`, `logout`, `prompt_input_exit`, `other` | session_id, transcript_path, cwd, reason | Документирован для SIGTERM (CLI завершает дерево Bash-команд и запускает SessionEnd); при SIGKILL не документирован и не гарантирован | Нет |
| `Stop` | перед нормальным завершением ответа | session_id, transcript_path, last_assistant_message | Срабатывает на turn, а не на процесс; не является границей invocation при tool-loop | Нет |
| `StopFailure` | turn завершился из-за ошибки API; «fires instead of Stop»; fire-and-forget, exit code игнорируется | `error` (enum: `rate_limit`, `authentication_failed`, `oauth_org_not_allowed`, `account_on_hold`, `billing_error`, `invalid_request`, `model_not_found`, `server_error` — сюда маппится HTTP 529, `max_output_tokens`, `cloud_credential_error`, `unknown`), `error_details`, `last_assistant_message` | Да, но только классификация ошибки; на SIGTERM, по документации, выполняется только `SessionEnd`; при SIGKILL не документирован | Нет |
| `SubagentStop` | завершение subagent, созданного через Agent tool | agent_id, agent_type, agent_transcript_path | Для top-level `--agent` **не документирован**; наши роли — не Agent-tool subagent | Нет |
| `PostToolUseFailure` | ошибка отдельного tool call | tool_name, tool_input, tool_use_id, error, is_interrupt | Нет: это tool-level, не invocation; не отражает расход модели | Нет |

Вывод: hooks полезны как дополнительная классификация ошибок, но **не
закрывают главный пробел — token usage при timeout/cancel/interrupted**.
Ни одно из событий не передаёт `usage`/`modelUsage`; `last_assistant_message`
и `error_details` — это content, который запрещено сохранять. Добавление
hooks требует менять settings/конфигурацию дочернего процесса и добавлять
hook-скрипты (см. §3, вариант B), то есть расширяет security surface без
выигрыша в точности учёта.

Для нашего способа запуска (`claude -p --agent`, top-level agent)
практически применимы только `SessionEnd` и `StopFailure` как
дополнительные сигналы; `SubagentStop` относится к Agent-tool subagents, а
`PostToolUseFailure` — к отдельным tool calls, поэтому для учёта invocation
они не подходят.

Документация прямо подтверждает, что `-p`-сессия выполняет hooks из
`.claude/settings.json` проекта (даже в недоверенной папке), поэтому наши
существующие `PreToolUse`-guard'ы работают и в autonomy-child. Исключения:
`--bare`, `--safe-mode`, `--setting-sources`, `disableAllHooks` и
`allowManagedHooksOnly`. Любая схема, завязанная на hooks, становится
хрупкой при изменении флагов запуска.

### 2.2. Интерактивные сессии и Dev Control (вне scope этого этапа)

Предыдущий аудит показал, что интерактивные/CLI-сессии — крупный источник
расхода. На этом этапе они **не собираются** и **не смешиваются** с
`claude -p` orchestrator:

- `devcontrol` уже запускает `claude --bg` (`devcontrol/claude.py:181-237`)
  и имеет `SessionEnd` hook (`devcontrol/hooks/on_session_end.py`), который
  фиксирует только причину завершения и IDLE, без usage;
- `claude agents --json` даёт session id/pid/cwd, но не token usage;
- будущий отдельный этап может использовать `SessionStart`, `SessionEnd`,
  `StopFailure` и `transcript_path` из hook input; однако формат транскрипта
  не является стабильным публичным API, файл пишется асинхронно и может
  отставать от conversation к моменту hook, `--no-session-persistence` может
  его отключить, а разбор несёт риск захвата content. Точный provider usage
  всё равно потребует gateway/usage API;
- до появления такого этапа интерактивные сессии остаются в транскриптах и
  provider billing, а не в `by_task`/`accepted_cost_usd`.

### 2.3. OpenTelemetry: lifecycle и ошибки

OTel рекомендует:

- рассматривать invocation как span: начало фиксируется при создании,
  окончание — явным `end()`; без `end()` span не экспортируется;
- при ошибке выставлять статус `Error` и атрибут `error.type`, не подменяя
  успех «нулевыми» значениями;
- не записывать чувствительное содержимое (prompt/response) в атрибуты;
- для GenAI использовать отдельные атрибуты usage, при этом
  `gen_ai.usage.input_tokens` у разных провайдеров может включать или не
  включать cached tokens — источник и семантика должны быть явными.

Отдельно проверена документированная телеметрия самого Claude Code
(https://code.claude.com/docs/en/monitoring-usage): события
`claude_code.api_request` несут `input_tokens`, `output_tokens`,
`cache_read_tokens`, `cache_creation_tokens`, `cost_usd`, а token/cost
counters инкрементируются после каждого API-запроса. Это единственный
документированный per-request источник, но: (а) события `api_error` не
содержат token/cost; (б) экспорт OTel обычно батчируется и при SIGKILL
может быть потерян; (в) включение требует env/коллектора, то есть
изменения окружения/инфраструктуры, и не даёт task correlation. Поэтому
этот путь не используется на данном этапе, но остаётся кандидатом для
точного provider-учёта в будущем.

Наша модель — «span + durable journal»: start пишется до запуска, terminal —
в `finally`/ветках ошибок; если процесс умер, span остаётся незакрытым и
восстанавливается отдельным reconciliation-проходом, при этом usage не
выдумывается.

### 2.4. Практика durable-журналов

Стандартный паттерн: append-only event log с двумя типами событий
(`started`/`finished`), идемпотентная дедупликация по id и периодическая
реконсиляция «висящих» started-записей по признаку живости процесса/хоста.
Именно этот паттерн рекомендуется ниже.

## 3. Сравнение вариантов

| Вариант | Покрытие | Точность usage | Сложность/риск | Решение |
|---|---|---|---|---|
| **A. Journal в runner + reconciliation** (рекомендуется) | success, API error, invalid output, model mismatch, launch error, timeout, SIGINT, crash/SIGKILL/VPS (inferred) | точный, когда CLI вернул JSON; `unknown` иначе | малая; нет hooks, нет новых процессов; меняется только runner/observability + контекст из orchestrator | **Принять** |
| B. Hooks (`SessionEnd`/`StopFailure`) | добавляет причину завершения/ошибку API | **не даёт usage**; при SIGKILL не срабатывает | средняя: settings/hook-скрипты, security surface, влияние на все сессии | Отклонить на этом этапе |
| C. Парсинг транскриптов Claude Code | потенциально usage даже при сбое | формат не является стабильным публичным API; риск захвата content; гонки с параллельными сессиями | высокая | Отклонить; только исследовать для interactive-этапа |
| D. Provider gateway / usage API | все запросы, включая оборванные | точный provider usage/cache/request_count | высокая: transport-layer, VPS/архитектура | Вне scope; единственный путь к точному provider attribution |
| E. Замена `subprocess.run` на `Popen` | добавляет child pid и ручное управление kill | не меняет точность usage | средняя: меняет process lifecycle | Не требуется для A; оставить как отдельное решение |
| F. Встроенная OTel-телеметрия Claude Code | per-request `api_request` события и counters | потенциально точный, но `api_error` без tokens; батч может потеряться при SIGKILL | средняя/высокая: env, collector/export, нет task correlation | Не сейчас; кандидат на отдельный этап точного provider-учёта |

Вариант A минимален: он не меняет маршрутизацию моделей, число агентов,
планирование, бюджеты, permissions, VPS/Docker/systemd и не добавляет
фоновых процессов. Reconciliation выполняется opportunistically на старте
существующего `run`/`recover`, без scheduler.

### 3.1. Почему не hooks

1. Ни `SessionEnd`, ни `StopFailure` не содержат usage/cost.
2. `SessionEnd` документирован для SIGTERM, но не для SIGKILL/OOM/падения
   VPS — то есть именно в аварийных сценариях, ради которых задача и
   делается. Python `subprocess.run(timeout=...)` убивает child через
   SIGKILL, поэтому на нашем timeout SessionEnd не сработает.
3. `SubagentStop` не документирован для top-level `--agent`; это событие
   Agent-tool subagents.
4. `PostToolUseFailure` — tool-level шум, не граница invocation.
5. Подключение hooks требует менять конфигурацию дочернего процесса
   (`--settings`/project settings) и добавлять исполняемые скрипты — это
   изменение security-поверхности, запрещённое без отдельного одобрения.
6. `--bare` отключает hooks; схема стала бы зависеть от флагов запуска.

## 4. Рекомендуемая lifecycle-модель

```
                 +-------------------+
   spawn intent  |  started (pending)|  start event записан до subprocess
                 +---------+---------+
                           |
        +------------------+-------------------+------------------+
        |                  |                   |                  |
   returncode 0      returncode!=0       TimeoutExpired      KeyboardInterrupt
   is_error=false    или is_error=true    (watchdog kill)    (SIGINT, child killed)
        |                  |                   |                  |
      ok              failed (api_error)     timeout           cancelled
        |             invalid_output             |                  |
        |             model_mismatch             |                  |
        |             launch_error               |                  |
        +------------------+-------------------+------------------+
                           |
                  terminal event (finished)
                           |
        если terminal не появился, а процесс/хост умер:
                  reconcile → interrupted (inferred)
        если terminal не появился и живость не подтверждается:
                  reconcile → unknown/abandoned (inferred)
```

Определения:

- **started (pending)** — start-запись есть, terminal нет, владелец
  (orchestrator pid) жив и не превышен stale-порог. Это не terminal-статус;
  в отчётах показывается отдельно (`pending_invocations`).
- **ok** — процесс завершился с `returncode == 0`, `is_error` ложен, модель
  соответствует ожидаемой.
- **failed** — процесс завершился (exit code известен), но:
  `api_error` (non-zero/is_error), `invalid_output` (не JSON/не объект),
  `model_mismatch`, `launch_error` (не удалось запустить процесс).
- **timeout** — наш watchdog прервал процесс по `subprocess.TimeoutExpired`;
  `exit_code` неизвестен (процесс убит), `usage_known=false`.
- **cancelled** — оператор прервал invocation (SIGINT/KeyboardInterrupt);
  процесс убит `subprocess.run`; `usage_known=false`.
- **interrupted** — terminal-запись отсутствует, но установлено, что
  владелец/хост умер: pid мёртв, pid переиспользован или `boot_id`
  изменился. `inferred=true`; `finished_at`/`duration` неизвестны.
- **unknown/abandoned** — terminal нет, живость подтвердить нельзя, возраст
  превысил stale-порог. `inferred=true`; ничего не выдумывается.

Retry: каждый новый вызов — новый `invocation_id`; `attempt_id` (task.run_id)
может повторяться у developer/qa/reviewer одной попытки; `retry_count`
показывает номер повторной попытки. Двойного учёта нет: invocation
учитывается один раз по `invocation_id`.

## 5. Схема хранения событий

### 5.1. Формат

Один append-only JSONL — `.autonomy/invocations.jsonl` (тот же файл, что и
сейчас). Два типа записей, различаемых полем `event`:

- `invocation_started` — метаданные до запуска;
- `invocation_finished` — terminal-запись (успех или ошибка).

Старые записи без `event` считаются `invocation_finished` со
`status="ok"` и `usage_known=true`; если в legacy-записи уже стоит
`status="error"`, он нормализуется в `failed`. Это обеспечивает чтение
существующего файла без миграции.

### 5.2. `invocation_started`

```json
{
  "schema_version": 2,
  "event": "invocation_started",
  "invocation_id": "uuid",
  "task_id": "AUTONOMY-X",
  "attempt_id": "task-run-uuid",
  "agent_id": "autonomy-developer",
  "role": "developer",
  "model": "deepseek-flash[1m]",
  "execution_channel": "orchestrator",
  "retry_count": 0,
  "started_at": "2026-11-23T12:00:00+00:00",
  "owner_pid": 12345,
  "owner_pid_start_ticks": 987654,
  "boot_id": "host-boot-uuid",
  "host": "hostname",
  "usage_source": "claude_code"
}
```

`owner_pid` — pid процесса, который вызвал runner (orchestrator), а не pid
`claude` (при `subprocess.run` дочерний pid недоступен; см. §13). Поля
`pid`/`boot_id` — только метаданные, не секреты.

### 5.3. `invocation_finished`

Расширяет текущую схему BA-TOKEN-OBSERVABILITY-001:

```json
{
  "schema_version": 2,
  "event": "invocation_finished",
  "invocation_id": "uuid",
  "task_id": "AUTONOMY-X",
  "attempt_id": "task-run-uuid",
  "agent_id": "autonomy-developer",
  "role": "developer",
  "session_id": "claude-session-id",
  "model": "deepseek-flash[1m]",
  "reported_models": ["deepseek-flash[1m]"],
  "execution_channel": "orchestrator",
  "status": "ok",
  "error_type": null,
  "exit_code": 0,
  "is_error": false,
  "inferred": false,
  "usage_known": true,
  "request_count": null,
  "request_count_known": false,
  "num_turns": 4,
  "input_tokens": 12,
  "cache_hit_tokens": 100,
  "cache_miss_tokens": 16,
  "output_tokens": 3,
  "reasoning_tokens": null,
  "estimated_cost_usd": 0.04,
  "started_at": "2026-11-23T12:00:00+00:00",
  "finished_at": "2026-11-23T12:01:40+00:00",
  "duration_seconds": 100.2,
  "reconciled_at": null,
  "retry_count": 0,
  "accepted_result": null,
  "usage_source": "claude_code",
  "provider_request_count": null,
  "provider_cache_hit_tokens": null,
  "provider_cache_miss_tokens": null
}
```

Правила:

- `usage_known=false` ⇒ все token/cost-поля **null**, не `0`. Это главное
  отличие от текущей схемы, где int-поля по умолчанию 0. При
  `usage_known=true` `reasoning_tokens` всё равно может быть `null`, если
  CLI не отдаёт reasoning.
- `request_count_known` — явный boolean; `request_count` заполняется только
  если CLI реально вернул int. `num_turns` не подменяет request count.
- `exit_code` — только для завершившегося процесса; для timeout/cancel —
  `null`.
- `duration_seconds` — измеренное monotonic-время до terminal-события; для
  `interrupted`/`unknown` — `null` (нельзя знать, когда процесс умер).
- `reconciled_at` — время обнаружения, не время смерти; заполняется только
  для inferred-записей.
- `accepted_result` остаётся `null` на invocation; acceptance — join с
  `StateStore` (COMPLETED) при агрегации.

### 5.4. `status` и `error_type` (закрытые enum)

Terminal `status`: `ok`, `failed`, `timeout`, `cancelled`, `interrupted`,
`unknown`; `started`/pending — производное состояние, в terminal-записи не
пишется.

`error_type`: `api_error`, `invalid_output`, `model_mismatch`,
`launch_error`, `timeout`, `operator_interrupt`, `orchestrator_gone`,
`host_reboot`, `pid_reused`, `abandoned_unknown`. Сырой stderr/error text, `last_assistant_message`,
`error_details` и любые фрагменты prompt/response **не сохраняются**.

### 5.5. Примеры terminal-записей

Timeout:

```json
{
  "event": "invocation_finished",
  "status": "timeout",
  "error_type": "timeout",
  "exit_code": null,
  "usage_known": false,
  "input_tokens": null,
  "cache_hit_tokens": null,
  "cache_miss_tokens": null,
  "output_tokens": null,
  "reasoning_tokens": null,
  "estimated_cost_usd": null,
  "finished_at": "2026-11-23T12:15:00+00:00",
  "duration_seconds": 900.0
}
```

Interrupted (reconciliation):

```json
{
  "event": "invocation_finished",
  "status": "interrupted",
  "error_type": "host_reboot",
  "exit_code": null,
  "usage_known": false,
  "inferred": true,
  "finished_at": null,
  "duration_seconds": null,
  "reconciled_at": "2026-11-23T13:00:00+00:00"
}
```

## 6. Обработка timeout, exception, cancellation и crash recovery

### 6.1. Где пишутся события

Все lifecycle-события пишет `ClaudeRunner.run` — единственное место, где
известны точные границы subprocess. Orchestrator передаёт
`InvocationContext(task_id, attempt_id, retry_count)`; runner генерирует
`invocation_id` и пишет:

1. `invocation_started` — до `subprocess.run`;
2. ровно один `invocation_finished` — в success/failure/timeout/cancel
   ветках (флаг `finished_written`, без `finally`-дубля);
3. evidence — после terminal-записи (чтобы сбой evidence не потерял usage).

`_account` в orchestrator перестаёт писать JSONL (иначе будет два terminal
на один `invocation_id`); он продолжает обновлять `state.usage` и budget
tracker только для успешных `RunResult`, как сейчас. Budget-политика не
меняется.

### 6.2. Timeout

`subprocess.run(timeout=...)` при истечении убивает child и поднимает
`TimeoutExpired` (проверено по `subprocess.py` Python 3.14). Runner:

- фиксирует `status="timeout"`, `error_type="timeout"`, `exit_code=null`,
  `finished_at` = момент kill, `duration_seconds` = фактическое время;
- `usage_known=false` (JSON-результат не получен);
- переподнимает прежний `RunnerError`, поведение orchestrator не меняется.

### 6.3. API error / non-zero exit / invalid output / model mismatch

- если stdout распарсился в JSON: API-error результат CLI документированно
  содержит `usage`/`modelUsage`/`total_cost_usd`; terminal пишется с
  `status="failed"`, `error_type="api_error"` (или `model_mismatch`).
  `usage_known=true` только при непустом `modelUsage` хотя бы с одним
  ненулевым token-значением. Документированное исключение —
  `error_during_execution` после аварии сессии может обнулять cost-поля;
  такие нули не считаются точными (`usage_known=false`). При обрыве
  соединения/процесса result message может вообще отсутствовать;
- если JSON нет/невалиден: `status="failed"`,
  `error_type="invalid_output"`, `usage_known=false`, токены `null`;
- evidence пишется как раньше (для API error — с usage), после terminal;
- исключение `RunnerError` переподнимается без изменения текста/типа.

### 6.4. Cancellation (SIGINT)

`KeyboardInterrupt` — `BaseException`, поэтому существующий
`except Exception` его не ловит. Runner добавляет отдельный
`except KeyboardInterrupt`: пишет `status="cancelled"`,
`error_type="operator_interrupt"`, `usage_known=false`, затем **переподнимает**
исключение. `subprocess.run` уже убивает child при `KeyboardInterrupt`
(проверено по исходнику Python 3.14), поэтому orphan-child в этом сценарии
не создаётся. Orchestrator и task state ведут себя как раньше
(`recover_running` на следующем старте).

SIGTERM/SIGKILL: обработчик не добавляется (это изменило бы shutdown-
поведение). Такой запуск останется `started` и будет классифицирован как
`interrupted` при reconciliation. Отличать «остановку оператором» от
«аварии» без SIGTERM-обработчика невозможно — это осознанное ограничение
(см. §13).

### 6.5. Crash recovery / незавершённые запуски

Функция `reconcile_invocations(root, ...)`:

1. читает журнал, строит множество `invocation_id` с terminal-записью;
2. для каждого `started` без terminal:
   - `boot_id` в записи ≠ текущий `boot_id` → `interrupted`, `error_type=host_reboot`;
   - `owner_pid` не существует или его `starttime` не совпадает с записанным
     (PID reuse) → `interrupted`, `error_type=orchestrator_gone`/`pid_reused`;
   - `owner_pid` жив → invocation считается in-flight; terminal не пишется;
   - живость проверить нельзя и возраст > stale-порога →
     `unknown`, `error_type=abandoned_unknown`, `inferred=true`;
3. пишет inferred terminal-записи идемпотентно: повторный проход видит
   terminal и ничего не добавляет; при гонке с реальным terminal
   authoritative-запись имеет приоритет (см. §7).

Где вызывается (без нового scheduler):

- `Orchestrator._run_once` после `store.recover_running()`
  (`orchestrator.py:631`) — best-effort, ошибки подавляются;
- CLI `python -m autonomy.orchestrator recover` — после `recover_running`;
- при необходимости — вручную `python -m autonomy.observability reconcile`
  (новая функция/точка входа, без фонового процесса).

Stale-порог по умолчанию: `2 * BA_MODEL_TIMEOUT + 300` секунд
(для 900 с → 2100 с), настраивается env; применяется только когда
pid/boot-проверка недоступна. Живой процесс раньше порога не трогается.

## 7. Дедупликация и защита JSONL

### 7.1. Запись

- Lock-файл `.autonomy/invocations.lock` + `fcntl.flock(LOCK_EX)` только на
  время append (не на весь invocation). Сериализует редкие конкурентные
  записи (`run` держит RUN_LOCK, но `propose` — нет: `orchestrator.py:1019`).
- Одна строка = `json.dumps(...) + "\n"`, один `os.write` в
  `O_APPEND|O_CREAT|O_WRONLY` (0600), затем `fsync`.
- Ошибка записи журнала подавляется и **не влияет** на task outcome; при
  этом start-запись могла остаться → reconciliation позже пометит
  interrupted (честная деградация, без падения задачи).
- Ротация/удаление не вводятся (деструктивные операции без решения
  владельца). Оценка роста: ~2 записи × 1–2 КБ на invocation; 3 роли на
  задачу → ~6–12 КБ/задача.

### 7.2. Чтение и частичные записи

- `read_invocations` продолжает пропускать невалидные строки; последняя
  строка без завершающего `\n` считается частичной и пропускается
  (`partial_tail`), чтобы обрыв записи не создал «валидную» неполную
  terminal-запись.
- `include_corrupt` сохраняется как диагностический маркер.

### 7.3. Дедупликация и приоритет

Ключ — `invocation_id` + тип события:

- duplicate `invocation_started` → первая запись выигрывает;
- duplicate `invocation_finished`:
  - authoritative (не inferred) выигрывает у inferred;
  - среди authoritative — первая запись;
  - среди inferred — первая;
- legacy-запись без `event` — authoritative `finished`;
- `finished` без `started` учитывается (совместимость и поздние записи);
- `started` без `finished` — pending, не входит в accepted cost.

Это исключает двойной учёт при повторной обработке и при гонке
reconcile/реального terminal.

### 7.4. Агрегация

`summarize` дополняется:

- `by_status` (ok/failed/timeout/cancelled/interrupted/unknown/pending);
- `usage_known_invocations`, `usage_unknown_invocations`,
  `pending_invocations`, `inferred_invocations`;
- `request_count_known` уже есть в totals/buckets;
- accepted cost считается только по известному usage;
  `accepted_cost_unknown_usage_invocations` показывает, у скольких
  invocations принятых задач usage неизвестен. Неизвестное **не**
  заменяется нулём и не экстраполируется.

## 8. Изменения в конкретных файлах и функциях

### 8.1. `autonomy/observability.py`

- Константы: `SCHEMA_VERSION = 2`, `STARTED_EVENT`, `FINISHED_EVENT`,
  `TERMINAL_STATUSES`, `ERROR_TYPES`.
- `InvocationContext` (frozen dataclass: task_id, attempt_id, retry_count).
- `InvocationStart` (frozen dataclass: все поля §5.2).
- `InvocationMetrics` расширяется nullable-полями `event`, `schema_version`,
  `status`, `error_type`, `exit_code`, `duration_seconds`, `usage_known`,
  `request_count_known`, `inferred`, `reconciled_at`; token-поля становятся
  `int | None`. Существующий `from_run_result` заполняет их для успеха;
  добавляется `from_failure(...)`.
- `record_started(root, start)`, `record_finished(root, metrics)`;
  `record_invocation` становится алиасом `record_finished` для совместимости.
- `_append_record(root, payload)` — lock + O_APPEND + fsync.
- `read_invocations` — пропуск partial tail; API сохраняется.
- `reconstruct_invocations(records)` — слияние start/finish по правилам §7.3.
- `reconcile_invocations(root, *, now=None, current_boot_id=None,
  pid_probe=None, stale_after_seconds=None)` — §6.5; probes инъектируются
  для тестов.
- `summarize` — расширение §7.4; существующие ключи и поведение для legacy-
  записей сохраняются.

### 8.2. `autonomy/runner.py`

- `ClaudeRunner.__init__(..., journal_root: Path | None = None)`; по
  умолчанию `self.root / ".autonomy"`.
- `run(..., context: InvocationContext | None = None)`; role-обёртки
  (`architect/developer/qa/reviewer`) получают optional `context` и передают
  его в `run`.
- `run`:
  - генерирует `invocation_id` и `started_at` (уже есть);
  - пишет `record_started` до `subprocess.run`, с `owner_pid`,
    `owner_pid_start_ticks`, `boot_id`, `host`;
  - оборачивает `subprocess.run` в `except TimeoutExpired`,
    `except KeyboardInterrupt`, `except OSError/Exception` (переподнимая
    исходное исключение после terminal-записи);
  - после парсинга payload определяет `status`/`error_type`/`usage_known` и
    пишет `record_finished` до `_write_evidence`;
  - `RunResult` не меняется (поля уже есть); исключения и их тексты не
    меняются.
- Вспомогательные `_boot_id()`, `_pid_start_ticks(pid)` (Linux `/proc`,
  best-effort, `None` при недоступности).

### 8.3. `autonomy/orchestrator.py`

- Импорт `InvocationContext`, `reconcile_invocations`.
- `_run_once`: `reconcile_invocations(journal_root)` после
  `recover_running` (в `contextlib.suppress`, не влияет на task), где
  `journal_root = getattr(self.runner, "journal_root", self.store.root)`,
  чтобы state и журнал указывали на один каталог.
- CLI `recover`: тот же вызов.
- Все вызовы ролей получают `context=InvocationContext(task_id=task.id,
  attempt_id=task.run_id, retry_count=max(0, task.attempts - 1))`;
  architect — `InvocationContext()` (task_id=None).
- `_account` больше не пишет JSONL (единственный писатель — runner);
  `record_usage`/`tracker.add` сохраняются без изменений.
- `main()`: `ClaudeRunner(journal_root=store.root)` явно, чтобы state и
  journal совпадали.

### 8.4. Файлы без изменений

- `autonomy/state.py` — схема state не меняется; `recover_running` остаётся
  как есть.
- `autonomy/budget.py` — без изменений; failed usage не попадает в budget.
- `autonomy/sandbox.py` — без изменений; hooks/env не добавляются.
- `.claude/settings.json`, `devcontrol/claude-settings.json` — без изменений.
- Миграции/БД/Docker/VPS/systemd — не затрагиваются.

### 8.5. Изменяемые тесты (механически)

Fake runners в `tests/unit/test_autonomy.py`,
`tests/unit/test_autonomy_budget.py`,
`tests/integration/test_autonomy_worktree.py` получают optional `context`
(или `**kwargs`); тест `test_orchestrator_account_records_task_and_attempt`
заменяется runner-level тестом, так как JSONL теперь пишет runner.

## 9. План тестирования

### 9.1. Unit: runner lifecycle

1. start пишется до вызова subprocess (fake проверяет наличие записи).
2. success → ровно один finished, `status=ok`, usage token-поля int.
3. API error с JSON → finished `failed/api_error`, usage известен,
   `RunnerError` поднят, evidence записан.
4. API error без JSON → `failed/invalid_output`, токены `null`,
   `usage_known=false`.
5. `TimeoutExpired` → `timeout/timeout`, duration>0, токены `null`,
   `RunnerError`.
6. `KeyboardInterrupt` → `cancelled/operator_interrupt`, исключение
   переподнято, `usage_known=false`.
7. `OSError` при spawn → `failed/launch_error`, исключение переподнято.
8. model mismatch → `failed/model_mismatch`, usage известен.
9. сбой записи evidence после terminal → finished уже есть, task outcome
   не изменён.
10. сбой журнала не ломает invocation (runner возвращает/бросает как без
    журнала).
11. в start/finished нет prompt/response/secret (маркеры `"secret"`,
    `"password"`, текст prompt).
12. `request_count` отсутствует → `null` + `request_count_known=false`;
    `num_turns` не превращается в request count.

### 9.2. Unit: агрегация и совместимость

13. legacy-записи (без `event`) читаются как ok/usage_known, старые тесты
    проходят.
14. started+finished → одна invocation, terminal usage.
15. duplicate authoritative → first wins.
16. inferred, затем authoritative → authoritative wins.
17. finished без started → учитывается.
18. started без finished → pending, не в accepted cost.
19. unknown usage не суммируется как 0; счётчики known/unknown корректны.
20. corrupt/partial tail: невалидная последняя строка без `\n` не
    становится invocation.
21. пустой/отсутствующий журнал → пустой отчёт.

### 9.3. Unit: reconciliation

22. owner pid мёртв → interrupted/orchestrator_gone; повторный reconcile
    идемпотентен.
23. boot_id изменился → interrupted/host_reboot.
24. owner pid жив → pending, terminal не пишется.
25. PID reuse (starttime не совпал) → interrupted/pid_reused.
26. нет pid/boot, возраст > порога → unknown/abandoned_unknown.
27. гонка: reconcile пишет inferred, затем реальный terminal →
    authoritative выигрывает при агрегации.
28. reconcile во время активного `propose` (pid жив) не помечает его
    interrupted.

### 9.4. Integration/failure scenarios

29. дочерний процесс пишет synthetic start и делает `os._exit(1)` → на
    следующем reconcile interrupted, usage неизвестен.
30. SIGKILL симулируется через мёртвый pid/boot_id (без реального kill в
    тестах); отдельный integration-тест может убить тестовый child.
31. failed invocation не меняет `state.usage`/budget (явная проверка), но
    виден в journal.
32. orchestrator retry/blocked после failed developer остаётся прежним
    (регрессия существующих тестов).
33. конкурентные writers (N потоков/процессов) → все строки валидны,
    ровно N записей, без interleaving.

### 9.5. Регрессия

- `tests/unit/test_autonomy_observability.py` (8 тестов) — обновить под
  расширенную схему, сохранив старые сценарии.
- `tests/unit/test_autonomy_security.py` — argv/evidence не изменились.
- `tests/unit/test_autonomy_budget.py` — budget behavior не изменился.
- Полный `pytest --create-db`; ruff/format/mypy.

Аварийные сценарии тестируются без реальных API-вызовов: fake subprocess,
synthetic journal records, инъекция `boot_id`/`pid_probe`, один
subprocess-crash тест. Массовые API-эксперименты не требуются.

## 10. Риски и ограничения

1. **Usage при timeout/cancel/interrupted неизвестен** — provider не отдал
   JSON (SIGTERM, по документации, не создаёт result; SIGKILL — тем более).
   API-error JSON, наоборот, обычно содержит usage, и это будет учтено.
   Hooks не исправляют пробел; Claude Code OTel `api_request` — единственный
   документированный per-request источник, но не внедряется сейчас
   (вариант F). Точный provider attribution — только gateway/usage API
   (вариант D).
2. **SIGKILL orchestrator может оставить child `claude` живым** (ОС не
   убивает детей автоматически). Parent-pid детектирует смерть
   orchestrator, но не судьбу child; расход child может остаться
   неучтённым. `Popen` с child pid улучшил бы диагностику, но не даёт
   usage. Автоматическое убийство orphan-child — деструктивно, требует
   отдельного решения.
3. **SIGTERM не классифицируется как cancelled** без signal handler;
   будет interrupted. Добавление handler меняет shutdown-поведение.
4. **Budget/state не учитывают failed usage** (политика не меняется);
   journal показывает больше, чем state/budget. Единый источник истины по
   фактическому расходу — журнал; state usage остаётся success-only
   budget-учётом. Это осознанное расхождение.
5. **Запись журнала может не удаться** (диск, права); start останется без
   terminal и будет помечен interrupted — статус может быть неточным, но
   двойного учёта нет.
6. **Рост файла** без ротации; оценка в §7.1; удаление/ротация — отдельное
   решение владельца.
7. **flock на NFS/сетевых ФС** может быть ненадёжен; предполагается
   локальная ФС (текущая архитектура).
8. **Wall-clock** для `started_at`/возраста; duration — monotonic. Перевод
   часов может влиять на stale-эвристику.
9. **PID reuse** mitigated через starttime, но `/proc` есть только на
   Linux; fallback — stale-порог.
10. **Legacy evidence** по-прежнему содержит result/stderr content; новый
    журнал — нет. Политика очистки evidence не меняется.
11. **Старые читатели** нового event-журнала могли бы считать start как
    invocation; в текущем репозитории единственный читатель —
    `summarize`, он обновляется. Внешних потребителей нет.
12. **Hooks не используются**; при будущем включении `--bare` они
    отключатся.

## 11. Оценка точности метрик

| Метрика | ok | failed (JSON) | failed (no JSON) | timeout | cancelled | interrupted/unknown |
|---|---|---|---|---|---|---|
| task/attempt/agent/role/model | точно | точно | точно | точно | точно | точно |
| started_at | точно | точно | точно | точно | точно | точно |
| finished_at | точно | точно | точно | точно (момент kill) | точно (момент interrupt) | **неизвестно** (`null`) |
| duration | точно | точно | точно | точно (до kill) | точно (до interrupt) | **неизвестно** |
| exit_code | точно | точно | точно | null | null | null |
| status | точно | точно | точно | точно | точно | **inferred** |
| token/cost | Claude-reported | Claude-reported | **неизвестно** | **неизвестно** | **неизвестно** | **неизвестно** |
| request_count | только если CLI дал | только если CLI дал | неизвестно | неизвестно | неизвестно | неизвестно |
| num_turns | если CLI дал | если CLI дал | неизвестно | неизвестно | неизвестно | неизвестно |
| provider invoice | не коррелирован | не коррелирован | не коррелирован | не коррелирован | не коррелирован | не коррелирован |

«Неизвестно» всегда кодируется `null` + `usage_known=false`, никогда не
нулём и не оценкой. Accepted-task cost — сумма известного; рядом
показывается число invocations с неизвестным usage.

Уточнения по источникам: API-error result message обычно содержит usage, но
`error_during_execution` после аварии сессии может обнулять cost-поля —
такие нули трактуются как unknown. При SIGTERM CLI документированно
завершается с кодом 143 и **не создаёт result message**; SessionEnd при
этом может сработать, но usage не передаёт. Точный `request_count` сейчас
недоступен; в будущем его потенциально дадут `api_request`-события OTel,
но только при надёжном экспорте и task correlation — это отдельный этап.

## 12. Соответствие текущей архитектуре

- Не меняются: model routing, число агентов, алгоритм планирования,
  `Budget`/`TOKEN_BUDGET`/`COST_BUDGET` (их нет), автоматические остановки,
  permissions/security, VPS/Docker/systemd, hooks/settings.
- Не добавляются scheduler, timer, daemon или фоновые процессы:
  reconciliation вызывается существующими `run`/`recover` и вручную.
- Не переписывается `observability.py`: расширяются существующие функции,
  legacy-записи остаются читаемыми.
- Не сохраняются prompt/response/headers/API keys/секреты/file content;
  hooks-поля `last_assistant_message`/`error_details` не используются.
- Единственное поведенческое соседство: runner пишет 2 дополнительные
  строки и fsync на invocation (≈ единицы мс), а также перехватывает
  `KeyboardInterrupt`/`TimeoutExpired` только чтобы записать terminal и
  переподнять исходное исключение. Task outcome, retry и state не меняются.
- Изменения локальны для stdlib-слоя autonomy; Django/PostgreSQL/Redis не
  затрагиваются.

## 13. Решения, требующие одобрения владельца

**Блокирующие (без них реализацию не начинать):**

1. **Схема v2 в том же `invocations.jsonl`**: два типа событий, nullable
   token-поля, `usage_known`/`request_count_known`, legacy-записи без
   `event` читаются как ok. Альтернатива — отдельный файл событий.
2. **Runner — единственный писатель lifecycle-событий**; `_account`
   перестаёт писать JSONL. Это меняет существующий тест
   `test_orchestrator_account_records_task_and_attempt` (заменяется).
3. **Failed usage учитывается только в журнале, не в state/budget.**
   Подтвердить, что бюджетная политика остаётся success-only.
4. **Классификация cancelled только для SIGINT**; SIGTERM/SIGKILL →
   interrupted. Альтернатива — SIGTERM handler (меняет shutdown).
5. **Reconciliation без нового scheduler**: на старте `run`/`recover` и
   вручную; stale-порог `2*BA_MODEL_TIMEOUT+300` с; живой pid не трогать.
6. **Hooks не внедряются** на этом этапе; interactive-сессии —
   отдельный этап (SessionStart/SessionEnd/StopFailure + transcript_path).

**Желательные, но не блокирующие:**

7. `Popen` вместо `subprocess.run` для child pid/управляемого kill — не
   требуется для точности; рекомендуется оставить `subprocess.run`.
8. Явный `InvocationContext` в role-методах (обновление fake runners в
   тестах) против contextvar без изменения сигнатур.
9. Retention/ротация журнала (сейчас не вводится).
10. Автоматическое завершение orphan-child после SIGKILL orchestrator
    (сейчас не вводится — деструктивно).

## 14. Источники

Официальная документация Claude Code:

- Hooks reference — https://code.claude.com/docs/en/hooks
- Hooks guide — https://code.claude.com/docs/en/hooks-guide
- CLI reference (`-p`, `--agent`, `--settings`, `--bare`) —
  https://code.claude.com/docs/en/cli-reference
- Headless mode / SIGTERM —
  https://code.claude.com/docs/en/headless#stop-a-run-with-sigterm
- Monitoring usage (OTel token/cost counters, `api_request`) —
  https://code.claude.com/docs/en/monitoring-usage
- Agent SDK cost tracking (failed conversations, crash recovery) —
  https://code.claude.com/docs/en/agent-sdk/cost-tracking#track-costs-on-failed-conversations

Проверка установленной версии: `claude --version` → **2.1.329**; встроенный
справочник событий содержит `SessionEnd` (matchers `clear`, `resume`,
`logout`, `prompt_input_exit`, `other`), `StopFailure` (matchers типов
ошибок API), `SubagentStop` (Agent-tool subagents), `PostToolUseFailure`
(tool-level).

OpenTelemetry:

- Traces / spans — https://opentelemetry.io/docs/concepts/signals/traces/
- Recording errors — https://opentelemetry.io/docs/specs/semconv/general/recording-errors/
- GenAI spans (usage attributes) —
  https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/
- Trace API: SetStatus —
  https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/trace/api.md#set-status

Python subprocess semantics: https://docs.python.org/3/library/subprocess.html#subprocess.run
(при timeout и `KeyboardInterrupt` child убивается; проверено также по
`/usr/local/lib/python3.14/subprocess.py`).

Локальные документы: `docs/audits/BA_TOKEN_EFFICIENCY_AUDIT_REPORT.md`,
`docs/audits/BA_TOKEN_OBSERVABILITY_DESIGN.md`,
`docs/audits/BA_TOKEN_OBSERVABILITY_METRICS_SCHEMA.md`,
`docs/audits/BA_TOKEN_OBSERVABILITY_IMPLEMENTATION_REPORT.md`.
