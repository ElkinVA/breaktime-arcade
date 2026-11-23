# BA-TOKEN-EFFICIENCY-AUDIT-001 — отчёт

**Дата:** 2026-11-23  
**Режим:** исследование, **без изменений кода, orchestrator, бюджета,
моделей, VPS, Docker и секретов**.  
**База:** Git `HEAD` = `origin/main` = `50e6fa1`; рабочее дерево чистое.  
**Данные:** выгрузка DeepSeek за 22–23.11.2026 предоставлена владельцем;
локальные транскрипты Claude Code и код AI Headquarters проверены отдельно.

## 1. Краткий вывод

Основной подтверждённый вклад в объём входного контекста дают **не отдельные
задачи orchestrator, а длительные интерактивные/CLI-сессии Claude Code**,
в которых каждый следующий tool-round повторно отправляет накопленную
историю: в локальных транскриптах две сессии дают **85,6% запросов** и
**88,6% cache-read токенов**. Вторая по значимости группа причин —
обязательное чтение крупных реестров агентом-архитектором и длинные
tool-циклы ролей (`claude -p` без ограничения числа ходов/контекста).
Orchestrator в текущем окружении **не запущен** (`.autonomy` отсутствует),
поэтому приписать ему заявленные 7 968 запросов без task-level
инструментирования нельзя.

Провайдерские 7 968 Flash-запросов и 576 Pro-запросов — **факт выгрузки**;
локальные транскрипты не являются этим же биллингом: период, машина и
модель в них отличаются.

## 2. Подтверждённые факты

### 2.1. Git и фактическое состояние AI Headquarters

- `HEAD` = `origin/main` = `50e6fa1`; незакоммиченных изменений нет.
- `.autonomy/` отсутствует; `~/.local/state/ba-devcontrol/` отсутствует.
- systemd user units `ba-autonomy-orchestrator` и `ba-devcontrol`
  **не установлены**; timers — 0.
- `claude agents --json` — только текущая interactive-сессия; background
  sessions нет.
- `api.telegram.org:443` — connection timeout; bot-процесс отсутствует.
- Значит: текущий провайдерский расход **не может быть объяснён только
  живым orchestrator**; он включает интерактивные сессии и/или другой ПК.

### 2.2. Провайдерская выгрузка (owner-provided)

| Метрика | Значение |
|---|---:|
| Flash requests | 7 968 |
| Flash cache hit | 1 890 338 176 |
| Flash cache miss | 8 031 088 |
| Flash output | 3 868 282 |
| Средний cache hit/request | 237 241 |
| Средний cache miss/request | 1 008 |
| Средний input/request | 238 249 |
| Средний output/request | 485 |
| Pro requests | 576 |
| Стоимость 22–23.11 | ≈ $11,75 |
| Стоимость/request (арифметика) | ≈ $0,001375 |

Это агрегированные данные провайдера; **per-task и per-agent разбивки в
выгрузке нет**. Стоимость/request — арифметика, не цена за задачу.

### 2.3. Локальные транскрипты Claude Code

Проверено 8 JSONL-файлов проекта (`~/.claude/projects/...ba`), 77,1 МБ;
агрегировались только metadata (`usage`, model, sessionId, tool counts),
без вывода содержимого.

```text
assistant requests (usage entries): 8 942
tool_use / tool_result:             5 579 / 5 567
cache_read_input_tokens:            3 234 696 192
input_tokens:                       8 684 309
output_tokens:                      11 745 201
модель в metadata:                  deepseek-flash 8 940; synthetic 2
```

Две длительные сессии:

| Session | Requests | Cache read | Output | Median context | Max context | Compactions |
|---|---:|---:|---:|---:|---:|---:|
| `2b3837d2-e04` | 3 777 | 1 271 534 080 | 5 823 381 | 294 153 | 752 999 | 4 |
| `5d4c9f64-10e` | 3 874 | 1 593 131 776 | 2 979 867 | 465 559 | 753 265 | 2 |
| **Итого две** | **7 651** | **2 864 665 856** | **8 803 248** | — | — | 6 |
| Доля всех локальных | **85,6%** | **88,6%** | **75,0%** | — | — | — |

Контекст измерен как `input_tokens + cache_read_input_tokens +
cache_creation_input_tokens` на один assistant request. Максимум 753k
означает, что сессия дошла до очень большого окна и продолжала
tool-rounds; compaction была всего 2–4 раза.

