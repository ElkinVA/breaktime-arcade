# BA-DEVCONTROL-001 — Telegram Dev Control

**Дата:** 2026-11-20/21
**Статус:** **TECHNICALLY ACCEPTED** (agent, 2026-11-21); live setup —
токен + opt-in.
Мониторинг/отчёты/задачи/inbox/hooks работают; автономный `/continue`
включается только после `setup_token.py --enable-autonomous`. Sandbox
test runner реализован: код агента исполняется только в изолированной
среде без `.env`/certs/creds, без egress и docker.sock (R-039 снижен).
Финальный Pro-review после sandbox — ожидается.
**Исполнитель:** основная сессия / `deepseek-flash[1m]`.
**Исследование:** `claude-code-guide` (Claude Code 2.1.329) + live probes.
**Основание:** OD-DEVCONTROL-001; запрос владельца на автономную разработку и
Telegram Dev Control.

## 1. Цель

Отдельный локальный сервис для удалённого управления автономной разработкой BA:
статус, текущая задача, прогресс, отчёты, запуск/пауза/возобновление/безопасная
остановка, вопросы агенту, уведомления. Бот: `@breaktime_arcade_dev_bot`.
Не входит в Django и не влияет на сайт/игры.

## 2. Архитектура

```text
Telegram long polling ──► devcontrol/bot.py ──► claude --bg / agents --json /
        (owner id)                │              logs / stop (fixed argv)
                                  ▼
                    ~/.local/state/ba-devcontrol/
                    state.json, events.jsonl, inbox.jsonl, PAUSE
                                  ▲
        Stop / PermissionRequest / SessionEnd hooks + status_cli.py (agent)
```

- Поддерживаемый интерфейс Claude Code: `--bg` (позиционный промпт, без `-p`),
  `agents --json` (`id`, `sessionId`, `state`, `status`, `waitingFor`),
  `logs`, `stop`; resume — только полный session UUID после остановки.
- Одна сессия: `fcntl.flock` + проверка активных сессий в cwd проекта.
  При активной интерактивной сессии `/continue` отказывает.
- Runtime вне репозитория (`var/` принадлежит root из-за Docker): home state
  0700, файлы 0600, atomic temp+fsync+replace, file locks.

## 3. Файлы

| Файл | Назначение |
|---|---|
| `devcontrol/bot.py` | команды, inline-кнопки, авторизация, монитор, heartbeat |
| `devcontrol/claude.py` | `--bg`/agents/logs/stop, active/resume/reference |
| `devcontrol/store.py` | state/events/inbox, atomic, flock, dedupe |
| `devcontrol/telegram.py` | Bot API long polling, sanitization, chunking |
| `devcontrol/config.py` | env-file 0600, token/owner, runtime path |
| `devcontrol/status_cli.py` | события задачи/ревью/блокировки/pending |
| `devcontrol/setup_token.py` | getpass-ввод токена, `getMe`, 0600 |
| `devcontrol/hooks/` | Stop / PermissionRequest / SessionEnd |
| `devcontrol/sandbox/run_tests.py` | изолированный test runner: копия кода без секретов, private test DB/Redis/Mailpit, internal network, no docker.sock |
| `devcontrol/githooks/pre-push` | pre-push secret-scan |
| `devcontrol/claude-settings.json` | permissions + hooks для `--settings` |
| `devcontrol/systemd/`, `install_service.sh` | systemd user service |
| `tests/unit/test_devcontrol.py` | 31 unit tests (fakes + sandbox helpers + proxy/setup) |

## 4. Безопасность

- Только `TELEGRAM_OWNER_ID` для message и callback; username не используется;
  чужие игнорируются; `update_id`/callback id дедуп.
- Токен: `creds/telegram.env` (0700/0600, вне Git) или env; getpass; не в argv,
  не в логах; `sanitize_text` редактирует token-shape/ANSI; ошибки Telegram
  санитизируются.
- Нет shell из Telegram: только фиксированные `claude` argv; `/ask` — текст в
  inbox/prompt, не команда.
- **Автономный запуск по умолчанию выключен** (`DEVCONTROL_ALLOW_AUTONOMOUS=0`);
  `/continue`/`/resume` возвращают security-gate отказ. Включение — только
  явный `setup_token.py --enable-autonomous` с предупреждением: Claude
  работает под пользователем; при docker-группе это root-эквивалент.
  Безопасная альтернатива — отдельный пользователь/контейнер без docker.sock.
- Claude permissions: `acceptEdits` + `denyInsteadOfPrompting` +
  `disableBypassPermissionsMode` + `disableAutoMode`; scoped
  `Read/Grep/Glob/Edit/Write(./**)`; узкий allow-list; deny для
  rm/reset/clean/force/down -v/prune/sudo/pipe-to-shell/секретов,
  `git add -A`, `make up/migrate/backup`, `docker compose up/build/restart`,
  `docker run`; deny Edit/Write Makefile/compose/Dockerfile/CI/ТЗ/CLAUDE.md/
  `devcontrol/**`; проектный `bash_guard.py` наследуется.
