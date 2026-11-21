# AI_INFRASTRUCTURE_PREPARATION_AUDIT (исторический, 2026-11-20)

> Архив. Документ отражает состояние на 2026-11-20 и не является текущим
> статусом проекта. Актуальные источники — `docs/handoff/NOW.md`,
> `docs/status/PROJECT_STATUS.md`, `docs/status/BACKLOG.md`.

**Дата аудита:** 2026-11-20, ~08:15 MSK (данные по текущей сессии — частичные; сессия продолжается).
**Объекты:** `/home/elkinva/projects/ba` и `/home/elkinva/projects/ai-dev`.
**Режим:** read-only. Исходники, настройки, скиллы, hooks, документация, Git-индекс, `.env`, сертификаты и credentials не изменялись. Коммиты, reset, clean, stash, удаление файлов и новые пакеты разработки не выполнялись.
**Единственное созданное изменение:** этот файл отчёта в корне `ba`, вне продуктового кода (`apps/`, `config/`, `tests/` не затронуты).
**Секреты:** значения токенов, паролей, ключей и приватных конфигураций не выводились. Для секретоподобных совпадений указаны только пути и категории.

---

## 0. Резюме

1. **Основная работа действительно идёт на Flash.** В `~/.bashrc` основная модель и все алиасы (`opus`, `sonnet`, `haiku`) указывают на `deepseek-flash`/`deepseek-flash[1m]`; `CLAUDE_CODE_SUBAGENT_MODEL` также Flash. Все 2105 API-запросов основной сессии в доступных логах — `deepseek-flash`. Pro доступен и технически работоспособен, но фактически использован только в трёх коротких probe-вызовах субагентов: 8 сообщений, ~20,2 тыс. input-токенов, $0,179 расчётной стоимости — **0,04 %** от зафиксированной расчётной стоимости.
2. **Архитектура «Pro ставит задачи — Flash исполняет» не включена процессом.** Агенты `architect`, `code-reviewer`, `security-auditor` закреплены за Pro, но вызываются только явно; основная Flash-сессия сама планирует, читает, правит и проверяет. В логах нет ни одного реального Pro-review и ни одного Pro-плана; три Pro-вызова имеют описания «Probe … agent».
3. **Skills/agents/hooks спроектированы разумно, но недоиспользуются.** 7 скиллов, 5 агентов, 1 guard-хук. За все 8 сессий: `ba-development` — 1 вызов, `ba-create-report` — 2, остальные 5 скиллов — 0; агенты — 6 вызовов, из них 5 probe-вызовов. `ba-testing` содержит устаревшее утверждение, что pytest/ruff/mypy недоступны; `ba-project-audit` указывает на несуществующий путь; `ba-code-review` не обязывает вызывать независимого Pro-агента.
4. **Контекст восстанавливается по документам, но с оговорками.** Свежая read-only сессия по документам восстановила цель, план §2.25, текущую позицию, выполненные пакеты, блокеры, следующий пакет и provenance ТЗ. Она не смогла проверить код/git/тесты и нашла устаревшие указатели (`docs/spec`, `ai-dev`-путь), устаревший раздел `CLAUDE.md`, расхождения в датах/цифрах. Реестры занимают ~175 КБ / 1 927 строк; компактного «NOW» нет.
5. **Репозитории независимы, но связаны копиями ТЗ.** `ba` — продуктовый репозиторий; `ai-dev` — отдельное AI-пространство. Оригиналы ТЗ лежат в `ba/technical_specification/` (**untracked**), побайтовые копии — в `ai-dev/docs/project-reference/` (**tracked**, SHA-256 совпадают). Кодовых импортов, submodule, symlink и общих Git-историй нет. Риски: каноническое место ТЗ в Git не решено, `ai-dev` не зарегистрирован как Claude-проект, его работа логируется под `ba`, у `ai-dev` нет `.claude`/guard.
6. **Расход токенов сконцентрирован.** По локальным cost-state записям: ~$435,45 расчётной стоимости за 8 сессий; 72,6 % — одна длинная сессия `2b3837d2` ($316,10), 26,4 % — работы по `ai-dev` ($114,87) в трёх сессиях, залогированных под `ba`. Всё это Flash. Основные источники: длинный контекст (692 млн cache-read токенов), 1546 Bash-вызовов (1141 с file-reading паттернами), 4,8 млн символов tool-result, повторные чтения файлов, effort `max`. Это оценка Claude Code, не счёт провайдера.
7. **Критический приоритет:** checkpoint + bundle обоих репозиториев; реальный Pro-review текущего diff; Bash-guard/permissions; изоляция `ai-dev`; затем маршрутизация моделей, NOW-контекст и исправление устаревших указателей. Очистка мусора — после checkpoint.

---

## 1. Подтверждённые факты

### 1.1. Репозитории и Git

| Параметр | `ba` | `ai-dev` |
|---|---|---|
| Ветка | `main` | `main` |
| HEAD | `1fc96b40b6c11b1fcb20e1e5a833a65d166c8340` | `b82609bd297b92bdec1e9d274e373fb5d542ed33` |
| Remote | отсутствует | отсутствует |
| Submodule | нет | нет |
| Tracked-файлов | 552 | 36 |
| Modified tracked | 101 | 1 (`CLAUDE.md`, +42 строки) |
| Untracked-файлов | 107 | 10 |
| Status entries | 163 (101 `M`, 62 `??`) | 5 (1 `M`, 4 `??`) |
| Staged | 0 | 0 |
| `.claude/` | 7 skills, 5 agents, 1 hook, settings | отсутствует |
| Claude project registration | есть (`~/.claude.json/projects` — только `ba`) | отсутствует |
| Claude-транскрипты | 8 сессий, 53 МБ | 0; работа `ai-dev` логировалась в сессиях `ba` |

Факты:
- В `ba` незакоммичены все последние миграции, сервисы, тесты, реестры, `.claude/` и `technical_specification/`.
- В `ai-dev` незакоммичены `M CLAUDE.md` (раздел «Автономность и передача результата», +42 строки), `handoff/AI-ENV-002/`, два audit-дампа (`AI_ENVIRONMENT_AUDIT_20261118_080734.md` 317 312 байт и `..._091512.md` 433 829 байт), `tools/collect_ai_environment.sh`.
- Оба репозитория — независимые Git-истории; remote/backup отсутствуют.

### 1.2. Конфигурация моделей и Claude Code

| Параметр | Фактическое значение | Источник |
|---|---|---|
| Основная модель | `deepseek-flash[1m]` | `~/.bashrc:132`; env |
| Алиас Opus | `deepseek-flash[1m]` | `~/.bashrc:133`; env |
| Алиас Sonnet | `deepseek-flash[1m]` | `~/.bashrc:134`; env |
| Алиас Haiku | `deepseek-flash` | `~/.bashrc:135`; env |
| Модель субагентов по умолчанию | `deepseek-flash` | `~/.bashrc:136`; env |
| Endpoint | `https://api.deepseek.com/anthropic` | `~/.bashrc:131` |
| Effort | `max` | env `CLAUDE_CODE_EFFORT_LEVEL`, `CLAUDE_EFFORT` |
| Auto-compact window | `786432` | env |
| Файл токена | `~/.config/ba/deepseek.env`, только `ANTHROPIC_AUTH_TOKEN`, режим 600 | env/stat; значение не выводилось |
| Launcher-скрипт | `setup-claude-code-deepseek-ubuntu.sh` пишет в `~/.config/claude-code/deepseek.env` | скрипт, строка 63 |
| Фактический env-файл launcher-скрипта | отсутствует | `ls` |
| Глобальные настройки Claude | `~/.claude/settings.json` — только `theme: dark` | файл |
| Проектные настройки `ba` | `.claude/settings.json` — только PreToolUse guard | файл |
| Permissions/deny/allow | отсутствуют; `allowedTools` в `~/.claude.json` пуст | `~/.claude.json`, settings |
| Зарегистрированные проекты | только `/home/elkinva/projects/ba` | `~/.claude.json` |