### 2.4. Размеры контекстных документов

| Документ | Размер | Оценка токенов |
|---|---:|---:|
| `CLAUDE.md` | 11 161 chars | ~2 790 |
| `.claude/README.md` | 7 946 chars | ~1 986 |
| `docs/handoff/NOW.md` | 26 822 chars | ~6 705 |
| `docs/status/PROJECT_STATUS.md` | 67 196 chars | ~16 799 |
| `docs/status/BACKLOG.md` | 18 248 chars | ~4 562 |
| `docs/decisions/OWNER_DECISIONS.md` | 53 950 chars | ~13 487 |
| `docs/tasks/TASK_HISTORY.md` | 74 724 chars | ~18 681 |
| `docs/audits/AUDIT_REGISTER.md` | 52 078 chars | ~13 019 |
| `docs/risks/RISK_REGISTER.md` | 32 693 chars | ~8 173 |
| `docs/decisions/ADR-APPF-001.md` | 37 990 chars | ~9 497 |

Оценка токенов — `chars/4`, не биллинг. Четыре документа, которые
`autonomy-architect` обязан читать (`NOW`, `PROJECT_STATUS`, `BACKLOG`,
`OWNER_DECISIONS`), дают **166 216 chars ≈ 41,5k токенов** только за один
planning call, ещё до чтения кода и tool results.

### 2.5. Реализация AI Headquarters

- `autonomy/orchestrator.py::run` — bounded-цикл до `max_tasks` (default 5;
  VPS unit `--max-tasks 1`), `claim_next` по priority/dependencies.
- `autonomy/runner.py::run` — один `claude -p --agent ...` на роль,
  `--output-format json`; timeout 900 с; **нет** `--max-turns`,
  `--max-budget`, `--resume` и явного ограничения tool-loop.
- `_developer_prompt` — acceptance + previous error (до 4 000 chars).
- `_qa_prompt` — developer.result до 8 000 chars.
- `_reviewer_prompt` — developer/QA до 8 000 chars каждый + diff до 40 000
  chars.
- `_architect_prompt` — JSON состояния очереди; architect-agent обязан
  читать четыре крупных документа и код.
- `StateStore.record_usage` агрегирует usage по task; `metrics.py` считает
  tokens/cost на **accepted task**, но не request_count/cache hit/miss и не
  разбивает по роли.
- Runner пишет evidence с `modelUsage`, usage и результатом; `.autonomy`
  отсутствует, исторических task-level evidence для аудита нет.

### 2.5. Жизненный цикл задачи и передачи контекста

- `orchestrator._run_isolated`: worktree → Developer → QA → Reviewer →
  fast-forward merge; состояние/usage пишутся в `StateStore`; `recover_running`
  восстанавливает RUNNING/QA/REVIEW после падения.
- Каждая роль — отдельный `claude -p` invocation; **`--resume` не
  используется**, поэтому между ролями передаётся не полная история, а
  срезы: developer.result до 8k, QA result до 8k, diff до 40k.
- Внутри одной role invocation Claude Code сам ведёт tool-loop; именно там
  накапливаются промежуточные tool results и растёт контекст. Runner не
  задаёт max turns/context cap; timeout 900 с — единственный верхний предел.
- `devcontrol` `/continue` запускает `claude --bg`; `SessionEnd` только
  фиксирует IDLE, автоматического handover/next session нет.
- Параллельность ограничена `RUN_LOCK`, но в проверенном окружении
  orchestrator/Dev Control не запущены; единственная активная сессия —
  interactive.

### 2.6. Почему cache hit огромен, но это не оправдание

Высокий cache hit (237k/request) означает, что провайдер повторно получает
почти тот же огромный prefix. Это дешевле cache miss, но **не уменьшает
объём обрабатываемого контекста и не устраняет стоимость output/Pro**.
Длинная сессия с 753k контекста остаётся дорогой независимо от cache.

## 3. Обнаруженные дефекты и архитектурные причины

### D1. Длительные сессии без task-boundary handover — основной драйвер

