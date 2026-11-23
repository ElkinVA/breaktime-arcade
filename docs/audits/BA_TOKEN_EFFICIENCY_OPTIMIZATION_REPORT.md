# BA-TOKEN-EFFICIENCY — practical optimization report

**Дата:** 2026-11-23  
**Статус:** **IMPLEMENTED; effect measured where a deterministic metric exists**  
**Основа:** `BA_TOKEN_EFFICIENCY_AUDIT_REPORT.md`,
`BA_TOKEN_EFFICIENCY_REMEDIATION_PLAN.md`, OBS-001/002.

## 1. Что оптимизировано и почему

### 1.1. Обязательный контекст архитектора

**Подтверждённая причина (аудит):** `.claude/agents/autonomy-architect.md`
требовал читать `NOW.md`, `PROJECT_STATUS.md`, `BACKLOG.md`,
`OWNER_DECISIONS.md` целиком перед каждым planning call. Суммарно — 168 145
chars (~42k tokens по оценке 4 chars/token) до добавления кода/инструментов.

**Изменение:**

- добавлен `docs/handoff/ARCHITECT_BRIEF.md` — компактная routing map
  (продуктовое состояние, приоритеты, инварианты, ссылки на точные разделы);
- `autonomy-architect.md` теперь начинает с brief и читает полные реестры
  только при отмеченной неоднозначности или под конкретную задачу.

**Детерминированный показатель:**

| Метрика | До | После | Изменение |
|---|---:|---:|---:|
| Обязательные полные документы | 4 файла | 1 brief + targeted | — |
| Символы обязательного bundle | 168 145 | 5 011 | −163 134 (−97.0 %) |
| Оценка токенов (4 chars/token) | ~42 036 | ~1 253 | ~−40 783 на proposal |

Это оценка обязательного bundle, а не фактический API-расход: реальный
planning call дополнительно читает код. Инструкции агента выросли на ~325
chars (context discipline), что пренебрежимо мало относительно сокращения.
Фактические `input_tokens` до/после измеряются отдельным контрольным
запуском (см. §3).

### 1.2. Повторное чтение и tool-loop

**Подтверждённая причина (аудит):** роли могли повторно читать большие
документы и повторять проверки без нового результата; tool-loop не ограничен
по ходам.

**Изменение (prompt-level, без hard caps):**

- `autonomy-developer.md`: только task-scoped файлы и точный раздел ТЗ;
  targeted tests первыми; не повторять полный suite; после двух одинаковых
  неудач остановиться и сообщить.
- `autonomy-qa.md`: не дублировать полный прогон developer; проверять
  изменённую поверхность; уже зафиксированную команду/exit code проверять
  один раз.
- `autonomy-reviewer.md`: diff + только необходимые файлы; не читать реестры
  целиком; не повторять уже подтверждённые проверки.
- `autonomy-architect.md`: Grep/Glob и точечный Read; остановиться, когда
  feasibility/acceptance установлены.

Количественного before/after для этого пункта нет: жёсткие лимиты не
вводились, чтобы не снижать качество анализа. Эффект будет виден в
`invocations.jsonl` по `input_tokens`/`num_turns` на последующих задачах.

### 1.3. Организация интерактивных сессий

**Подтверждённая причина (аудит):** две длинные локальные сессии дали 85.6 %
запросов и 88.6 % cache read; median context 294k/465k, max 753k.

**Изменение:** `docs/runbook/ai_session_policy.md` — одна сессия на
значимый task boundary, handoff в NOW перед закрытием, `/clear`/новая сессия
после задачи, не более одной активной `claude --bg`-сессии, не держать idle
сессии, не перечитывать полные реестры. Это операционная политика, не
автоматический enforcement: scheduler/hooks не добавлялись.

## 2. Что намеренно не менялось

- Модели и маршрутизация (`deepseek-v4-pro` / `deepseek-flash[1m]`).
- Число агентов и роли.
- `TOKEN_BUDGET`/`COST_BUDGET` и автоматические остановки — не вводились.
- Полный suite, независимый review и security-анализ — не сокращались.
- Orchestrator planning/task state/budget — не менялись.
- Большие документы не удалялись и не переписывались; brief — routing map,
  полные реестры остаются источником истины.

## 3. Фактическое измерение архитектора

**Метод:** одинаковый prompt и пустая очередь, реальный
`claude -p --agent autonomy-architect` (`deepseek-v4-pro`) в двух worktree:
- before — HEAD до оптимизации (старые agent instructions, 4 полных
  документа);