Агенты:

| Агент | Модель в frontmatter | Фактические сообщения в логах | Назначение |
|---|---|---|---|
| `architect` | `deepseek-v4-pro` | 2 сообщения (probe) | read-only архитектура/ТЗ |
| `code-reviewer` | `deepseek-v4-pro` | 2 сообщения (probe) | read-only review diff |
| `security-auditor` | `deepseek-v4-pro` | 4 сообщения (probe) | read-only security |
| `developer` | `deepseek-flash` | 3 сообщения (probe) | реализация в назначенных файлах |
| `qa-engineer` | `deepseek-flash` | 2 сообщения (probe) | тестовая матрица/прогоны |

Важное наблюдение: в `meta.json` всех пяти probe-агентов поле `pickedEffortModel` = `deepseek-flash[1m]`, при этом в транскриптах трёх агентов `message.model` = `deepseek-v4-pro`. Это может быть полем выбора effort, а не модели; фактическая модель подтверждена транскриптом. Требуется контролируемая проверка после изменения маршрутизации.

### 1.3. Фактические модели в логах

Источник: 8 JSONL-транскриптов `~/.claude/projects/-home-elkinva-projects-ba/*.jsonl` и 5 subagent-транскриптов сессии `2b3837d2`.

| Показатель | `deepseek-flash` / `[1m]` | `deepseek-v4-pro` |
|---|---:|---:|
| API-запросы основной сессии | 2105 | 0 |
| Сообщения основной сессии (dedup) | 2080 | 0 |
| Сообщения субагентов | 5 | 8 |
| Input-токены основной сессии | 2 164 706 | 0 |
| Output-токены основной сессии | 3 115 905 | 0 |
| Cache-read основной сессии | 635 665 920 | 0 |
| Thinking-токены основной сессии | 1 903 440 | 0 |
| Input-токены субагентов | 12 349 | 20 179 |
| Output-токены субагентов | 1 073 | 2 483 |
| Cache-read субагентов | 18 048 | 32 384 |
| Thinking-токены субагентов | 412 | 868 |
| Расчётная стоимость (cost-state) | $435,27 | $0,179 |

Cost-state по моделям (последний снимок на сессию, сумма по 8 сессиям):

```text
deepseek-flash[1m]  input 2 606 111  output 3 040 612  cache_read 692 036 352  thinking 1 858 585  $435,064
deepseek-flash     input    24 499  output     3 103  cache_read      18 048  thinking     2 355  $0,209
deepseek-v4-pro    input    20 179  output     2 483  cache_read      32 384  thinking       868  $0,179
TOTAL                                                                                          $435,452
```

Расхождение между «основной сессией» и cost-state объясняется субагентами, накопительными снимками и особенностями учёта; для итоговых цифр используйте cost-state, для структуры сообщений — транскрипты. Cost-state — расчёт Claude Code, не счёт DeepSeek.

Pro-вызовы:
- `architect`: 2 сообщения, 6 296 input, 499 output, 5 888 cache-read, 77 thinking;
- `code-reviewer`: 2 сообщения, 6 293 input, 556 output, 5 888 cache-read, 133 thinking;
- `security-auditor`: 4 сообщения, 7 590 input, 1 428 output, 20 608 cache-read, 658 thinking;
- описания в meta: «Probe architect agent», «Probe code-reviewer agent», «Probe security-auditor agent».
- Реального Pro-review текущего diff в логах нет.

### 1.4. Skills, agents, hooks, permissions

- Skills: 7 файлов, 1,5–3,0 КБ каждый; описания загружаются в список, тела — при вызове. За все сессии: `ba-development` 1, `ba-create-report` 2, остальные 0.
- Agents: 5 файлов, 1,6–1,9 КБ; 6 вызовов: 5 probe в `2b3837d2` + 1 `architect` в `402395a8` (без отдельного Pro-следа в cost-state).
- Hook: один `PreToolUse` для `Edit|Write|MultiEdit|NotebookEdit`, fail-closed; блокирует `CLAUDE.md`, `technical_specification/**`, `docs/spec/**`, `.git`, `certs`, `creds`, `reports`, `infra/nginx/staging.conf`, `.claude/settings.local.json`, `.env*`, пользовательские настройки; **не покрывает Bash**.
- Permissions: в `settings.json` нет `permissions`; `allowedTools` пуст; режим подтверждений — auto. Опасные Bash-команды технически не блокируются.
- Pre-commit: EOF/whitespace/YAML/JSON/merge/large-files/private-key/ruff. CI: ruff, mypy, manage.py check, makemigrations, pytest + coverage; E2E в CI не запускается.
- `ai-dev`: `.claude`, agents, hooks, skills, permissions отсутствуют; есть только `CLAUDE.md`, `README.md`, `docs/project-reference/`, `handoff/`, `tools/ai-handoff/`, `tools/collect_ai_environment.sh`.

### 1.5. Восстановление контекста

Симуляция: отдельный read-only Explore-агент, без чтения исходников, без git/docker/pytest/make, только документация `ba`. Он прочитал `CLAUDE.md`, `PROJECT_STATUS`, `CONTEXT_RECOVERY`, `BACKLOG`, `TASK_HISTORY`, `OWNER_DECISIONS`, `AUDIT_REGISTER`, `RISK_REGISTER`, часть `docs/contracts/`, `docs/foundation/`, заголовки и §2.25 `ts_site.txt`.

Восстановлено с высокой уверенностью:
- цель продукта и 11 продуктовых инвариантов;
- нормативный план §2.25 (этапы 0–8);
- текущая позиция: каркас, этап 0 не закрыт, этап 1 не завершён; App F не реализован;
- выполненные пакеты и статусы (BA-STAGE-2.1…2.5, BA-QUALITY-001, BA-CATALOG-001…005, E2E, FOUNDATION, APPF-001);
- блокеры и решения владельца;
- следующий незаблокированный пакет — BA-QUALITY-002;
- пути ТЗ и SHA-256, зафиксированные в документах;
- устаревшие указатели и противоречия.

Не удалось определить только по документации:
- фактическое состояние кода, тестов, конфигурации и Git (не читались по условию);
- канонический вариант BA-GAME-2.2;
- содержание BA-SDK-1.1/BA-ENV-1.1;
- является ли строка §2.25 «этап 1 не начат» действующей или устаревшей;
- решения владельца вне раздела A `OWNER_DECISIONS`;
- production/legal/email/remote/backup;
- точные SHA-256 на текущий момент (не пересчитывались).

Стоимость симуляции: 98 155 subagent-токенов, 18 tool uses, 155 секунд. Это показывает: восстановление по документам возможно, но не бесплатно; 175 КБ реестров — существенная часть контекста.

### 1.6. Связь `ba` и `ai-dev`

