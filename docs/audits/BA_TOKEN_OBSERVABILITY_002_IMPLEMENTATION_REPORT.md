# BA-TOKEN-OBSERVABILITY-002 — implementation report

**Дата:** 2026-11-23  
**Статус:** **IMPLEMENTED / TESTS PASSING / INDEPENDENT REVIEW ACCEPT (minor fixes applied)**  
**Модели:** реализация/проверки — `deepseek-flash[1m]`; независимый review —
`code-reviewer` (`deepseek-v4-pro`).  
**Основа:** одобренный дизайн
`docs/audits/BA_TOKEN_OBSERVABILITY_002_DESIGN.md` (§13 все решения
подтверждены владельцем 2026-11-23).

## 1. Согласованный scope

Реализован минимальный lifecycle-журнал:

- schema v2 в существующем `.autonomy/invocations.jsonl`: события
  `invocation_started` / `invocation_finished`;
- runner — единственный писатель lifecycle-событий; `_account` больше не
  дублирует JSONL;
- failed usage пишется в журнал, но **не** меняет state/budget;
- `cancelled` = SIGINT; SIGTERM/SIGKILL → `interrupted` через reconciliation;
- reconciliation вызывается на старте существующих `run`/`recover` и вручную;
- hooks не внедрялись; `subprocess.run` сохранён; `InvocationContext` явный;
  ротация журнала и kill orphan-child не добавлялись.

## 2. Изменённые файлы

| Файл | Изменение |
|---|---|
| `autonomy/observability.py` | schema v2, `InvocationContext`/`InvocationStart`, `from_outcome`/`from_failure`, start/finish writers, lock+O_APPEND+fsync, partial-tail handling, `reconstruct_invocations`, `reconcile_invocations`, расширенный `summarize` |
| `autonomy/runner.py` | start event до spawn; ровно один terminal на исход (ok/api_error/invalid_output/model_mismatch/launch_error/timeout/cancelled); evidence после terminal; `journal_root`; `context` в role-обёртках |
| `autonomy/orchestrator.py` | `InvocationContext` для ролей; `_account` без JSONL; reconciliation в `_run_once`/`recover`; `ClaudeRunner(journal_root=store.root)` |
| `tests/unit/test_autonomy_observability.py` | 30 тестов: lifecycle, API-error usage, unknown usage, timeout/cancel/launch/model mismatch, dedup, legacy, partial tail, reconciliation (dead/reused/boot/abandoned), concurrency, manual CLI |
| `tests/unit/test_autonomy.py`, `test_autonomy_budget.py`, `test_autonomy_notify.py`, `tests/integration/test_autonomy_worktree.py` | fake runners принимают `context` |
| `docs/audits/BA_TOKEN_OBSERVABILITY_METRICS_SCHEMA.md` | ссылка на schema v2 |
| `docs/audits/BA_TOKEN_OBSERVABILITY_002_DESIGN.md` | статус APPROVED/IMPLEMENTED |

## 3. Lifecycle и точность

| Исход | status / error_type | usage |
|---|---|---|
| CLI success | `ok` | Claude-reported; `usage_known` только при ненулевом `modelUsage` |
| API error / non-zero | `failed` / `api_error` | сохраняется, если CLI вернул ненулевой `modelUsage`; нулевые crash-поля → `usage_known=false` |
| невалидный JSON | `failed` / `invalid_output` | null + `usage_known=false` |
| неверная модель | `failed` / `model_mismatch` | сохраняется, если есть |
| spawn failure | `failed` / `launch_error` | null |
| timeout | `timeout` / `timeout` | null; `exit_code=null`; duration до kill |
| SIGINT | `cancelled` / `operator_interrupt` | null |
| owner pid dead | `interrupted` / `orchestrator_gone` | null; `inferred=true`; `finished_at/duration=null` |
| boot id изменился | `interrupted` / `host_reboot` | null; inferred |
| pid reuse | `interrupted` / `pid_reused` | null; inferred |
| stale, живость не подтверждена | `unknown` / `abandoned_unknown` | null; inferred |
| started без terminal | pending | не входит в accepted cost |

