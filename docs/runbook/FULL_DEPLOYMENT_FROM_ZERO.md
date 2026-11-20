# Полное развёртывание BA с нуля на другом ПК

**Назначение:** поднять dev-окружение Breaktime Arcade на новом ПК с нуля,
получить тот же рабочий контур и продолжить разработку. Документ не является
production-инструкцией; production/staging в текущем состоянии не готовы.

**Составлено по:** текущему окружению Windows + WSL2 Ubuntu 22.04, Docker
Desktop/Engine, 2026-11-20. Полный прогон «с нуля» на чистом ПК ещё не
выполнялся; шаги, требующие проверки на новом ПК, отмечены в разделе 11.
Репозиторий — приватный GitHub `ElkinVA/breaktime-arcade`.

## 0. Что понадобится

- Windows 10/11 с WSL2 и Ubuntu 22.04 (или Linux-хост).
- Docker Engine 29.9.3 + Compose 5.7.1 (Docker Desktop с WSL integration либо
  Docker Engine внутри WSL).
- `git`, `make`, `curl`, `openssl`, `uv`, `mkcert`, Node.js 22 + npm.
- Свободный порт `8443`; порт 80 не используется.
- Доступ к приватному GitHub-репозиторию по SSH.
- Ключ DeepSeek/Anthropic-совместимого провайдера (для Claude Code); в Git
  не попадает.

## 1. Базовые пакеты в WSL/Ubuntu

```bash
sudo apt update
sudo apt install -y git make curl openssl build-essential libnss3-tools
```

Node.js 22 (через nvm или NodeSource) и uv:

```bash
# пример через nvm; можно системный Node 22
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc
nvm install 22
npm --version

curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
uv --version
```

mkcert:

```bash
sudo apt install -y mkcert   # если пакет доступен
# иначе: скачать бинарник mkcert с GitHub и положить в /usr/local/bin
mkcert -version
```

Docker: установить Docker Desktop и включить интеграцию с Ubuntu-22.04, либо
Docker Engine в WSL. Проверка:

```bash
docker --version
docker compose version
```

## 2. Доступ к GitHub и клон

Сгенерировать SSH-ключ и добавить публичную часть в GitHub → Settings → SSH
and GPG keys:

```bash
ssh-keygen -t ed25519 -C "work-pc"
cat ~/.ssh/id_ed25519.pub
ssh -T git@github.com   # ожидается: Hi ElkinVA!
```

Клонировать:

```bash
mkdir -p ~/projects && cd ~/projects
git clone git@github.com:ElkinVA/breaktime-arcade.git ba
cd ba
git status              # main, clean
git log --oneline -3
```

`ba` и `ai-dev` — разные репозитории; не смешивать.

## 3. DNS и TLS для браузера

В WSL `/etc/hosts` и в Windows
`C:\Windows\System32\drivers\etc\hosts` (от администратора) добавить:

```text
127.0.0.1 portal.test
127.0.0.1 demo.games.test
```

`*.games.test` в hosts не поддерживается wildcard’ом: добавляйте конкретные
`host_label` игр по мере необходимости. Для тестов Django DNS не нужен.

Сертификаты:

```bash
cd ~/projects/ba
make certs
```

`mkcert -install` создаёт локальный CA. Чтобы браузер Windows доверял
сертификатам, импортировать корневой CA mkcert в «Доверенные корневые
центры сертификации» текущего пользователя:

```bash
mkcert -CAROOT     # путь к rootCA.pem
# скопировать rootCA.pem в Windows и импортировать:
# certutil -addstore -user Root rootCA.pem
```

## 4. Окружение и запуск

```bash
cd ~/projects/ba
make env          # создаёт .env со случайными секретами; требует uv
make assets       # npm install + сборка Tailwind/статики
make up           # web, db, redis-cache, redis-broker, redis-throttle,
                  # worker, beat, nginx
make migrate      # явно применить миграции
make superuser    # создать администратора CRM (интерактивно)
```

`make env` не перезаписывает существующий `.env`. Не копировать `.env`,
`certs/`, `creds/` из чата/репозитория; при переносе с другого ПК —
передавать только защищённым каналом либо генерировать заново.

Проверка:

```bash
make ps
./verify_stack.sh
curl -k https://portal.test:8443/healthz
curl -k https://portal.test:8443/readyz
curl -k -o /dev/null -w '%{http_code}\n' https://portal.test:8443/en/
```

Ожидается: стек здоров, `healthz`/`/en/` — 200, `readyz` — 200 при здоровых
БД/Redis/i18n/backup.

## 5. Проверки качества (baseline)

```bash
make check        # ruff + mypy + pytest
```

