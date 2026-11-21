# Автономный запуск разработки

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