- after — новый commit (brief + context discipline).

Записи — в отдельном временном journal; proposals не enqueue-ились.

| Фаза | input_tokens | output_tokens | cache read | cost USD | num_turns | tasks в JSON |
|---|---:|---:|---:|---:|---:|---:|
| before | 132 148 | 13 076 | 1 259 392 | 1.617336 | 32 | direct JSON parse failed; orchestrator parser: 4 tasks |
| after | 59 430 | 19 452 | 843 520 | 1.205210 | 39 | direct JSON parse failed; orchestrator parser: 3 tasks |

Фактическое изменение на этой паре запусков:

| Метрика | before | after | Δ |
|---|---:|---:|---:|
| input_tokens | 132 148 | 59 430 | −72 718 (−55.0 %) |
| cache_read_tokens | 1 259 392 | 843 520 | −415 872 (−33.0 %) |
| output_tokens | 13 076 | 19 452 | +6 376 (+48.8 %) |
| num_turns | 32 | 39 | +7 |
| cost_usd | 1.617336 | 1.205210 | −0.412126 (−25.5 %) |

**Production validation 2026-11-23:** реальный `orchestrator propose` после
оптимизации записал 59 759 input, 22 537 output, 1 017 984 cache read,
1.371212 USD, 46 turns и поставил 4 валидные задачи. Относительно
до-оптимизационного controlled call: input −54.8 %, cost −15.2 %; output и
num_turns выше. Это фактический production-вызов в OBS-002 journal, не
оценка.

Оба результата — валидные proposals после штатного `_parse_json` (4 и 3
задачи); качество на этом срезе не упало. Output/num_turns выросли; причина
не доказана (возможно, больше исследования кода), поэтому это честный
результат, а не «экономия любой ценой». Один запуск на фазу — индикативное
измерение, не статистика; повторять массово не планируется.

## 4. Ограничения измерения

- Стоимость одного planning call зависит от того, какие файлы код-базы модель
  решит прочитать; сравнение на одном запуске — индикативное, не
  статистическое.
- `input_tokens` включает tool results; brief сокращает обязательный bundle,
  но не запрещает чтение кода.
- Для интерактивных сессий количественного before/after нет: в журнал они не
  попадают; политика снижает риск, но не измерена автоматически.
- Провайдерский invoice, cache hit/miss и request_count по-прежнему не
  коррелируются с задачей.

## 5. Изменённые файлы

- `.claude/agents/autonomy-architect.md`
- `.claude/agents/autonomy-developer.md`
- `.claude/agents/autonomy-qa.md`
- `.claude/agents/autonomy-reviewer.md`
- `docs/handoff/ARCHITECT_BRIEF.md` (new)
- `docs/runbook/ai_session_policy.md` (new)

## 6. Operational observation: first AI HQ production task

`ARCADE-RETENTION-001` (commit `8e42426`) дал фактическую стоимость по
OBS-002 journal:

| Роль/попытка | input | output | cost USD |
|---|---:|---:|---:|
| architect (propose) | 59 759 | 22 537 | 1.371212 |
| developer attempt 1 | 64 050 | 33 564 | 3.022070 |
| QA attempt 1 (fail: NOT TESTED mypy/migrations) | 41 069 | 19 021 | 1.369958 |
| developer attempt 2 | 59 879 | 27 294 | 1.858417 |
| QA attempt 2 (pass) | 33 482 | 14 646 | 0.900024 |
| reviewer attempt 2 | 44 324 | 10 416 | 0.718564 |
| **Итого** | 302 563 | 127 478 | **9.240245** |

Вывод: после сокращения architect bundle доминируют role/tool-контексты
developer/QA, а неудачная QA-попытка стоила ~4.39 USD. Это не объявляется
достигнутой экономией; это измеренная точка для следующих шагов. QA-тулинг
(host mypy + постоянный migration guard) исправлен, чтобы не повторять
retry по инфраструктурной причине. Модели/бюджет не менялись. Следующая задача `ARCADE-CATALOG-SLUG-301-001` (attempt 1) стоила
~4.848 USD (developer 2.763, QA 0.723, reviewer 1.362) — без failed QA и
retry; architect-вызов амортизируется между задачами.

## 7. Git

- Commit: `c389f53` — `chore(ai): reduce architect context and add session hygiene`.