- `ba/technical_specification/ts_site.txt` (169 360 байт) SHA-256 `17d2caa0…c7090`; `ts_game.txt` (34 712 байт) SHA-256 `40e6d425…26db`.
- `ai-dev/docs/project-reference/` содержит те же файлы с теми же SHA-256; копии **tracked** в Git `ai-dev`; оригиналы в `ba` — **untracked**.
- `ai-dev/docs/project-reference/README.md` фиксирует: копии сделаны из `ba/technical_specification/`, оригиналы не изменялись, побайтовое совпадение (`cmp`) и SHA-256 совпадают; с загруженными в ChatGPT оригиналами совпадает только построчный текст (различие CRLF/финальный перевод строки).
- `BA-SDK-1.1` и `BA-ENV-1.1` отсутствуют; BA-GAME-2.2 существует в двух вариантах, эталонный не выбран.
- Ссылки `ai-dev → ba`: provenance README, handoff-задания, заморозка `ba` в `ai-dev/CLAUDE.md`. Ссылки `ba → ai-dev`: только `docs/handoff/CONTEXT_RECOVERY.md:67` и исторический `BA-FOUNDATION-001_AUDIT_PACKAGE.txt`; кодовых зависимостей нет.
- Git-истории независимы; remote/submodule/symlink между репозиториями нет.
- `ai-dev` не зарегистрирован в `~/.claude.json/projects`; все Claude-сессии запускались с cwd `ba`. Работа `ai-dev` логировалась в сессиях `ba`: `39d90d68` (119 Edit/Write путей `ai-dev`), `402395a8` (78 `ai-dev` + 33 `ba`), `627b1af9` (18 `ai-dev`). `2b3837d2` — 0 путей `ai-dev`.
- Guard-хук `ba` создан 2026-11-18 12:16 MSK. Сессии `39d90d68` и `627b1af9` — 2026-11-17, до хука; `402395a8` завершилась 12:20 MSK, то есть почти все её записи — до появления хука. Текущий хук блокирует Edit/Write вне `ba`, но не Bash; у `ai-dev` своего guard нет.
- Handoff `ai-dev`: `AI-ENV-002-RESULTS.zip` (337 745 байт) проверен `sha256sum -c` — OK, `unzip -t` — OK; ZIP содержит `PROJECT_REFERENCE`, `GIT_DIFF`, `GIT_STATUS`, `EXECUTION.log`, `MANIFEST`. В `~/ai-handoff/` остались 8 каталогов `.build-*` (всего ~5 МБ) — успешные staging, сохранённые скриптом для проверки.
- Секрет-скан `ai-dev`: 46 текстовых файлов, 2 эвристических совпадения категории `connection-string` — `handoff/SETUP-001-FIX-01/TEST_RESULTS.md:117` и `tools/ai-handoff/tests/run-tests.sh:366`; оба указывают на `db.example.internal`, пароль — тестовая подстановка. Подтверждённых секретов нет; значения не выводились.

### 1.7. Расход токенов

Сессии (cost-state — последний снимок; стоимость расчётная):

| Сессия | Рабочая область (по путям) | Сообщений основной сессии | Input | Output | Cache-read | Cost USD | Модели |
|---|---|---|---:|---:|---:|---:|---|
| `2b3837d2` | `ba` (0 путей `ai-dev`) | 1495 | 1 526 208 | 1 978 450 | 480 224 128 | 316,10 | flash + 3 Pro probe |
| `402395a8` | преимущественно `ai-dev` (101/33) | 244 | 272 404 | 555 009 | 94 736 512 | 84,35 | flash (+1 Agent) |
| `39d90d68` | `ai-dev` (134/0) | 218 | 126 012 | 292 981 | 48 338 944 | 22,62 | flash |
| `627b1af9` | `ai-dev` (18/5) | 42 | 86 608 | 166 970 | 6 125 056 | 7,91 | flash |
| `5d4c9f64` | `ba` (25/2), текущая | 79* | 127 581 | 122 463 | 6 241 280 | 4,34* | flash |
| `921dc119` | `ba` | 1 | 13 407 | 30 | 0 | 0,07 | flash |
| `ccf7843e` | `ba` | 1 | 12 486 | 2 | 0 | 0,07 | flash |
| `6e39a78a` | `ba` | 2 | 0 | 0 | 0 | 0,00 | synthetic |
| **Итого** | | **2082** | **2 164 706** | **3 115 905** | **635 665 920** | **435,45** | |

\* Текущая сессия — частичные данные на момент сбора; после этого она выросла (включая симуляцию контекста на 98 155 subagent-токенов).

Выводы:
- 72,6 % расчётной стоимости — одна длинная сессия `2b3837d2` (2026-11-18 09:22 UTC — 2026-11-19 17:06 UTC, 1495 сообщений).
- 26,4 % — работы `ai-dev` в трёх сессиях, залогированных под `ba` (`402395a8` + `39d90d68` + `627b1af9`).
- 99,96 % стоимости — Flash; Pro — 0,04 %, только probe.
- Основные источники контекста: 692 млн cache-read, 2,6 млн input, 3,0 млн output, 1,86 млн thinking; effort `max`.
- Инструменты: Bash 1546 вызовов (1141 с file-reading паттернами), Edit 1000, Write 199, Read 110, Agent 6, Skill 3, WebFetch 3. Tool-result: 2868 результатов, 4,8 млн символов, средний 1673; максимум — 106 815 символов (Bash), 27 799 (Read tool-results), 24 062 (Bash), 23 377 (Read `CONTEXT_RECOVERY`), 21 729 (Read `PROJECT_STATUS`).
- Повторные чтения: `collect_ai_environment.sh` — 23 чтения (22 дубля) в `402395a8`; `create-handoff.sh` — 6; `ts_site.txt` — 4; `create_report.py` — 4; `test_core.py`, `i18n/middleware.py`, `test_accounts.py` — по 3.
- Исторические деструктивные команды: 54 `rm -rf` под `/tmp`; 1 `rm -rf reports` (путь проекта, сессия `2b3837d2`); 2 `DROP DATABASE IF EXISTS ba_schema_check_002` в dev-проверке схемы. `git reset --hard`, `git clean`, `push --force` не найдены. Совпадения `truncate`/`FLUSHALL` в текущей сессии — текст аналитического скрипта, а не выполненные команды; исключены.

---

## 2. Предположения

- **A-01.** Cost-state `totalCostUSD` — оценка Claude Code, а не счёт DeepSeek; фактические списания могут отличаться.
- **A-02.** Принадлежность сессий к `ba`/`ai-dev` определена по путям чтения/записи и cwd; cwd у всех сессий — `ba`. Точная бизнес-принадлежность части сессии `402395a8` (33 пути `ba`, 101 путь `ai-dev`) может быть смешанной.
- **A-03.** Данные текущей сессии `5d4c9f64` частичные; её стоимость и токены вырастут после завершения.
- **A-04.** `pickedEffortModel=deepseek-flash[1m]` у Pro-агентов — поле выбора effort, а не фактической модели; фактическая модель подтверждена `message.model` в транскриптах. Требуется контролируемая проверка.
- **A-05.** `rm -rf reports` в `2b3837d2` удалил каталог сгенерированных отчётов; доказательств потери пользовательских данных нет, но и доказательств обратного нет.
- **A-06.** Два `connection-string` совпадения в `ai-dev` — тестовые фикстуры (`db.example.internal`, подстановка пароля), не реальные секреты.
- **A-07.** Устаревшие разделы `CLAUDE.md`, `README.md`, `.claude/README.md`, `ba-testing` — исторические/необновлённые, а не намеренная дезинформация.
- **A-08.** Строка §2.25 «этап 1 не начат» — нормативный снимок от 12.11.2026; фактические работы BA-STAGE-1.1/1.2/2.x/каталог его опережают. Это расхождение, а не доказательство отмены требований.
- **A-09.** В этом аудите тесты/линтеры/HTTP-проверки не перезапускались; результаты 185 passed / 82,34 % взяты из отчёта текущей сессии и предыдущих self-check, а не подтверждены независимо.
- **A-10.** За пределами доступных логов возможны другие сессии/инструменты, не оставившие транскриптов; вывод «Pro почти не используется» относится к доступным логам.

---

## 3. Обнаруженные проблемы

