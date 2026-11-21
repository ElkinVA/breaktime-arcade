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

### Минимальная изоляция model-процессов (AUTONOMY-SECURITY-001)

Все role-вызовы `claude` запускаются с явным allowlist окружения
(`autonomy/sandbox.py`): передаются только model/provider-переменные,
процессные basics и не-секретные proxy/TLS настройки. DB, Telegram, AWS,
Django, Redis, Celery, Docker, CI/VCS и прочие секреты не наследуются;
proxy-URL с credentials отбрасываются. Architect/Developer/QA/Reviewer
запускаются только с `cwd` внутри `.autonomy/worktrees/<task>/...`;
отклоняются main checkout, относительные и выходящие за worktree пути,
symlink-escape, `.env`/`certs`/`creds`/`secrets`/`.ssh`/`.aws` и socket-файлы.

Это **прикладная**, а не OS-изоляция: дочерний процесс по-прежнему работает
от host-пользователя и может обратиться к абсолютным путям вне worktree
через инструменты/shell, не покрытые hooks. Остаточный разрыв зафиксирован
как технический долг **R-040** в `docs/risks/RISK_REGISTER.md`; до полного
автономного доверия требуется внешний sandbox (namespace/seccomp/AppArmor,
отдельный пользователь, скрытый `docker.sock`).

### Execution guards and efficiency accounting

Only the per-run task cap and wall-clock guard can stop a run:
`BA_MAX_TASKS_PER_RUN` (default 5) and `BA_MAX_RUN_SECONDS` (default 3600).
`--max-tasks` is clamped to the task cap.

`BA_MAX_TOKENS` and `BA_MAX_COST_USD` are **not stop conditions**. Actual
tokens/cost from `modelUsage` are still stored in evidence, task/run records
and `state.json` and feed `python3 -m autonomy.orchestrator metrics`.
Retry limits, the run lock, completed fingerprints and worktree gates remain
active.

### Уведомления о событиях

`orchestrator run` отправляет владельцу структурированные Telegram-события
(`task_completed`, `task_rejected`, `task_blocked`, `run_budget_stop`,
`run_stopped`, `fatal_error`). Это вспомогательный канал наблюдения: сбой
уведомлений не меняет результат задачи.

Конфигурация берётся из окружения `TELEGRAM_BOT_TOKEN` и
`TELEGRAM_CHAT_ID` (для совместимости также `TELEGRAM_OWNER_ID`) либо из
`creds/telegram.env` (0600, вне Git). Если токен/чат не заданы, событие
пишется в лог как `notification skipped`; сетевые ошибки повторяются
(с учётом `retry_after`) и затем также помечаются `skipped`. Токен и тела
ошибок очищаются от секретов и никогда не попадают в лог или сообщение.

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

Для переноса самого оркестратора `autonomy/` на отдельный VPS подготовлен
низкорисковый пакет `autonomy/vps/`: systemd **user** unit, шаблон
несекретного окружения, инструкции backup/restore state/evidence и
runbook с предпосылками. Пакет не содержит секретов, не меняет код
оркестратора и ничего не разворачивает автоматически; сервис стартует
только вручную. См. `autonomy/vps/README.md`.

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
