# BA Dev Control

Локальный Telegram-пульт для автономной разработки Breaktime Arcade.
Бот: **@breaktime_arcade_dev_bot**. Сервис отдельный от Django и не влияет на
сайт, игры или их контейнеры.

## Что делает

- показывает статус проекта, текущую задачу, прогресс, READY/следующие задачи;
- запускает одну автономную фоновую сессию Claude Code (`claude --bg`);
- ставит на паузу, снимает паузу, безопасно останавливает сессию с
  подтверждением;
- принимает сообщения владельца и передаёт их агенту через inbox на границе
  задачи;
- присылает события задачи/ревью/блокировки/ошибки/решения владельца;
- переживает перезапуск бота: состояние в `~/.local/state/ba-devcontrol`,
  сессия Claude живёт в supervisor Claude Code.

## Архитектура

```text
Telegram (long polling)
        │  только owner_id
        ▼
devcontrol/bot.py  ──►  claude --bg | agents --json | logs | stop
        │                         │
        │                         ├─ Stop / PermissionRequest / SessionEnd hooks
        │                         └─ background session (Claude Code supervisor)
        ▼
~/.local/state/ba-devcontrol/{state.json,events.jsonl,inbox.jsonl,PAUSE}
```

- **Никакого shell из Telegram.** Бот вызывает только фиксированные `claude`
  команды; текст владельца передаётся одним аргументом промпта.
- **Одна сессия.** `fcntl.flock` + проверка `claude agents --json` не дают
  запустить второго исполнителя в том же проекте. Если в проекте уже идёт
  интерактивная сессия, `/continue` откажет — завершите её.
- **Права.** `--permission-mode acceptEdits` + `devcontrol/claude-settings.json`:
  `denyInsteadOfPrompting`, запрет bypass/auto, scoped `Read/Grep/Glob/Edit/Write(./**)`,
  узкий allow-list и deny-list; проектный `bash_guard.py` продолжает
  применяться. Запрещены правки Makefile/compose/Dockerfile/.gitignore/
  pyproject/uv.lock/CI/scripts/ТЗ/CLAUDE.md/`devcontrol/**`; запрещены
  `make up/migrate/backup`, `docker compose up/build/restart`, `docker run`,
  секретные чтения, `git add -A`, force/clean/reset. Всё, что не разрешено,
  deny-hook пишет в события и требует решения владельца.
- **Окружение.** Claude получает только `ANTHROPIC_*`, PATH/HOME/locale и
  DOCKER_HOST/CONTEXT; Telegram/DB/Redis/AWS-секреты не наследуются.
- **Секреты.** Токен читается из `creds/telegram.env` (0600, вне Git) или env;
  в логи/сообщения не попадает. Токен не передаётся в аргументах процесса.

## Подключение (делает владелец)

1. Создайте бота у **@BotFather** (`/newbot`, имя
   `breaktime_arcade_dev_bot`) и получите токен.
2. Узнайте свой Telegram user ID (например, через @userinfobot).
3. Запишите секреты **локально**, не в чат и не в Git:

   ```bash
   cd /home/elkinva/projects/ba
   python3 devcontrol/setup_token.py --verify
   ```

   Скрипт читает токен через `getpass` (ввод не отображается), создаёт
   `creds/` 0700 и `creds/telegram.env` 0600. В `--verify` вызывается `getMe`;
   сам токен не печатается.
4. Проверка конфигурации:

   ```bash
   python3 devcontrol/bot.py --check
   ```

   **Автономный запуск по умолчанию выключен** (security gate). Включить его
   может только владелец, явно приняв модель угроз:

   ```bash
   python3 devcontrol/setup_token.py --force --verify --enable-autonomous
   ```

   Тестовый код агента исполняется только в **sandbox** (test-only
   DB/Redis/Mailpit, копия кода без `.env`/certs/creds, без egress и
   docker.sock). Процесс агента (git/static/status) работает **под вашим
   пользователем**; при docker-группе это root-эквивалент для не-тестовых
   действий. Безопаснее отдельный пользователь/контейнер без
   `/var/run/docker.sock`; включайте opt-in осознанно.