| ID | Severity | Проблема | Доказательство | Влияние |
|---|---|---|---|---|
| PR-01 | P0 | Нет checkpoint/backup; почти вся работа `ba`, реестры, `.claude/`, ТЗ — uncommitted/untracked; remote отсутствует | Git-статус; R-008 | Потеря worktree/диска уничтожает код и контекст |
| PR-02 | P0 | Pro не используется для реального планирования/review; только 3 probe | Логи: 8 Pro-сообщений, $0,179, 0,04 %; описания «Probe» | Нет независимого review; качество решений Flash не проверено |
| PR-03 | P0 | Нет Bash-guard/permissions; исторический `rm -rf reports`; ai-dev без guard | Hook покрывает только Edit/Write; лог `2b3837d2` | Разрушительные команды и записи вне `ba` технически возможны |
| PR-04 | P1 | `ai-dev` не зарегистрирован как Claude-проект; его работа логируется под `ba`; у него нет `.claude` | `~/.claude.json`; 0 транскриптов ai-dev; 3 сессии с путями ai-dev | Нет независимости истории/токенов; риск кросс-записи |
| PR-05 | P1 | Устаревшие указатели: `docs/spec` пуст; `CONTEXT_RECOVERY` ведёт на `ai-dev/...` без `../`; `ba-project-audit` — на несуществующий `docs/project-reference` | `README.md:6`, `CLAUDE.md:5`, `CONTEXT_RECOVERY.md:67`, `ba-project-audit/SKILL.md:13` | Новая сессия ищет ТЗ не там; provenance теряется |
| PR-06 | P1 | `CLAUDE.md` недооценивает состояние: «все schemas пусты», «Views каталога — stub», `docs/` пуст | `CLAUDE.md:9-17` против `PROJECT_STATUS.md:146-178`, `TASK_HISTORY.md` | Риск повторной реализации/неверных решений |
| PR-07 | P1 | Реестры ~175 КБ; нет компактного NOW; модель-политика и BA-AUTONOMOUS-001 не в первичных реестрах | 1 927 строк; `OWNER_DECISIONS` не содержит BA-AUTONOMOUS-001; модель только в `.claude/README` и skill | Дорогое восстановление; модель-политика теряется |
| PR-08 | P1 | «AWAITING INDEPENDENT REVIEW» накапливаются; независимый review не выполняется | BACKLOG: 6+ пакетов; Pro-review в логах нет | Ложное чувство готовности; дефекты переходят дальше |
| PR-09 | P1 | TZ provenance: оригиналы `ba/technical_specification` untracked; копии `ai-dev` tracked; `docs/spec` пуст; каноническое место в Git не решено | R-010; `OWNER_DECISIONS.md:193`; SHA-256 | Риск рассинхронизации/потери оригинала |
| PR-10 | P1 | Container E2E падает: Playwright driver `libatomic.so.1` отсутствует; host E2E 13 passed | Отчёт текущей сессии; Dockerfile/dev image | E2E не воспроизводится в контейнере; CI/dev parity |
| PR-11 | P2 | Skills недоиспользуются; `ba-testing` устарел; `ba-code-review` не обязывает Pro-агента; `ba-development` не требует обновления реестров | Usage 3 skill calls; файлы skills | Процесс исполняется вручную на Flash; review-гейт фиктивен |
| PR-12 | P2 | Токен-неэффективность: 1141 Bash file-reading, 4,8 млн символов tool-result, повторные чтения, effort max | Логи | Высокая стоимость/латентность, риск потери контекста |
| PR-13 | P2 | Мусор: root one-off scripts, `.backups/`, `project_dump.txt`, `BA-FOUNDATION-001_AUDIT_PACKAGE.txt`, old reports, ai-handoff staging | Инвентаризация | Шум в поиске, риск случайного запуска архивных скриптов |
| PR-14 | P2 | Несогласованные даты/цифры: `TASK_HISTORY` header BA-DOC-002 при содержании BA-CATALOG-005; coverage 81,65/177 vs 82,34/185; «8 tests» vs сумма 33 | Документы | Недоверие к реестрам, неверные выводы |
| PR-15 | P2 | `ai-dev` governance uncommitted (`M CLAUDE.md`), audit-дампы и `collect_ai_environment.sh` untracked; 8 staging-каталогов | Git-статус; `~/ai-handoff` | Потеря правил/аудитов; дубли и устаревшие копии |

---

## 4. Критические риски

| ID | Риск | Вероятность/влияние | Связь |
|---|---|---|---|
| CR-01 | Потеря незакоммиченной работы и контекста `ba`/`ai-dev` | Высокая/критическое | PR-01, PR-15, R-008 |
| CR-02 | Разрушительная Bash-команда или запись вне разрешённой области | Средняя/критическое | PR-03, PR-04 |
| CR-03 | Отсутствие реального независимого review; дефекты и нарушения ТЗ проходят дальше | Высокая/высокое | PR-02, PR-08, PR-11 |
| CR-04 | Кросс-контаминация `ba`/`ai-dev`: работа под одним cwd, разные правила, нет guard у `ai-dev` | Средняя/высокое | PR-04, PR-03 |
| CR-05 | Рассинхронизация/потеря канонического ТЗ; `docs/spec` пуст; оригиналы untracked | Средняя/критическое | PR-05, PR-09 |
| CR-06 | Устаревший контекст ведёт к неверным решениям (повторная реализация, неверный этап) | Высокая/высокое | PR-05, PR-06, PR-07, PR-14 |
| CR-07 | Перекос качества/стоимости: всё Flash, Pro не участвует; длинные сессии и max effort | Высокая/среднее | PR-02, PR-12 |
| CR-08 | E2E не воспроизводится в контейнере; CI не покрывает E2E | Средняя/высокое | PR-10 |
| CR-09 | Governance-правила `ai-dev` и AI-настройки не в Git; решения не трассируются | Средняя/высокое | PR-07, PR-15 |

---

## 5. Рекомендуемые изменения (P0/P1/P2)

| ID | P | Изменение | Ожидаемый эффект | Требует владельца |
|---|---|---|---|---|
| REC-01 | P0 | Checkpoint + tag + bundle для `ba`; отдельно для `ai-dev`; без cleanup до этого | Восстановимость кода/контекста; снимает CR-01 | Да (scope, TZ, `.claude`, reports) |
| REC-02 | P0 | Реальный независимый review текущего diff через `code-reviewer` (Pro); security — `security-auditor` | Закрывает/выявляет дефекты; снимает фиктивный review-гейт | Да (запуск review) |
| REC-03 | P0 | Bash-guard и/или permissions.deny: `rm -rf` вне `/tmp`, `docker compose down -v`, `git reset --hard`, `git clean`, `push --force`, `DROP/FLUSHALL`, запись в защищённые пути | Техническая защита вместо только правил | Да (settings/hook) |
| REC-04 | P1 | Изолировать `ai-dev`: запускать Claude с cwd `ai-dev`, зарегистрировать проект, добавить `.claude` guard/запрет записи в `ba` | Независимые логи/токены; нет кросс-записи | Да |
| REC-05 | P1 | Маршрутизация: Pro — план/архитектура/review; Flash — реализация/рутина/тесты; добавить `ba-plan`; обновить `ba-development`/`ba-code-review` | Качество решений + контролируемая стоимость | Да (`.bashrc`, skills) |
| REC-06 | P1 | NOW-контекст (10–20 строк) + правило обновления + фиксация модели; исправить указатели; commit docs/`.claude` | Быстрое восстановление, меньше контекста и дрейфа | Да (protected `CLAUDE.md`) |
| REC-07 | P1 | Исправить `ba-testing`, `ba-project-audit`, `.claude/README`, `TASK_HISTORY` header; обновить `CLAUDE.md`/`README` | Доверие к документации | Да (protected files) |
| REC-08 | P1 | Записать BA-AUTONOMOUS-001 и AI-модель-политику в `OWNER_DECISIONS`/AI-ENV-реестр; связать с NOW | Трассируемость решений | Да |
| REC-09 | P1 | Токен-эффективность: effort `high` по умолчанию, `max` для Pro-плана/review; Read/Grep вместо `cat`; лимиты вывода; дробление сессий | Снижение cache/output и латентности | Да (`~/.bashrc`) |
| REC-10 | P2 | Cleanup: архив one-off скриптов, `.backups/`, dump, audit package, old reports, ai-handoff staging; `.gitignore`; никогда `git clean -fdX` | Меньше шума/риска | Да |
| REC-11 | P1 | E2E: `libatomic1` в dev image или официальный host-runner; E2E в CI | Воспроизводимость QA | Да (Dockerfile/CI) |
| REC-12 | P0/P1 | Remote/backup для обоих репозиториев; bundle/tar вне диска | DR | Да (внешний сервис) |