**Факт:** две локальные сессии — 85,6% запросов/88,6% cache read; median
context 294k/465k, max 753k; compaction 2–4.
**Механизм:** Claude Code отправляет накопленную историю на каждом
tool-round; чем дольше сессия, тем больше повторяемый prefix. Это
относится к interactive/CLI-сессиям и `devcontrol` `claude --bg`, а не
только к `autonomy` task-run.
**Файлы/участки:** `devcontrol/claude.py:181-198` (`claude --bg`);
`autonomy/runner.py:83-149`; отсутствие обязательного handover/закрытия
сессии после задачи.
**Вклад:** подтверждён локальными данными; доля именно в провайдерских
22–23 запросах не доказана (нет task correlation).

### D2. Обязательный крупный doc-bundle архитектора

**Факт:** `.claude/agents/autonomy-architect.md:12-14` требует читать
`NOW`, `PROJECT_STATUS`, `BACKLOG`, `OWNER_DECISIONS`; их размер
166k chars (~41,5k tokens) на один planning call, плюс код/инструменты.
**Риск:** каждый `propose` (в том числе при пустой очереди) повторно
загружает реестры; исторические слои `NOW`/`PROJECT_STATUS` увеличивают
prefix.
**Участки:** `.claude/agents/autonomy-architect.md`, `CLAUDE.md:22`,
`orchestrator.py:329-343`, `orchestrator.py:429-452`.

### D3. Tool-loop роли не ограничен по ходам/контексту

**Факт:** `ClaudeRunner.run` задаёт timeout, но не `--max-turns`/
`--max-budget`/явный context cap; developer/QA имеют Bash-инструменты
(`runner.py:215-289`), QA может запускать полный `make check`, developer —
итеративно тестировать; один `claude -p` invocation может сделать много
API-запросов, каждый с растущим контекстом.
**Вклад:** вероятный, масштаб не подтверждён без per-invocation
request_count.

### D4. Повторное планирование и auto-next без no-progress guard

**Факт:** `orchestrator.py:604-650` при отсутствии READY вызывает
`propose`; `run` допускает до 5 задач; `retry` — до `max_attempts=2`;
`qa_failures`/`review_rejections` считаются, но нет детектора «нет diff/
тот же тест/нет прогресса».
**Риск:** повторные architect/QA/reviewer вызовы и циклы около одной
задачи; вклад не измерен, `.autonomy` отсутствует.

### D5. Дублирование и исторические слои документации

**Факт:** `CLAUDE.md` (11k), `.claude/README.md` (8k), `NOW` (27k),
`PROJECT_STATUS` (67k), `TASK_HISTORY` (75k), `AUDIT_REGISTER` (52k),
`RISK_REGISTER` (33k); `NOW`/`PROJECT_STATUS` содержат несколько
исторических stage-блоков. Agents, читающие их целиком, платят за
историю, не нужную текущей задаче.
**Риск:** рост контекста и повторное чтение; не все документы читаются
каждой ролью, поэтому вклад зависит от роли.

### D6. Нет task/agent-level учёта запросов и cache hit/miss

**Факт:** `autonomy/metrics.py` даёт tokens/cost на accepted task;
`StateStore.Task.usage` агрегирует токены, но не request_count/cache
hit/miss; `RunResult` не содержит request_count; `.autonomy`/evidence
отсутствуют. Провайдерская выгрузка не содержит task_id.
**Следствие:** нельзя доказать, сколько запросов создала конкретная
задача/роль/повтор; нельзя отделить orchestrator от интерактивных сессий.

### D7. Модель в локальных транскриптах — только Flash

**Факт:** 8 940 usage-записей `deepseek-flash`, 0 `deepseek-v4-pro`;
провайдерская выгрузка содержит 576 Pro-запросов.
**Интерпретация:** это **не доказательство** неверной маршрутизации:
Pro-вызовы могли идти на другом ПК/в удалённом worktree, а локальные
транскрипты не покрывают весь биллинг. Это подтверждает необходимость
per-agent evidence (`modelUsage`) и корреляции с провайдером.

## 4. Вероятные причины и неподтверждённые гипотезы

**Вероятно (подтверждено частично):**

1. Длительные сессии и tool-rounds — главный источник 238k среднего
   input; локальные две сессии дают 85,6% запросов.
2. Architect doc-bundle — крупный фиксированный prefix каждого planning
   call (41,5k токенов только на четыре документа).
3. Tool-loop ролей и повторные QA/Reviewer вызовы — вторичный вклад;
   нужен request_count.

