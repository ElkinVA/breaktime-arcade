# BA-TOKEN-EFFICIENCY-REMEDIATION — план снижения расхода

**Дата:** 2026-11-23  
**Статус:** **PROPOSED / NOT IMPLEMENTED** — аудит завершён, архитектурные
изменения не выполнялись.  
**Связанные документы:** [audit report](BA_TOKEN_EFFICIENCY_AUDIT_REPORT.md),
[metrics](BA_TOKEN_EFFICIENCY_METRICS.md).

## 1. Цель и границы

Снизить стоимость **принятой задачи** и объём повторяемого контекста, не
ухудшая качество, безопасность и обязательные требования ТЗ.

Ограничения текущего этапа: не менять orchestrator, бюджет, модели, число
агентов, VPS, Docker, секреты, историю/сессии; не возвращать
`TOKEN_BUDGET`/`COST_BUDGET` как stop-условия; не запускать массовые
эксперименты.

## 2. Приоритеты

| № | Изменение | Ожидаемый эффект | Риск | Владелец |
|---|---|---|---|---|
| R1 | Task-bounded сессии + handover | Убирает рост 294k–753k контекста в долгой сессии | потеря контекста между ролями | owner/architect |
| R2 | Компактный brief архитектора | Убирает обязательные ~41,5k токенов реестров на каждый planning call | пропуск важного решения | architect |
| R3 | Ограничение tool-loop и QA scope | Меньше tool-rounds/повторных тестов в одной роли | неполная проверка | developer/QA |
| R4 | Дедупликация и no-progress detection | Меньше повторных planner/QA/reviewer циклов | ложная остановка | orchestrator |
| R5 | Task/agent-level instrumentation | Позволяет измерять эффект и стоимость/задачу | overhead/приватность | owner |
| R6 | Адресная документация и архив истории | Меньше повторного чтения реестров | устаревший контекст | docs owner |
| R7 | Model routing по сложности | Pro только на plan/review, Flash на implement/QA | неверная маршрутизация | owner/architect |

## 3. R1 — Task-bounded сессии и handover

**Проблема:** локальные две сессии дали 85,6% requests и 88,6% cache read;
median context 294k/465k, max 753k; compaction 2/4. Каждый tool-round
повторяет накопленную историю.

**Изменение (предложение, не выполнять сейчас):**

- завершать role/session на границе задачи; не продолжать один
  `claude --bg`/interactive session через несколько задач;
- формировать компактный `handoff` фиксированного размера: task_id,
  acceptance, изменённые файлы, diff stat, команды/exit, findings,
  остатки, next step;
- новая Developer/QA/Reviewer-сессия получает handoff, а не всю историю;
- для `autonomy/runner.py` предусмотреть `--resume` только для
  продолжения **той же** ограниченной роли, не для новой задачи;
- в `devcontrol/claude.py:181-198` добавить политику
  task-boundary/handover (при реализации).

**Критерий эффекта:** median context/request и requests/task падают;
handoff сохраняет acceptance/security. Точный процент — после R5.

**Риски:** потеря неочевидных требований; handoff должен включать
ссылки на ТЗ/ADR, а не всю историю.

## 4. R2 — Компактный контекст архитектора

**Проблема:** `.claude/agents/autonomy-architect.md:12-14` обязывает читать
`NOW` + `PROJECT_STATUS` + `BACKLOG` + `OWNER_DECISIONS`; 166 216 chars
≈ 41,5k токенов на planning call, плюс код/инструменты.

**Изменение:**

- ввести `docs/handoff/TASK_BRIEF.md` (или генерируемый brief) с текущими
  READY/blockers/owner decisions, ограниченный ~8–12k chars;
- architect читает brief + целевой раздел, а не полные реестры;
- исторические stage-блоки `NOW`/`PROJECT_STATUS` вынести в архивный
  `docs/status/archive/` (при согласовании);
- `CLAUDE.md:22` оставить обязательные NOW/PROJECT_STATUS/BACKLOG для
  **человека/новой сессии**, но не требовать полного чтения агентом на
  каждый planning call.

**Критерий:** planning prompt ≤~15k tokens до кода; обязательные
owner/security decisions присутствуют.

## 5. R3 — Ограничение tool-loop и QA

**Проблема:** `autonomy/runner.py::run` задаёт только timeout 900 с; нет
`--max-turns`, context cap; developer/QA имеют Bash и могут многократно
запускать тесты/читать файлы; каждый tool-round добавляет контекст.

**Изменение:**

- добавить в `ClaudeRunner.run` параметры `max_turns`, `max_output_tokens`
  (если CLI поддерживает), явный `max_context` бюджет роли;
- QA запускает **targeted** tests + lint/types, полный suite — только по
  условию/один раз на задачу; результаты сжимать до команды/exit/краткого
  tail;