---

## 6. Точные инструкции по реализации (НЕ ПРИМЕНЯТЬ без решения владельца)

### 6.1. Маршрутизация моделей

**Вариант A (рекомендуемый, opt-in Pro):** оставить Flash основной моделью, но сделать `opus` алиасом Pro.

Текущие строки `~/.bashrc:131-137`:

```bash
export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
export ANTHROPIC_MODEL="deepseek-flash[1m]"
export ANTHROPIC_DEFAULT_OPUS_MODEL="deepseek-flash[1m]"
export ANTHROPIC_DEFAULT_SONNET_MODEL="deepseek-flash[1m]"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="deepseek-flash"
export CLAUDE_CODE_SUBAGENT_MODEL="deepseek-flash"
[ -f "$HOME/.config/ba/deepseek.env" ] && . "$HOME/.config/ba/deepseek.env"
```

Предлагаемая замена только одной строки:

```bash
export ANTHROPIC_DEFAULT_OPUS_MODEL="deepseek-v4-pro"
```

Остальное без изменений: основная модель — Flash, Haiku — Flash, субагенты по умолчанию — Flash, Pro — только явно (`/model opus` или агент с `model: deepseek-v4-pro`).

**Вариант B (без изменения env):** в начале planning-сессии выполнить `/model deepseek-v4-pro`, после плана — `/model deepseek-flash[1m]` в новой сессии/субагенте. Это работает уже сейчас.

**Проверка:**

```text
/model
```

Ожидаемо: основной режим Flash; `/model opus` → `deepseek-v4-pro` (после варианта A). После пробного вызова `architect` проверить `message.model` в `~/.claude/projects/.../subagents/*.jsonl` и `meta.json`; не менять endpoint/токен.

**Важно:** Pro имеет `leading-only` обновления system/tool. Использовать его в свежей сессии/субагенте, не переключать посреди длинной tool-heavy сессии. Не менять `ANTHROPIC_AUTH_TOKEN`, endpoint и файл токена.

### 6.2. Роли и процесс

| Работа | Модель | Механизм |
|---|---|---|
| План, архитектура, БД, сложные развилки | Pro | Свежая сессия `/model deepseek-v4-pro` или агент `architect` |
| Реализация, рутина, документация | Flash | Основная сессия / `developer` |
| Независимый code review | Pro | Агент `code-reviewer`, не skill на основной модели |
| Security review | Pro | Агент `security-auditor` |
| Тесты/QA | Flash | `qa-engineer` / основная сессия |
| Отчёт | Flash | `ba-create-report` только по явной команде |

Предлагаемый новый skill `ba-plan` (создавать только после согласования):

```markdown
---
name: ba-plan
description: Подготовка плана пакета Breaktime Arcade силами Pro-архитектора перед реализацией на Flash.
tools: Read, Grep, Glob, Bash
---

# BA Plan

1. Прочитай NOW, PROJECT_STATUS, BACKLOG, точный раздел ТЗ.
2. Вызови субагента `architect` (deepseek-v4-pro) с узким брифом.
3. Сохрани результат в `docs/tasks/<TASK-ID>_PLAN.md`: пункты ТЗ,
   acceptance criteria, файлы, миграции, security/backward-compat риски,
   порядок шагов, что не входит.
4. Остановись. Реализацию выполняет Flash в отдельной сессии/агенте.
```

Обновить `ba-development`:
- шаг 4 — явная таблица моделей (Pro план, Flash реализация);
- шаг 7 — «обязательно вызови `code-reviewer` (Pro); self-review на Flash не считается независимым»;
- шаг 8 — обновить NOW, шесть реестров, `PROJECT_STATUS`; указать фактическую модель.

Обновить `ba-code-review`:
- «Для независимого review вызови субагента `code-reviewer` (Pro). Не выполняй review на основной Flash-модели».

### 6.3. Checkpoint и backup

Порядок (не выполнен):

```bash
cd /home/elkinva/projects/ba
git status --short --branch
git diff --check
git diff --stat
# Явное добавление, не git add -A:
# - 101 modified tracked
# - untracked apps/, tests/, docs/, .claude/, BA-FOUNDATION-001_REPORT.md
# - technical_specification/ — только по решению владельца
git add <явные пути>
git diff --cached --name-only
# Проверить, что .env*, certs/, creds/, reports/, audit-package, caches не в индексе
git commit -m "checkpoint: accounts, catalog, quality, docs and AI tooling before cleanup"
git tag -a checkpoint-2026-11-20 -m "Pre-cleanup checkpoint 2026-11-20"
git bundle create ~/backups/ba-20261120.bundle --all
```

Для `ai-dev` — отдельно:

```bash
cd /home/elkinva/projects/ai-dev
git status --short
# Решить судьбу M CLAUDE.md, handoff/AI-ENV-002, audit-дампов, collect_ai_environment.sh
git add <явные пути>
git commit -m "checkpoint: AI-ENV-002 rules and handoff materials"
git tag -a checkpoint-2026-11-20 -m "AI workspace checkpoint 2026-11-20"
git bundle create ~/backups/ai-dev-20261120.bundle --all
```

Не включать в Git: `reports/*.zip`, `BA-FOUNDATION-001_AUDIT_PACKAGE.txt`, `.backups/`, `project_dump*`, logs, caches, `.venv`, `node_modules`. `technical_specification/` — оригиналы ТЗ; рекомендуется включить в `ba`-checkpoint или как минимум в bundle. Не удалять и не перезаписывать.

### 6.4. NOW-контекст

Предлагаемый файл `docs/handoff/NOW.md`:

```markdown
# NOW — Breaktime Arcade
Дата: YYYY-MM-DD
Текущий пакет:
Статус: READY / IN_PROGRESS / PARTIAL / BLOCKED / AWAITING REVIEW
Следующий пакет:
Блокеры:
Решения владельца, ожидающие:
Последние фактические проверки (команда → exit code → краткий результат):
Модель текущей работы (Flash/Pro):
Git: branch / HEAD / status summary
Активные риски:
Ссылки: PROJECT_STATUS, BACKLOG, CONTEXT_RECOVERY, TASK_HISTORY
```

Правило: `NOW.md` обновляется после каждого пакета; новая сессия читает `NOW` + `PROJECT_STATUS` + `BACKLOG`, а `TASK_HISTORY`/`AUDIT_REGISTER`/`RISK_REGISTER` — только при необходимости. Это сокращает стартовый контекст с ~175 КБ до ~20–30 КБ.

### 6.5. Bash-guard / permissions

Предлагаемый минимальный Bash-хук (не создавать без согласования):
- матчер `Bash`;
- блокировать: `docker compose down -v`, `git reset --hard`, `git clean -[a-z]*[fx]`, `git push --force`, `rm -rf` вне `/tmp`, запись в `.env*`/`certs`/`creds`/`.git`/`reports`/`technical_specification`/`CLAUDE.md`, `DROP DATABASE` вне `ba_schema_check_*`, `FLUSHALL`;
- разрешить `/tmp` и явно согласованные dev-проверки;
- fail-closed.
- Альтернатива — `permissions.deny` в `.claude/settings.json`, если используемая версия Claude Code поддерживает нужные правила; проверить схему перед внедрением.
- Добавить `.claude/**` в защищённые пути (кроме явно разрешённого `settings.local.json`?) и отдельный guard для `ai-dev` с `PROJECT_ROOT=/home/elkinva/projects/ai-dev`, запретом записи в `ba`.

### 6.6. Изоляция `ai-dev`

- Запускать Claude Code из `/home/elkinva/projects/ai-dev`, чтобы проект регистрировался и транскрипты шли в отдельный каталог.
- Добавить `ai-dev/.claude/settings.json` с PreToolUse guard: запрет записи в `ba/**`, `.env*`, `certs`, `creds`, `.git`, `~/.bashrc`, `~/.claude/**`; fail-closed.
- Либо явное правило: `ai-dev` read-only по отношению к `ba`; любые изменения `ba` — только отдельная сессия с cwd `ba` и разрешением владельца.
- Не смешивать коммиты и handoff-архивы двух репозиториев.