**Гипотезы (не подтверждены):**

- Все 7 968 Flash-запросов созданы `autonomy` orchestration;
- `devcontrol --bg`/auto-next создал существенную долю;
- Pro-вызовы маршрутизируются неправильно или не логируются;
- duplicate enqueue/повторные задачи дают заметный вклад;
- полный `make check` в QA выполняется на каждой попытке.

Для проверки нужны per-task/per-agent метрики; без них эти числа
**не подставлять**.

## 5. Экономическая таблица

Точные per-task данные отсутствуют. Не заполнять `N/A` оценками.

| Метрика | Значение | Источник/статус |
|---|---:|---|
| API-запросы на задачу | **N/A** | нет task_id в выгрузке; `.autonomy` отсутствует |
| Cache hit на задачу | **N/A** | нет task/agent correlation |
| Cache miss на задачу | **N/A** | то же |
| Output на задачу | **N/A** | то же |
| Стоимость задачи | **N/A** | только общая $11,75 |
| Повторные вызовы на задачу | **N/A** | `attempts` есть в state, но state отсутствует |
| Доля задач без прогресса | **N/A** | нет task-level данных |
| Стоимость принятой задачи | **N/A** | `metrics.py` умеет считать, но state/evidence отсутствуют |
| Flash requests (все) | 7 968 | owner |
| Pro requests (все) | 576 | owner |
| Средний input/Flash request | 238 249 | расчёт из owner |
| Средний output/Flash request | 485 | расчёт из owner |
| Стоимость/request | ≈ $0,001375 | арифметика, не per-task |

Локальные (не биллинговые) данные: 8 942 requests, 3,234,696,192 cache
read, 11,745,201 output за 16–23.11; две сессии — 85,6% запросов.

## 6. Рекомендации (кратко)

Полный план — [BA_TOKEN_EFFICIENCY_REMEDIATION_PLAN.md](BA_TOKEN_EFFICIENCY_REMEDIATION_PLAN.md).

1. **Task-bounded sessions + handover:** не держать одну сессию на
   несколько задач; после задачи сохранять компактный handoff и начинать
   новую сессию/роль с ограниченным контекстом.
2. **Компактный brief архитектора:** читать только актуальные разделы,
   вынести историю в архив; ограничить обязательный doc-bundle.
3. **Ограничить tool-loop:** max turns/tool output/QA test scope; не
   запускать полный suite в каждой попытке.
4. **Убрать повторное планирование:** architect только при пустой
   очереди/по таймеру; dedupe и no-progress detection.
5. **Инструментировать task_id/agent_id/session_id/model/request_count/
   cache hit/miss/output/cost/retry/status/accepted.**
6. **Модели по сложности:** Pro — architect/reviewer; Flash — implement/QA;
   подтверждать фактический `modelUsage`, не менять модели без данных.
7. **Не возвращать TOKEN_BUDGET/COST_BUDGET как stop**; использовать
   observability и soft alerts.

## 7. Ожидаемый эффект и риски

**Ожидаемый эффект (качественно):** снижение повторяемого prefix и числа
запросов за счёт ограничения сессии/tool-loop и адресного контекста.
Точный процент без task-level замера не заявляется.

**Риски:** потеря требований/security при чрезмерном сокращении контекста;
ошибки handover; рост cache miss при новых сессиях; снижение качества при
агрессивном max-turns; instrumentation может собирать чувствительные
данные — хранить только метрики и IDs, без prompt/secret content.

## 8. NOT TESTED

- Реальная причинно-следственная связь 7 968/576 запросов с конкретными
  задачами orchestrator.
- Живой orchestrator/`devcontrol` (не запущены).
- Pro-маршрутизация на другом ПК/в удалённом worktree.
- Стоимость одной задачи/принятой задачи.
- Влияние конкретных изменений без внедрения и повторного замера.

## 9. Итог

Аудит **завершён как исследование**. Основной подтверждённый драйвер —
длительные сессии с накопленным контекстом; архитектурные усилители —
doc-bundle архитектора, tool-loop ролей и отсутствие task-level учёта.
Orchestrator не работал в проверенном окружении, поэтому обвинять только
его нельзя. До внедрения рекомендаций и повторного замера архитектурные
изменения не выполнялись.
