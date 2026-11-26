# VPS transfer package: autonomy orchestrator

Низкорисковый пакет переноса **существующего** оркестратора `autonomy/` на
отдельный VPS. Пакет не меняет код оркестратора, не содержит секретов и
ничего не разворачивает автоматически.

## Состав

| Файл | Назначение |
| --- | --- |
| `ba-autonomy-orchestrator.service` | systemd **user** unit; вызывает `python3 -m autonomy.orchestrator run --max-tasks 1` |
| `orchestrator.env.example` | шаблон **несекретного** окружения (модели, бюджеты, таймауты) |
| `README.md` | этот runbook: предпосылки, установка, запуск, backup/restore |

Оркестратор запускается как есть: unit не копирует и не патчит `autonomy/`,
не содержит shell-обёрток, `ExecStartPre`/`ExecStartPost`, `git clone`,
`docker`/`compose` или деплой-команд. Установка пакета не включает
автозапуск: сервис стартует только по явной команде владельца.

## Границы и безопасность

- В unit и env-шаблоне **нет** токенов, API-ключей, паролей и приватных
  ключей. Unit ссылается только на внешние файлы `EnvironmentFile`.
- Модельные креды — `~/.config/ba/deepseek.env` (0600).
- Telegram-креды — `<repo>/creds/telegram.env` (0600), вне Git.
- `.autonomy/` (state/evidence) — локальное состояние, вне Git; может
  содержать транскрипты/диффы, поэтому резервные копии тоже 0600.
- Не добавлять `--dangerously-skip-permissions` и не ослаблять hooks.
- Пакет не деплоит портал, игры, nginx, БД и не запускает миграции.

## Предпосылки VPS

| Предпосылка | Требование / действие владельца |
| --- | --- |
| ОС | Linux с systemd и пользовательским менеджером (`systemd --user`) |
| Python | `python3` ≥ 3.11 (рекомендуется 3.14 из стека проекта); `autonomy/` использует только stdlib |
| Claude Code CLI | `claude` в `PATH` (unit добавляет `%h/.local/bin`); поддерживает `-p --agent --output-format json` |
| Провайдер модели | `~/.config/ba/deepseek.env` (0600) с `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN` и при необходимости `ANTHROPIC_*` model-переменными |
| Репозиторий | clone в `~/ba`, ветка `main`, чистое рабочее дерево; приватный доступ по SSH deploy key |
| Git identity | `git config user.name` / `user.email` для коммитов оркестратора |
| Telegram (опционально) | `~/ba/creds/telegram.env` (0600): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_OWNER_ID` или `TELEGRAM_CHAT_ID` |
| Сеть | исходящий TCP 443 к провайдеру модели и `api.telegram.org`; прокси без встроенных кредов — через `TELEGRAM_PROXY` |
| Docker (опционально) | нужен только для `devcontrol/sandbox/run_tests.py` и полного `make check`; без него QA ограничивается статическими/targeted проверками |
| Backup | каталог для state/evidence вне репозитория (например `~/backups/`) |
| Linger | `sudo loginctl enable-linger "$USER"` — только если сервис должен жить после logout/reboot |

## Установка (вручную)

Выполняется один раз владельцем. Пакет ничего не устанавливает и не
включает сам.

```bash
cd ~/ba
git pull --ff-only

# Unit
mkdir -p ~/.config/systemd/user
install -m 0644 autonomy/vps/ba-autonomy-orchestrator.service \
  ~/.config/systemd/user/ba-autonomy-orchestrator.service

# Несекретное окружение
install -d -m 700 ~/.config/ba
install -m 600 autonomy/vps/orchestrator.env.example \
  ~/.config/ba/orchestrator.env
# отредактировать при необходимости (пути/модели/бюджеты)

# Секреты владелец кладёт отдельно, вручную:
#   ~/.config/ba/deepseek.env         (0600)
#   ~/ba/creds/telegram.env           (0600)

systemctl --user daemon-reload
```

Если репозиторий расположен не в `~/ba`, измените в unit
`WorkingDirectory`, `ConditionPathExists`, `Documentation` и путь
`EnvironmentFile` (или используйте drop-in).

## Запуск и наблюдение

```bash
# Один ограниченный запуск (--max-tasks 1 внутри unit)
systemctl --user start ba-autonomy-orchestrator.service

systemctl --user status ba-autonomy-orchestrator.service
journalctl --user -u ba-autonomy-orchestrator.service -f
```

`Type=oneshot`: после завершения очередного bounded-запуска сервис
останавливается. Повторный запуск — снова вручную. Автозапуск/таймер не
входят в пакет; включать `systemctl --user enable` или timer можно только
осознанным решением владельца.

Остановка на безопасной границе — создать `/home/<user>/ba/.autonomy/STOP`
(оркестратор проверяет его между задачами). Принудительная остановка:

```bash
systemctl --user stop ba-autonomy-orchestrator.service
```

## State и evidence: backup

Состояние и evidence лежат в `~/ba/.autonomy/`. В Git они не попадают.
Останавливать сервис на время копирования обязательно, чтобы не получить
несогласованный `state.json`.

```bash
systemctl --user stop ba-autonomy-orchestrator.service