### 6.7. Точные исправления указателей

| Файл:строка | Сейчас | Предлагается |
|---|---|---|
| `ba/README.md:6` | `docs/spec/` | `technical_specification/` + ссылка на `../ai-dev/docs/project-reference/README.md` |
| `ba/CLAUDE.md:5` | `Полное ТЗ: docs/spec/` | `Полное ТЗ: technical_specification/`; provenance — sibling `ai-dev` |
| `ba/CLAUDE.md:9-17` | устаревший «каркас/пусто/stub» | краткая ссылка на `docs/status/PROJECT_STATUS.md` + актуальный список |
| `ba/docs/handoff/CONTEXT_RECOVERY.md:67` | `ai-dev/docs/...` | `../ai-dev/docs/project-reference/README.md` |
| `ba/.claude/skills/ba-project-audit/SKILL.md:13` | `docs/project-reference/README.md` | `technical_specification/` + `../ai-dev/docs/project-reference/README.md` (read-only) |
| `ba/.claude/skills/ba-testing/SKILL.md:28-31` | «pytest/ruff/mypy отсутствуют» | «в dev-контейнере доступны; host `.venv` — для E2E; фиксируй exit code» |
| `ba/.claude/README.md:116-123` | 11 tests / 302 files / 297 mypy | 185 passed / 333 files / 316 mypy; host E2E |
| `ba/docs/tasks/TASK_HISTORY.md:3` | `BA-DOC-002` | `BA-CATALOG-005` (фактическая актуализация) |
| `ba/docs/decisions/OWNER_DECISIONS.md:11` | `BA-DOC-002` | уточнить фактическую дату/пакет |

`CLAUDE.md` и `docs/spec` защищены хуком; изменения — только с разрешения владельца.

### 6.8. Токен-эффективность

- Текущий effort `max`; для рутины рекомендуется `high`, для Pro-плана/review — `max` (если переменная контролируется в `~/.bashrc`; проверить `env` перед изменением).
- Вместо `cat/head/tail/sed` больших файлов — `Read` с `offset/limit`, `Grep`, `Glob`; для Bash-вывода — `head -n 200`, `wc -l`, `rg -m`.
- Не перечитывать `CONTEXT_RECOVERY`/`PROJECT_STATUS` в каждой сессии; использовать `NOW.md`.
- Разбивать длинные сессии на пакеты; после каждого пакета — NOW + реестры.
- Делегировать изолированный review/анализ Pro-субагенту; не загружать весь контекст в основную сессию.
- Не запускать полный `collect_ai_environment.sh` повторно без необходимости; сохранять summary/манифест.
- Логи/аудиты `ai-dev` (317/433 КБ) читать через summary/манифест, не целиком.

---

## 7. Что требует решения владельца

1. **Checkpoint:** включать ли `technical_specification/` и `.claude/` в commit `ba`; включать ли audit-дампы/handoff в commit `ai-dev`; делать ли tag/bundle.
2. **Модель:** менять ли `~/.bashrc` (`ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-v4-pro`) или использовать `/model` вручную; утвердить политику «Pro планирует/review — Flash исполняет».
3. **Independently review:** запускать ли реальный `code-reviewer`/`security-auditor` по текущему diff; принять/отклонить замечания; когда закрывать статусы AWAITING REVIEW.
4. **ai-dev:** регистрировать ли как Claude-проект; добавлять ли `.claude` guard; утвердить правило read-only к `ba`.
5. **TZ:** где канонический экземпляр в Git (R-010); обновлять ли `docs/spec` или оставить указатель на `technical_specification/`; утвердить BA-GAME-2.2/SDK/ENV.
6. **Защита:** утвердить Bash-guard/permissions и защиту `.claude/**`; разрешить/запретить `rm -rf` в dev-проверках.
7. **Контекст:** утвердить NOW.md и правки `CLAUDE.md`/`README`/skills/registry headers.
8. **Расход:** утвердить effort `high` по умолчанию и бюджет Pro; определить, какие задачи требуют Pro.
9. **E2E:** исправлять dev image (`libatomic1`) или официально перейти на host-runner; включать ли E2E в CI.
10. **Backup/remote:** выбрать внешний backup/remote для `ba` и `ai-dev` (R-008).
11. **Приоритет разработки:** продолжать BA-QUALITY-002 или сначала разблокировать App F (SDK/ENV/BA-GAME/DB-001…008).

---

## 8. Task 1 — маршрутизация моделей: подробный разбор

### 8.1. Почему основную работу выполняет Flash

1. `ANTHROPIC_MODEL=deepseek-flash[1m]` — основная модель.
2. `ANTHROPIC_DEFAULT_OPUS_MODEL` и `ANTHROPIC_DEFAULT_SONNET_MODEL` тоже Flash; `/model opus` и `/model sonnet` не дают Pro.
3. `ANTHROPIC_DEFAULT_HAIKU_MODEL` и `CLAUDE_CODE_SUBAGENT_MODEL` — Flash; субагенты по умолчанию Flash.
4. Pro-агенты (`architect`, `code-reviewer`, `security-auditor`) read-only и вызываются только явно; в основной сессии их никто не вызывает автоматически.
5. `ba-development` шаг 4 говорит «выбери модель», но не задаёт маршрут; основной агент остаётся Flash.
6. В логах Pro появляется только в трёх probe-вызовах; реальные задачи выполняет основная Flash-сессия.
7. `pickedEffortModel` у Pro-агентов = Flash[1m] — дополнительный признак того, что маршрутизация/effort не настроены прозрачно; требует проверки.

### 8.2. Что предлагается

- Pro — технический руководитель: план, архитектура, БД, сложные развилки, независимый review, security.
- Flash — реализация, рутина, чтение/поиск, тесты по готовому плану, отчёты.
- Явные артефакты: `docs/tasks/<ID>_PLAN.md` от Pro; реализация Flash; `REVIEW` от Pro; `TEST_RESULTS` от Flash/QA.
- Pro не использовать для массового чтения файлов и рутинных правок.
- Pro-сессии — свежие, из-за `leading-only`; не переключать посреди tool-heavy сессии.
- Стоимость Pro контролировать: 1 план + 1 review на пакет, не более; фиксировать модель в отчёте.

### 8.3. Проверка после внедрения

1. `/model` — отображает ожидаемую модель.
2. Пробный `architect` с узким брифом; проверить `message.model` = `deepseek-v4-pro` в subagent-транскрипте.
3. Проверить, что основная сессия остаётся Flash.
4. Проверить, что endpoint/токен не изменились.
5. Записать результат в `docs/handoff/NOW.md` или отчёт.

---

## 9. Task 2 — Skills и Agents: инвентаризация и оценка

### 9.1. Таблица