Текущий ожидаемый baseline — см. `docs/handoff/NOW.md` (на 2026-11-20:
297 passed, 2 skipped, 1 warning; ruff/mypy зелёные). Если числа
отличаются — сначала смотреть `NOW.md`/`PROJECT_STATUS.md`, затем
`git log`.

## 6. Перенос данных (опционально)

Код и тесты не требуют данных. Если нужен текущий dev-контент:

1. На старом ПК: `make backup`; файл `var/backups/ba-*.dump` + SHA-256.
2. Передать дамп защищённым каналом.
3. На новом ПК поднять стек и применить миграции.
4. Восстанавливать **только в новую/пустую БД**, не перезаписывать рабочую:
   см. `docs/runbook/restore.md`. Не использовать `--clean` на `ba`.
5. Для проверки целостности — `make restore-check` (создаёт временную БД).

Не выполнять `docker compose down -v`, не удалять volumes/БД/бэкапы.

## 7. Claude Code и AI-контур

Установить Claude Code (Node 22):

```bash
npm install -g @anthropic-ai/claude-code
claude --version
```

В `~/.bashrc` (или профиле shell) задать переменные провайдера. Значения
брать из защищённого хранилища; **не коммитить**:

```bash
export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
export ANTHROPIC_AUTH_TOKEN="<ваш ключ>"
export ANTHROPIC_MODEL="deepseek-flash[1m]"
export ANTHROPIC_DEFAULT_OPUS_MODEL="deepseek-v4-pro"
export ANTHROPIC_DEFAULT_SONNET_MODEL="deepseek-flash[1m]"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="deepseek-flash"
export CLAUDE_CODE_SUBAGENT_MODEL="deepseek-flash"
```

Проверка маршрутизации:

```bash
env | grep '^ANTHROPIC_' | sed -E 's/=(.*)$/=<set>/'
```

Ожидается Flash основной, Pro через opus-алиас. Pro использовать text-only:
`architect`/`code-reviewer`/`security-auditor` получают компактный бриф,
diff, требования и результаты тестов; инструменты им не передаются
(`leading-only`).

Запуск из корня репозитория:

```bash
cd ~/projects/ba
claude
```

Проектные `.claude/skills`, `.claude/agents`, `.claude/settings.json` и hooks
подхватываются автоматически. Первый документ сессии — `docs/handoff/NOW.md`,
затем `PROJECT_STATUS.md` и `BACKLOG.md`; полные реестры — по необходимости.

## 8. Git-процесс

- Ветка `main`; remote `origin` — приватный GitHub.
- Перед коммитом: `git status`, проверка отсутствия секретов в индексе.
- Push — обычный `git push origin main`; force-push и переписывание истории
  запрещены.
- `.env`, `certs/`, `creds/`, staging-секреты, бэкапы и отчёты — вне Git
  (`.gitignore`).
- `CLAUDE.md` защищён hook’ом: правки только владельцем/с явным разрешением.

## 9. Остановка и возобновление

```bash
make down        # без удаления volumes
make up          # продолжить
make ps
```

После перезапуска ПК: Docker Desktop → `cd ~/projects/ba && make up`.
Долгие операции (тесты, сборка) — внутри контейнера через Makefile.

## 10. Что пока не готово

- `compose.prod.yml`, production Nginx/monitoring/WAL/PITR/S3 — не заполнены.
- Staging требует отдельных секретов и разрешения; staging.conf защищён.
- SDK/iframe/EventLog и ZIP pipeline (кроме preflight) ждут утверждения
  BA-SDK/ENV/GAME.
- E2E в контейнере ограничен `libatomic.so.1`; host E2E — отдельный venv.

## 11. Чек-лист продолжения на другом ПК

1. Клонировать `main` и убедиться, что рабочее дерево чистое:
   `git status`, `git log --oneline -3`.
2. Пройти разделы 1–4, получить `297 passed, 2 skipped` в `make check`.
3. Прочитать `docs/handoff/NOW.md`, затем `PROJECT_STATUS.md` и
   `BACKLOG.md`; полные реестры — по необходимости.
4. Не копировать `.env`, `certs/`, `creds/`, `var/backups/` из чата или
   старого ПК; сгенерировать заново либо передать защищённым каналом.
5. Продолжить с первого `READY`-пакета в `BACKLOG.md`
   (**BA-ZIP-EXTRACT-001**), не меняя порядок зависимостей.
6. Перед задачей — ID, критерии приёмки, файлы, тесты; после — отчёт,
   обновление NOW/шести реестров/PROJECT_STATUS, проверки и независимый
   Pro text-only review.
7. Решения владельца (BA-SDK/ENV, BA-GAME, retention, антифрод, challenge,
   staging XFF, публичный nickname) не принимать самостоятельно.