- Env для `claude`: только `ANTHROPIC_*`, PATH/HOME/locale, DOCKER_HOST/CONTEXT;
  TELEGRAM/DB/Redis/AWS-секреты не наследуются.
- State вне repo (`~/.local/state/ba-devcontrol`); Bash `cat/head/tail/grep/rg/wc`
  удалены из allow; hook-сообщения и `/logs` проходят redaction секретов.
- Hooks: `Stop` → `turn_done`; `PermissionRequest` → событие + deny;
  `SessionEnd` → `session_end`; hook-файлы 0600 в home runtime.
- `/stop` — подтверждение, `claude stop <short-id>`; conversation сохраняется;
  `/resume` — полный UUID, не short id/name (иначе копия).
- Prompt injection через owner-сообщения ограничен permissions/hooks; текст не
  интерполируется в argv-флаги/пути.

## 5. Проверки

```text
pytest tests/unit/test_devcontrol.py -> 31 passed (1 host-only skip in web)
pytest (full)                        -> 360 passed, 3 skipped, 1 warning
sandbox runner tests/unit/test_plural.py -> 7 passed, exit 0, no leftover containers
ruff check apps config tests devcontrol -> All checks passed
ruff format --check                  -> 359 files already formatted
mypy (files apps, config, devcontrol) -> Success: 333 source files
```

Live probes (2026-11-20/21):

```text
claude --bg --name ba-bg-probe --permission-mode plan "..." ->
  backgrounded · f4c68b9e · ba-bg-probe; agents --json: id/sessionId/state;
  logs/stop работают.
claude --bg --settings devcontrol/claude-settings.json ->
  Stop hook записал turn_done ("SAFEOK", permission_mode=acceptEdits).
Широкий allow-list был отклонён Claude Code auto-mode classifier; суженный
allow-list прошёл no-tools probe.
```

Живой Telegram не тестировался: токена нет. `python3 devcontrol/bot.py --check`
и `status_cli.py status` работают; setup/install подготовлены.

## 6. Ограничения

- Нет поддерживаемого mid-turn message injection в `--bg`; `/ask` читается на
  границе задачи.
- `claude logs` — сырой TUI; бот чистит ANSI/шум, это не structured log.
- `agents --json` не содержит last-activity; heartbeat — отдельный.
- Сессии Claude не гарантируют выживание после выключения машины; после
  reboot — `/status`, `/resume` (полный UUID).
- Первый реальный автономный запуск может быть остановлен auto-mode
  classifier; бот сообщит об отказе, владелец должен одобрить permission-конфиг.
- Нет live Telegram-проверки: `api.telegram.org:443` недоступен и из WSL,
  и из Windows (TCP timeout), локального прокси нет. Добавлена поддержка
  `TELEGRAM_PROXY` (HTTP/HTTPS); `setup_token.py` сохраняет credentials при
  сетевой ошибке. Нужен VPN/прокси, покрывающий WSL2, либо запуск на хосте
  с доступом к Telegram.
- Sandbox test runner: тестовый код — только в отдельной compose-сети с
  test-only DB/Redis/Mailpit, копией кода без `.env`/certs/creds, без
  egress/docker.sock; `pytest`/`make check/test`/`docker compose exec`
  удалены из allowlist агента.
- При opt-in процесс агента работает под пользователем (git/static/status);
  при docker-группе это root-эквивалент для **не-тестовых** действий.
  Тестовое исполнение изолировано sandbox; безопаснее отдельный
  пользователь/контейнер без docker.sock.

## 7. Подключение

1. BotFather → токен `@breaktime_arcade_dev_bot`.
2. `python3 devcontrol/setup_token.py --verify` (getpass; локально).
   Автономный запуск по умолчанию выключен; для включения —
   `--force --enable-autonomous` после принятия модели угроз.
3. `python3 devcontrol/bot.py --check`.
4. `python3 devcontrol/bot.py` или `./devcontrol/install_service.sh`
   (для systemd — `~/.config/ba/deepseek.env` с ANTHROPIC_*, 0600).
5. В Telegram `/start`, `/status`; `/continue` — только когда в проекте нет
   другой активной Claude-сессии и включён opt-in.

## 8. Решение владельца

Владелец выбрал **вариант A — sandbox test runner** (2026-11-21).
Реализовано: агент исполняет тесты только в изолированной среде без
реальных секретов/egress/docker.sock; `pytest`/`make test/check`/
`docker compose exec` удалены из allowlist. Автономный запуск остаётся
opt-in (`--enable-autonomous`) после ввода токена; host-user риск процесса
агента (git/static/status) остаётся, но произвольный тестовый код — в
sandbox.

## 9. Следующий шаг

Владелец вводит токен (`setup_token.py --verify`) и выбирает A/B/C.
Параллельно BA продолжает R-035/BA-QUALITY-002.