| Имя | Тип | Модель | Вызов | Фактическое использование | Проблемы | Решение |
|---|---|---|---|---|---|---|
| `ba-development` | skill | нет (caller) | Skill | 1 | Нет шага обновления реестров; модель «на выбор»; review через skill или агент неоднозначен | Добавить маршрут моделей и обязательный review-агент; добавить обновление NOW/реестров |
| `ba-code-review` | skill | нет (caller) | Skill | 0 | Может выполняться на Flash; не независимый review | Обязать `code-reviewer` (Pro); оставить как чек-лист |
| `ba-testing` | skill | нет | Skill | 0 | Устаревший blocker pytest/ruff/mypy; не различает container/host E2E | Обновить; использовать для QA-матрицы |
| `ba-debugging` | skill | нет | Skill | 0 | Нет лимита итераций fix→test | Добавить max 2–3 итерации и stop-condition |
| `ba-project-audit` | skill | нет | Skill | 0 | Неверный путь `docs/project-reference` | Исправить на `technical_specification/` + sibling provenance |
| `ba-release` | skill | нет | Skill | 0 | Полезен; не связан с моделью | Оставить; добавить ссылку на NOW |
| `ba-create-report` | skill | нет | Skill | 2 | Генератор имел устаревший boilerplate; исправлен ранее | Оставить explicit-only; обновлять при изменениях |
| `architect` | agent | v4-pro | Agent | probe/1 | Read-only; не пишет план-файл | Использовать для `ba-plan`; добавить формат плана |
| `code-reviewer` | agent | v4-pro | Agent | probe | Не вызывается на реальный diff | Сделать обязательным review-гейтом |
| `security-auditor` | agent | v4-pro | Agent | probe | Не вызывается на реальные изменения | Обязателен для security-sensitive пакетов |
| `developer` | agent | flash | Agent | probe | Не использовался реально | Использовать для изолированных файлов |
| `qa-engineer` | agent | flash | Agent | probe | Не использовался реально | Использовать для матрицы/прогонов |
| guard hook | hook | — | PreToolUse | активен | Не покрывает Bash; не защищает `.claude/**` целиком | Добавить Bash-guard; расширить protected paths |
| settings/permissions | config | — | — | активен | Нет permissions/deny; `allowedTools` пуст | Добавить deny/guard |
| pre-commit/CI | config | — | — | активен | CI без E2E; dev image без libatomic | Добавить E2E или зафиксировать host-runner |

### 9.2. Дублирование и циклы

- `ba-code-review` (skill) и `code-reviewer` (agent) — дублирование по смыслу; skill должен быть тонким чек-листом, review — только Pro-агент.
- `ba-testing` и `qa-engineer` — дублирование; skill задаёт матрицу, агент исполняет.
- `ba-development` и `developer` — skill задаёт цикл, developer исполняет изолированный участок.
- `ba-project-audit` и `architect`/`security-auditor` — разные области: общий аудит проекта vs diff/security review.
- Циклы: `ba-debugging` может зациклиться на fix→test; `ba-development` — на implement→review→fix; нужны лимиты итераций и явный stop-condition. `ba-create-report` — explicit-only, цикла нет.
- Лишней сложности немного: 7 skills + 5 agents — приемлемо; добавлять **один** `ba-plan` и **один** Bash-guard, не плодить новых агентов.

### 9.3. Потребление контекста

- Skills: 1,5–3,0 КБ; agents: 1,6–1,9 КБ. Описания всегда в списке; тела загружаются по вызову. Это не главный источник.
- Главный источник — реестры (175 КБ), tool-result (4,8 млн символов), повторные чтения и длинная основная сессия.
- Рекомендация: не увеличивать количество skills; сократить стартовый контекст через NOW; использовать subagents для изоляции.

---

## 10. Task 3 — восстановление контекста

### 10.1. Результат симуляции

Свежая read-only сессия по документам восстановила:
- цель и 11 инвариантов;
- §2.25 (0–8) и источник истины;
- текущую позицию: каркас, этап 0 не закрыт, этап 1 не завершён;
- выполненные пакеты/статусы;
- блокеры и решения владельца;
- следующий READY-пакет BA-QUALITY-002;
- пути ТЗ и SHA-256, записанные в документах;
- устаревшие указатели и противоречия.

Не восстановила: фактическое состояние кода/git/тестов; канонический BA-GAME-2.2; содержание SDK/ENV; актуальность §2.25-строки; решения владельца вне раздела A; production/legal/email/remote; точные SHA-256 на текущий момент.

### 10.2. Согласованность реестров

| Документ | Дата/пакет | Согласованность | Замечания |
|---|---|---|---|
| `PROJECT_STATUS.md` | 2026-11-19, BA-CATALOG-005 | Основной статус согласован с BACKLOG/CONTEXT/AUDIT/RISK | Coverage 81,65/177 — исторический срез; текущий отчёт 82,34/185; §9 Git snapshot 163 entries совпадает с текущими status entries |
| `CONTEXT_RECOVERY.md` | 2026-11-19, BA-CATALOG-005 | Согласован; следующий BA-QUALITY-002 | `ai-dev`-путь без `../`; очень длинный |
| `BACKLOG.md` | 2026-11-19, BA-CATALOG-005 | Согласован | Coverage 81,65 — исторический |
| `TASK_HISTORY.md` | header BA-DOC-002, content до BA-CATALOG-005 | Content согласован | Header даты устарел; отсутствуют BA-AUTONOMY-001/002 |
| `OWNER_DECISIONS.md` | header BA-DOC-002, content B.2 до TECH-CATALOG-005 | В основном согласован | Header даты; BA-AUTONOMOUS-001 не в разделе A; AI-модель-политика не записана |
| `AUDIT_REGISTER.md` | 2026-11-19, BA-CATALOG-005 | Согласован | Технические работы помечены «не аудит»; независимых review новых пакетов нет |
| `RISK_REGISTER.md` | 2026-11-19, BA-CATALOG-005 | Согласован; R-018…R-021 | Нет рисков AI-маршрутизации/контекста/кросс-репозитория — это новые риски аудита |
| `CLAUDE.md` | — | **Не согласован** | `docs/spec` пуст; «все schemas пусты»; «Views каталога — stub» |
| `README.md` | — | **Не согласован** | `docs/spec` вместо `technical_specification` |
| `.claude/README.md` | — | **Устарел** | 11 tests/302/297 vs 185/333/316; host `.venv` утверждение |
| `ba-testing/SKILL.md` | — | **Устарел** | Говорит, что pytest/ruff/mypy недоступны |
| `ba-project-audit/SKILL.md` | — | **Неверный путь** | `docs/project-reference/README.md` |

### 10.3. Минимальная система сохранения контекста

1. `docs/handoff/NOW.md` — 10–20 строк, обновляется после каждого пакета (шаблон в §6.4).
2. `CONTEXT_RECOVERY` и `CLAUDE.md` ссылаются на NOW как на первый документ; полные реестры — по требованию.
3. `PROJECT_STATUS` и `BACKLOG` остаются статусной панелью; `TASK_HISTORY`/`AUDIT_REGISTER`/`RISK_REGISTER` — детальная история.
4. В `ba-development` шаг завершения: обновить NOW + шесть реестров + `PROJECT_STATUS`; указать модель и фактические команды.
5. Один раз исправить указатели; commit docs/`.claude`; bundle.
6. Ожидаемый эффект: стартовый контекст ~20–30 КБ вместо ~175 КБ; новая сессия быстрее выходит на текущий пакет, меньше риск дрейфа.

---

## 11. Task 4 — связь `ba` и `ai-dev`

### 11.1. Карта зависимостей

```text
ba/technical_specification/  (оригиналы ТЗ, untracked)
        │  копирование + SHA-256/cmp
        ▼
ai-dev/docs/project-reference/  (tracked копии + provenance README)
        ▲
        │  read-only ссылка (сейчас сломанный относительный путь)
ba/docs/handoff/CONTEXT_RECOVERY.md

ba/docs/  ── read-only ссылки ──▶  ai-dev provenance
ai-dev/handoff/*  ──▶  ~/ai-handoff/TASK-ID-RESULTS.zip  (вне репозиториев)
```

- Кодовых импортов, submodule, symlink, общих Git-историй и remote нет.
- `ai-dev` не является частью `ba`; `ba` не зависит от `ai-dev` для runtime.
- `ai-dev` зависит от `ba` только как от источника ТЗ и объекта аудита; `ba` ссылается на `ai-dev` только за provenance.

### 11.2. Происхождение и идентичность ТЗ