mkdir -p ~/backups
backup="$HOME/backups/autonomy-state-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
tar --create --gzip --file "$backup" --directory "$HOME/ba" \
  .autonomy/state.json \
  .autonomy/events.jsonl \
  .autonomy/evidence
chmod 600 "$backup"
sha256sum "$backup"

# Скопировать архив защищённым каналом в отдельное хранилище.
systemctl --user start ba-autonomy-orchestrator.service
```

Не включать в архив `.env`, `certs/`, `creds/`, `.autonomy/worktrees/` и
`node_modules`. Архив и его копии — 0600, не коммитить и не публиковать.
Перед внешней передачей проверьте, что evidence не содержит секретов.

## State и evidence: restore

```bash
systemctl --user stop ba-autonomy-orchestrator.service
tar --extract --gzip --file "$HOME/backups/autonomy-state-YYYYMMDDTHHMMSSZ.tar.gz" \
  --directory "$HOME/ba"
chmod -R go-rwx "$HOME/ba/.autonomy"
python3 -m json.tool "$HOME/ba/.autonomy/state.json" >/dev/null
systemctl --user start ba-autonomy-orchestrator.service
```

## Обновление кода

```bash
systemctl --user stop ba-autonomy-orchestrator.service
cd ~/ba && git pull --ff-only
systemctl --user daemon-reload   # если менялся unit
systemctl --user start ba-autonomy-orchestrator.service
```

Пакет не выполняет pull, миграции и деплой автоматически.

## WSL heartbeat (owner-approved, 30 минут)

Для локального WSL-репозитория `~/projects/ba` добавлен отдельный
user-unit комплект `autonomy/vps/wsl/`:

- `ba-autonomy-orchestrator.service` — тот же существующий
  `autonomy.orchestrator run --max-tasks 1`, с абсолютными путями
  `/home/elkinva/projects/ba`, venv Python и nvm `claude` в `PATH`;
- `ba-autonomy-orchestrator.timer` — `OnBootSec=5min`,
  `OnUnitActiveSec=30min`, `Persistent=true`.

Владелец разрешил 30-минутный heartbeat, Pro architect/reviewer +
Flash developer/QA и текущие лимиты (`max-tasks 1`,
`BA_MAX_RUN_SECONDS=3600`). Установка — только через явную команду:

```bash
systemctl --user link "$HOME/projects/ba/autonomy/vps/wsl/ba-autonomy-orchestrator.service"
systemctl --user link "$HOME/projects/ba/autonomy/vps/wsl/ba-autonomy-orchestrator.timer"
systemctl --user daemon-reload
# Сначала проверить один bounded-run:
systemctl --user start ba-autonomy-orchestrator.service
journalctl --user -u ba-autonomy-orchestrator.service -n 100 --no-pager
# Включать timer только после успешного тестового запуска:
systemctl --user enable --now ba-autonomy-orchestrator.timer
```

`~/.config/ba/deepseek.env` (0600) обязан содержать рабочие
`ANTHROPIC_BASE_URL` и `ANTHROPIC_AUTH_TOKEN` (или `ANTHROPIC_API_KEY`).
Симптом отсутствующих кредов в журнале — `Not logged in · Please run
/login`; в этом случае timer не включать. `claude` в systemd должен
находиться в `PATH`; unit уже добавляет nvm-каталог Node 22.

WSL должен быть запущен; user timer не работает после завершения WSL
или Windows. Для запуска после logout нужен `loginctl enable-linger`
(решение владельца). `STOP`-файл `.autonomy/STOP` и `run.lock`
остаются аварийным стопом и защитой от параллельных запусков.

## Проверка пакета

Статические тесты разбирают unit и env-шаблон и проверяют отсутствие
реальных токенов:

```bash
python3 devcontrol/sandbox/run_tests.py tests/unit/test_vps_transfer_package.py
```

## Остаточные предпосылки (решает владелец)

1. Предоставить VPS, пользователя, SSH-доступ и исходящий 443.
2. Установить и авторизовать `claude`; положить модельные креды в
   `~/.config/ba/deepseek.env` (0600).
3. Создать Telegram-бота/узнать owner id и положить креды в
   `creds/telegram.env` (0600), если нужны уведомления.
4. Клонировать приватный репозиторий в `~/ba`, настроить deploy key и
   git identity; убедиться, что `main` чист.
5. Решить, нужен ли Docker/Compose на VPS для sandbox-тестов и полного
   `make check`; без него QA не сможет запускать полный набор.
6. Выбрать внешнее хранилище и расписание для backup state/evidence.
7. Явно решить, включать ли `loginctl enable-linger`, `systemctl --user
   enable` и/или таймер. По умолчанию автозапуска нет.
8. Принять модель угроз: процесс агента работает от пользователя VPS;
   application-level isolation (AUTONOMY-SECURITY-001) не является
   OS-sandbox (R-040).