`request_count` остаётся `None`, если CLI не вернул int;
`request_count_known=false`. `num_turns` не подменяет request count.

## 4. Реальный контрольный запуск

Выполнен через фактический CLI (`claude -p --agent autonomy-qa`) во временном
worktree, журнал — `/tmp/ba-obs-control/journal` (локальный, вне Git).
Промпты/ответы в журнал не попали; проверено grep.

| Сценарий | Фактическая запись |
|---|---|
| success | `ok`, `usage_known=true`, input 5962, output 105, cost 0.032435, exit 0 |
| timeout (`timeout=1`) | `timeout`, usage null, `usage_known=false`, exit null |
| SIGINT (SIGALRM → KeyboardInterrupt) | `cancelled`/`operator_interrupt`, usage null |
| invalid model | `failed`/`api_error`, exit 1, usage null (CLI не дал usage) |
| SIGKILL launcher после start + reconcile | `interrupted`/`orchestrator_gone`, `inferred=true`, usage null |

Итог: **5 started + 5 finished**, pending 0, двойного учёта нет; evidence
создан только для success и API error (timeout/cancel/crash — по дизайну без
evidence). Orphan `claude`-процессов после kill не осталось.

## 5. Проверки

```text
pytest tests/unit/test_autonomy_observability.py   -> 30 passed
pytest autonomy unit/integration subset            -> passed (включая worktree)
ruff check autonomy tests                          -> All checks passed
ruff format --check autonomy tests                 -> 90 files already formatted
mypy autonomy                                      -> no issues (9 files)
pytest --create-db (full)                          -> exit 0; 1019 tests, 1011 passed, 8 skipped
```

Финальный full suite выполнен после review-фиксов. Отдельно повторно
прогнаны 30 observability tests после последней правки теста.

## 6. Совместимость

- Legacy-записи без `event` читаются как authoritative terminal `ok`;
  `status="error"` нормализуется в `failed`.
- Старые `RunResult` и fake runners работают: новые поля имеют defaults;
  role-обёртки принимают optional `context`.
- `state.json` не менялся; budget policy success-only сохранена.
- Пустой/отсутствующий журнал → пустой отчёт; partial tail не считается
  invocation.

## 7. Остатки и ограничения

- Usage при timeout/cancel/interrupted неизвестен (нет result message);
  hooks это не исправляют.
- SIGKILL orchestrator может оставить child `claude` живым; parent-pid
  детектирует смерть orchestrator, но не судьбу child; kill не выполняется.
- SIGTERM классифицируется как interrupted (signal handler не добавлялся).
- Сбой записи журнала не влияет на задачу; возможна неточная классификация
  pending → interrupted, но без двойного учёта.
- Ротация/retention журнала не вводились; файл локален, вне Git.
- Legacy evidence по-прежнему содержит result/stderr; новый журнал — нет.

## 8. Независимый review

`code-reviewer` (`deepseek-v4-pro`) — **ACCEPT**, два прохода (первый по коду,
второй после delta). Замечания и статус:

- by_status отдавал нулевые token/cost без накопления — **исправлено**
  (`add(by_status, ...)`);
- started без owner/started_at оставался pending навсегда — **исправлено**
  (`unknown/abandoned_unknown`);
- SIGINT в окне между start-записью и subprocess — **исправлено**
  (`record_started` внутри try);
- отсутствовал ручной `python -m autonomy.observability reconcile` —
  **добавлен**;
- не были покрыты launch_error/model_mismatch/pid_reused/abandoned/
  evidence-failure/CLI — **добавлены тесты**;
- `ERROR_TYPES` не валидировался, reasoning-only usage считался unknown —
  **исправлено**.

Остаточные непроверенные: cross-process flock (тест thread-level; локальная
ФС), live-reproduction review не выполнял (полагается на control run).

## 9. Git

- Commit: заполняется после коммита.
- Working tree после коммита проверяется.