- developer не повторяет уже пройденные тесты; evidence хранит полный
  вывод, но prompt — только сводку;
- для reviewer diff ограничить уже существующими 40k; developer/QA
  result caps 8k не увеличивать.

**Файлы:** `autonomy/runner.py:83-149`, `:215-289`,
`autonomy/orchestrator.py:360-390`.

## 6. R4 — Дедупликация и no-progress detection

**Проблема:** `orchestrator.py:604-650` вызывает `propose`, если очередь
пуста; `run` до 5 задач; `retry` до 2; нет проверки «нет diff/тот же
failure».

**Изменение:**

- architect вызывать только при пустой очереди и cooldown/явном запросе;
- кэшировать proposal fingerprint; не предлагать одинаковые задачи;
- перед retry сравнивать diff/последний error; при идентичном failure —
  BLOCKED с диагностикой, без нового QA/Reviewer;
- запретить повторный full test, если предыдущий PASS и diff не менялся.

**Файлы:** `autonomy/orchestrator.py:429-452`, `:604-650`,
`autonomy/state.py:413-428`, `autonomy/metrics.py`.

## 7. R5 — Инструментирование

Добавить (при реализации) в `RunResult`/evidence/StateStore:

```text
task_id, agent_id, session_id, role, model,
request_count, prompt_cache_hit_tokens, prompt_cache_miss_tokens,
completion_tokens, reasoning_tokens (если доступно),
estimated_cost, retry_count, task_status, accepted_result,
started_at, finished_at
```

- `autonomy/runner.py`: сохранять request_count/num_turns и cache-поля из
  Claude Code JSON, если доступны; иначе — из контролируемого прокси.
- `autonomy/state.py`: добавить в `Task.usage`/run record; не агрегировать
  только totals.
- `autonomy/metrics.py`: per-role/per-agent, requests/task, cache hit/miss,
  cost/accepted task, retries, no-progress.
- Provider gateway: task_id/agent_id correlation; **никогда** не логировать
  API keys, headers, prompt content.
- Экспорт — только агрегаты; retention согласовать.

**Критерий:** можно ответить, сколько requests/cache/cost дала конкретная
задача и роль, и отделить orchestrator от интерактивных сессий.

## 8. R6 — Документация

- `CLAUDE.md` + `.claude/README.md` дублируют часть контекста (11k+8k);
  оставить один краткий operational brief, детали — по ссылкам.
- `NOW`/`PROJECT_STATUS` содержат исторические P0–P5 блоки; текущий
  статус — верхний раздел, историю — в архив.
- `TASK_HISTORY` (75k), `AUDIT_REGISTER` (52k), `RISK_REGISTER` (33k) не
  читать целиком на каждой задаче; выдавать срез по ID.
- Защищённые файлы (`CLAUDE.md`, `.claude/settings`, hooks) — только с
  разрешения владельца.

## 9. R7 — Модели и стоимость

- Pro — architect/reviewer, Flash — developer/QA (текущая политика).
- Не менять модели без per-agent данных.
- Не возвращать token/cost как stop; использовать soft alerts/дашборд.
- Для простых/read-only проверок допустим Flash/локальные тесты; решение
  по каждой роли — после R5.

## 10. Этапы внедрения

1. **Измерение (R5, docs-only instrumentation design)** — сначала
   подтвердить вклад механизмов; без изменений поведения.
2. **R2/R6** — компактный brief/архив; не меняет runtime.
3. **R4** — dedupe/no-progress; небольшой orchestration change, owner
   approval.
4. **R1/R3** — session/tool limits; требует owner approval и тестов.
5. Повторный замер; сравнить cost/accepted task и first-pass rate; не
   ухудшать качество.

## 11. Критерии приёмки изменений (будущих)

- Cost/accepted task и requests/task измерены до/после.
- First-pass rate/QA failures не ухудшились; security/ТЗ не потеряны.
- Handoff сохраняет acceptance, owner decisions, residual.
- Нет роста cache miss/ошибок из-за чрезмерного дробления сессий.
- Нет новых секретов в логах/метриках.
- Полный suite/линт/типы зелёные.

## 12. Stop conditions

- Нет owner approval на изменение AI HQ/session policy.
- Приходится ослаблять safety/ТЗ/тесты.
- Изменение ухудшает first-pass/качество без доказанного выигрыша.
- Нужны платные эксперименты/новые провайдеры без согласования.
- Любая destructive-операция или изменение секретов/VPS.

## 13. Что не делать

- Не возвращать `TOKEN_BUDGET`/`COST_BUDGET` как stop.
- Не удалять историю/сессии/реестры ради метрик.
- Не сокращать обязательные security/ТЗ-требования.
- Не запускать массовые benchmark-прогоны на API.
- Не менять модели/число агентов без отдельного решения.
