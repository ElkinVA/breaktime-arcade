# Автономный запуск разработки

## Control plane: очередь задач (основной путь)

`autonomy/` — durable task queue, которую не заменяют NOW/BACKLOG.
Состояние лежит в `.autonomy/state.json` (локально, вне Git), задачи имеют
статусы `READY/RUNNING/QA/REVIEW/COMPLETED/BLOCKED`, attempts, dependencies
и fingerprint. Каждый запуск:

1. Pro Architect (`deepseek-v4-pro`, tools Read/Grep/Glob) читает репозиторий
   и создаёт конкретные `AUTONOMY-*` задачи с acceptance criteria.
2. Flash Developer (`deepseek-flash`) реализует ровно одну задачу.
3. Flash QA запускает реальные проверки.
4. Pro Reviewer (`deepseek-v4-pro`) независимо читает commit/diff и выносит
   `accept/reject`.
5. При accept задача становится `COMPLETED`, при reject — retry/BLOCKED;
   затем автоматически выбирается следующая READY.

```bash
python3 -m autonomy.orchestrator status
python3 -m autonomy.orchestrator propose
python3 -m autonomy.orchestrator enqueue --id AUTONOMY-X --title "..." \
  --priority Major --acceptance "criterion"
python3 -m autonomy.orchestrator run --max-tasks 1
python3 -m autonomy.orchestrator recover
```

Evidence с фактическими `modelUsage`, `session_id` и diff — в
`.autonomy/evidence/`. Раннер проверяет, что Architect/Reviewer реально
использовали Pro, а Developer/QA — Flash. `--dangerously-skip-permissions`
не используется. Для остановки создайте `.autonomy/STOP`.

### Жёсткие бюджеты запуска

`orchestrator run` ограничен жёсткими лимитами (значения по умолчанию
указаны в `autonomy/budget.py`); лимиты задаются окружением:

| Переменная | По умолчанию | Что ограничивает |
| --- | --- | --- |
| `BA_MAX_TASKS_PER_RUN` | `1` | задач на один запуск |
| `BA_MAX_RUN_SECONDS` | `3600` | wall-clock запуска, секунды |
| `BA_MAX_TOKENS` | `5000000` | суммарные токены (input/output/cache) |
| `BA_MAX_COST_USD` | `5.0` | расчётная стоимость API, USD |

`--max-tasks` не может превысить `BA_MAX_TASKS_PER_RUN`: CLI-запрос
усекается. Остановка происходит на ближайшей безопасной границе (между
вызовами модели); в JSON-отчёте появляется
`{"status": "stopped", "reason": "BUDGET", "budget_reason": ...}`.
Устойчивые машинные коды: `MAX_TASKS`, `WALL_CLOCK`, `TOKEN_BUDGET`,
`COST_BUDGET`. Фактические токены и стоимость берутся из `modelUsage`
(`inputTokens`, `outputTokens`, `cacheReadInputTokens`,
`cacheCreationInputTokens`, `costUSD`) и сохраняются в evidence, задаче,
run-записи и общем `state.json`.

## Почему агент останавливается

Claude Code работает **turn-based**: один ответ — один turn. Внутри turn
агент может выполнить много пакетов, но после завершения ответа он не
просыпается сам. Поэтому «продолжай» в конце каждого отчёта — это не
настройка проекта, а граница harness.

В проекте уже включено:

- `CLAUDE.md` / `.claude/README.md` — техническая автономность и
  commit/push по `OD-AUTONOMY-004`;
- `ba-development` — отчёт после крупного блока, а не после пакета;
- protected-path hooks и `bash_guard` — защита, не средство остановки.

## Вариант A: `/loop` в текущей сессии

Для периодического продолжения в рамках Claude Code:

```text
/loop 45m продолжай автономную разработку Breaktime Arcade. Выбери следующий
READY-технический пакет, реализуй, проверь, обнови реестры и commit/push main.
Останавливайся только на owner-решении, blocker или destructive-операции.
```

`45m` можно заменить на другой интервал или убрать, чтобы агент сам выбирал
паузу. Это повторяет prompt в текущей сессии и не требует отдельного сервера.

## Вариант B: background-сессия

Для действительно независимого фонового прогона:

```bash
cd ~/projects/ba
claude --bg -- "Ты автономный технический руководитель Breaktime Arcade.
Продолжай READY-пакеты без подтверждений после каждого пакета. Соблюдай
CLAUDE.md, OWNER_DECISIONS и protected-path hooks. Останавливайся только на
продуктовом/юридическом/privacy/необратимом решении, production, секретах или
blocker. После каждого крупного блока обновляй NOW/PROJECT_STATUS/реестры и
делай commit/push main после зелёных проверок."
```

Проверка/остановка:

```bash
claude agents --json
claude logs <id>
claude stop <id>
```

`--bg` требует trusted workspace и подходящего permission mode; не
использовать `--dangerously-skip-permissions`.

## Вариант C: Dev Control / сервер

`devcontrol/` уже умеет запускать `claude --bg`, вести state/events и
останавливать сессию. Telegram-канал отложен до появления доступного
сервера/прокси; на сервере можно поднять `devcontrol/bot.py` +
systemd-сервис.

## Permissions

Чтобы уменьшить число подтверждений, в `.claude/settings.json` можно добавить
узкий allowlist, например:

```json
{
  "permissions": {
    "allow": [
      "Bash(make test:*)",
      "Bash(make lint:*)",
      "Bash(make types:*)",
      "Bash(make check:*)",
      "Bash(git status:*)",
      "Bash(git diff:*)",
      "Bash(git log:*)",
      "Bash(docker compose ps:*)",
      "Bash(docker compose logs:*)"
    ]
  }
}
```

Не добавлять `Bash(*)`, `--dangerously-skip-permissions` или ослабление
hooks. Protected settings изменяются только владельцем/с явного разрешения.

## Stop-условия

- Owner decision: BA-SDK/ENV/BA-GAME, retention, production, legal/privacy,
  financial, destructive data operations, secrets.
- Blocking technical defect или security finding без безопасного обхода.
- Исчерпан лимит итераций/бюджета.
- `docker compose down -v`, удаление volumes/БД/бэкапов, force-push,
  переписывание истории — запрещены.