- `ba/technical_specification/ts_site.txt` — 169 360 байт, SHA-256 `17d2caa0092c3db5071cadd18c22eab22662cb408ca3e216962692c0f26c7090`.
- `ba/technical_specification/ts_game.txt` — 34 712 байт, SHA-256 `40e6d4256090d312d22b42162e9e3cf118c5814c3ee4f110a0d30ca247a826db`.
- `ai-dev/docs/project-reference/` — те же размеры и SHA-256; копии tracked.
- `ai-dev/docs/project-reference/README.md` фиксирует: копии из `ba/technical_specification/`, оригиналы не изменялись, `cmp`/SHA-256 совпадают; с ChatGPT-оригиналами совпадает только построчный текст (CRLF/финальный newline).
- `BA-SDK-1.1`/`BA-ENV-1.1` отсутствуют; BA-GAME-2.2 — два варианта, эталон не выбран.

### 11.3. Дублирование и риск рассинхронизации

- Дублирование: ТЗ в двух местах (оригинал untracked в `ba`, копия tracked в `ai-dev`); `docs/spec` в `ba` пуст; `docs/project-reference` в `ba` отсутствует.
- Риск R-010: нет единого канонического места; оригиналы `ba` untracked; копии `ai-dev` tracked; если `ba/technical_specification` изменится, копии `ai-dev` устареют, а handoff-скрипт заметит расхождение только при сборке.
- Положительно: `ai-dev` README и handoff-скрипт проверяют SHA/cmp; есть история версий; `ai-dev` Git сохраняет копии.

### 11.4. Git-независимость и правила обновления

- Истории независимы; HEAD разные; remote/submodule нет.
- `ba` — продуктовый репозиторий; `ai-dev` — AI workspace, не часть продукта.
- Безопасные правила:
  1. ТЗ неизменяемы; новая редакция — новый файл с версией; обновить provenance README (размер, SHA-256, дата, что заменяет).
  2. Сначала обновляется оригинал в `ba` (или официально выбранное каноническое место), затем копия в `ai-dev`; проверка `cmp -s` + SHA-256.
  3. Не редактировать копии `ai-dev` вручную; не редактировать `ba/technical_specification` без решения владельца.
  4. `ai-dev` read-only по отношению к `ba`; изменения `ba` — только из сессии с cwd `ba`.
  5. Отдельные commit/tag/bundle для каждого репозитория; не смешивать.
  6. Handoff ZIP — вне репозиториев; проверять `unzip -t` + `sha256sum -c`; не включать секреты.
  7. Зафиксировать каноническое место ТЗ в `OWNER_DECISIONS` (R-010) и в `NOW`.

---

## 12. Task 5 — анализ расхода токенов

### 12.1. Методика и ограничения

- Источник: 8 JSONL-транскриптов `ba` + 5 subagent-транскриптов; cost-state снимки; `~/.claude.json`.
- Dedup assistant-сообщений по `message.id`; usage суммируется по модели; cost-state — последний снимок на сессию.
- `ai-dev` не имеет собственных транскриптов; его работа определяется по путям в сессиях `ba`.
- Cost-state — расчёт Claude Code, не счёт провайдера; фактические списания не проверялись.
- Текущая сессия частичная; симуляция контекста добавила 98 155 subagent-токенов.

### 12.2. Распределение работы между моделями

- Основная работа — Flash: 2080 сообщений, 2,16 млн input, 3,12 млн output, 636 млн cache-read.
- Pro — 8 сообщений, 20,2 тыс. input, 2,5 тыс. output, 32,4 тыс. cache-read, $0,179; только probe.
- Pro = 0,04 % расчётной стоимости; Flash = 99,96 %.
- Причина: конфигурация + отсутствие процесса (см. Task 1).

### 12.3. Основные источники расхода

1. Одна длинная сессия `2b3837d2`: 72,6 % стоимости, 1495 сообщений, 480 млн cache-read; длинный контекст повторно отправляется.
2. Работы `ai-dev` под `ba`: 26,4 % стоимости; три сессии; все Flash; много Bash/Edit/Write.
3. Bash как file-reader: 1546 вызовов, 1141 с file-reading паттернами; tool-result 4,8 млн символов; крупные выводы до 106 КБ.
4. Повторные чтения: `collect_ai_environment.sh` 23 раза, `create-handoff.sh` 6, `ts_site.txt` 4, `create_report.py` 4.
5. Effort `max`: 1,86 млн thinking-токенов; для рутины избыточен.
6. Отсутствие Pro-делегирования: основная Flash-сессия несёт и планирование, и реализацию, и проверку.

### 12.4. Рекомендации

| P | Действие | Ожидаемый эффект |
|---|---|---|
| P1 | NOW + чтение только нужных реестров | Снижение стартового контекста в разы |
| P1 | Read/Grep с лимитами вместо `cat/head/tail` больших файлов | Меньше tool-result и cache-read |
| P1 | Дробить сессии по пакетам; после пакета — NOW/реестры | Меньше длинного повторного контекста |
| P1 | Effort `high` для рутины, `max` для Pro-плана/review | Снижение thinking/output |
| P1 | Pro — план/review; Flash — реализация | Качество без переплаты за рутину |
| P2 | Не повторять полный `collect_ai_environment.sh`; хранить summary/манифест | Меньше больших выводов |
| P2 | Метрика по транскриптам: токены/стоимость по сессиям, моделям, пакетам | Управляемый бюджет |
| P2 | Кэшировать/переиспользовать результаты review, не перечитывать diff целиком | Меньше повторных Pro-вызовов |

---

## Приложение A. Команды и проверки (read-only)

Фактически выполнялись: `git status/log/diff/rev-parse/remote/ls-files/check-ignore`, `find`, `ls`, `stat`, `sha256sum`, `cmp`, `unzip -t`, `sha256sum -c`, `grep`, `sed -n`, Python-анализ JSONL (без вывода содержимого), `unzip -p` для проверки ZIP. Тесты/линтеры/миграции/Docker-команды в рамках этого аудита не запускались. Значения секретов не выводились.

## Приложение B. Инвентаризация

- `ba/.claude`: 7 skills, 5 agents, 1 hook, settings.json, README.
- `ba` root: один новый файл отчёта; остальные изменения не вносились.
- `ai-dev`: 36 tracked, 1 modified, 10 untracked; `.claude` отсутствует; handoff 1,2 МБ; reference 220 КБ; `~/ai-handoff` ZIP + 8 staging-каталогов.
- Реестры `ba`: 1 927 строк, 175 118 байт.
- TZ: `ts_site.txt` 169 360 байт, `ts_game.txt` 34 712 байт; SHA-256 совпадают с `ai-dev`.

## Приложение C. Контекст-симуляция

- Агент: read-only Explore, без исходников/git/docker/pytest/make.
- Прочитано: `CLAUDE.md`, 7 реестров, часть `docs/contracts/`, `docs/foundation/`, заголовки и §2.25 ТЗ.
- Восстановлено: цель, план, позиция, пакеты, блокеры, следующий пакет, provenance, противоречия.
- Не восстановлено: код/git/тесты, канонический BA-GAME, SDK/ENV, актуальность §2.25-строки, решения вне раздела A, production/legal/email/remote, точные SHA на момент.
- Стоимость: 98 155 subagent-токенов, 18 tool uses, 155 с.

## Приложение D. Ограничения и непроверенное

- Не перезапускались тесты/линтеры/миграции; цифры 185/82,34 % — из отчёта текущей сессии, не независимая проверка.
- Не проверялся провайдерский биллинг; cost-state — оценка.
- Не проверялись скрытые/незалогированные сессии; выводы по моделям относятся к доступным логам.
- Не проверялись production/staging/TLS/legal/email/remote.
- Не пересчитывались SHA-256 файлов; использованы записанные значения и выборочная проверка `sha256sum`.
- Не проверялась целостность всех `ai-dev` handoff ZIP, кроме `AI-ENV-002` (OK).
- Не выполнялась эксплуатация, сетевые сканирования, brute force или атаки.

## Приложение E. Заявление об изменениях

В рамках аудита не изменялись: исходники `ba`/`ai-dev`, конфигурации, `.bashrc`, `.claude/settings*`, `.env`, сертификаты, credentials, Git-индекс, история. Единственный созданный файл — этот отчёт в корне `ba`, вне product code. Секреты не выводились.