5. Для systemd создайте `~/.config/ba/deepseek.env` (0600) с
   `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, model-переменными; Telegram
   token туда не кладите. Запуск:

   - вручную: `python3 devcontrol/bot.py`;
   - как systemd user service: `./devcontrol/install_service.sh`
     (для старта после загрузки WSL — `sudo loginctl enable-linger "$USER"`).

6. В Telegram: `/start`, затем `/status`. Пока в проекте активна другая
   Claude-сессия или не включён `DEVCONTROL_ALLOW_AUTONOMOUS=1`, `/continue`
   вернёт отказ.

## Сеть и Telegram API

Проверьте доступность API из WSL **и** Windows:

```bash
curl -4 -sS -o /dev/null -w '%{http_code}\n' --connect-timeout 5 https://api.telegram.org/
```

Если соединение в timeout, API блокируется провайдером/сетью — бот не сможет
работать без VPN или HTTP/HTTPS-прокси, покрывающего WSL2.

Поддерживается HTTP/HTTPS-прокси:

```bash
python3 devcontrol/setup_token.py --verify --proxy http://HOST:PORT
# или в creds/telegram.env:
TELEGRAM_PROXY=http://HOST:PORT
```

- SOCKS stdlib не поддерживает; нужен HTTP-порт прокси.
- Прокси на Windows `127.0.0.1` из WSL2-NAT обычно недоступен; используйте
  адрес Windows-хоста (default gateway) или mirrored networking.
- `setup_token.py` без `--verify` сохраняет токен и при недоступной сети;
  `--verify` теперь тоже сохраняет при сетевой ошибке (но не при 401/403).

## Команды

`/start` `/help` — справка и меню (inline-кнопки)
`/status` — статус, live-сессия, heartbeat, пауза, ожидающее решение
`/report` — последний foundation-отчёт
`/progress` — счётчики статусов BACKLOG и следующая READY
`/next` — первая READY-задача
`/tasks` — текущая + READY/BLOCKED
`/continue` — запустить автономную сессию
`/pause` — не запускать новые задачи (текущая завершится на границе)
`/resume` — снять паузу / продолжить остановленную сессию
`/stop` — подтверждение и безопасная остановка (`claude stop <id>`)
`/logs` — очищенный снимок `claude logs`
`/ask <текст>` — передать сообщение агенту (inbox)
`/whoami` — ваш Telegram ID

Статусы: `RUNNING`, `IDLE`, `PAUSED`, `BLOCKED`, `ERROR`, `REVIEW`,
`COMPLETED`.

## События и hooks

`devcontrol/claude-settings.json` добавляет hooks (не меняя проектные):

- `Stop` → `turn_done` с чистым `last_assistant_message`;
- `PermissionRequest` → `permission_request` + deny (unattended fallback);
- `SessionEnd` → `session_end`.

Агент также вызывает `python3 devcontrol/status_cli.py event ...` на
переходах задачи; бот рассылает уведомления. `/logs` — только TUI-снимок,
поэтому основным источником событий служат hooks/status_cli.

## Восстановление

- Состояние: `~/.local/state/ba-devcontrol/state.json` (атомарно, 0600).
- После перезапуска бот перечитывает состояние, проверяет
  `claude agents --json` и продолжает мониторинг.
- `/resume` после `/stop` использует **полный session UUID**
  (`claude --bg --resume <uuid>`), чтобы продолжить ту же сессию; short id
  или имя запустили бы копию.
- Пока сессия работает, follow-up не вставляется в середину turn:
  сообщение лежит в inbox и читается на границе задачи.
- Ограничение: сессии Claude переживают выход из shell, но не гарантируют
  выживание после выключения машины; после reboot — `/status`, `/resume`.

## Тесты

```bash
docker compose -f compose.yml -f compose.dev-lite.yml exec -T --user 1000:1000 \
  web python -m pytest tests/unit/test_devcontrol.py -q
docker compose -f compose.yml -f compose.dev-lite.yml exec -T --user 1000:1000 \
  web python -m ruff check devcontrol
docker compose -f compose.yml -f compose.dev-lite.yml exec -T --user 1000:1000 \
  web python -m mypy devcontrol
```

Тесты (31) используют фейковый Telegram transport и фейковый Claude
controller; живой токен для них не нужен. Покрыты owner-auth (message и
callback), повторный `/continue`, pause/resume, stop-confirm с expiry,
redaction токенов/секретов, частичный inbox/dedupe, corrupt state, hooks,
sandbox path validation/copy/compose. Один host-only sandbox-тест
пропускается в web-контейнере без git.

## Sandbox test runner

Агент не запускает `pytest`/`make test`/`docker compose exec` напрямую.
Единственный путь —

```bash
python3 devcontrol/sandbox/run_tests.py [tests/... | apps/...]
```

Runner копирует tracked/untracked файлы (кроме `.env`, `certs`, `creds`,
`docs`, `var`), поднимает private PostgreSQL/Redis/Mailpit во внутренней
compose-сети, запускает pytest в контейнере с `read_only` rootfs,
`cap_drop: ALL`, без docker.sock и без внешнего egress, затем удаляет
временный проект. Реальный прогон `tests/unit/test_plural.py` — 7 passed,
exit 0, без остатков контейнеров.

## Ограничения и остатки

- **Главный риск:** при opt-in процесс агента работает под пользователем
  (git/static/status); при docker-группе это root-эквивалент для
  не-тестовых действий. Тестовое исполнение изолировано sandbox. Запуск
  выключен по умолчанию; безопасный вариант — отдельный
  пользователь/контейнер без docker.sock. Владелец принимает риск явно
  через `--enable-autonomous`.
- Нет поддерживаемого mid-turn message injection в `--bg`; используется inbox.
- `claude logs` — сырой TUI; бот очищает ANSI/шум, но это не structured log.
- `agents --json` не содержит last-activity; heartbeat бота — отдельный.
- Токен и разрешение на автономный запуск выдаёт владелец; без них сервис
  работает в `--check`/тестовом режиме и не запускает сессии.
- Production deployment, секреты, удаление данных и D-class решения —
  только владелец.
