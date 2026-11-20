# BA-AUTONOMY-003 — AI infrastructure report

**Дата:** 2026-11-20  
**Статус:** **IMPLEMENTED / AWAITING OWNER ACCEPTANCE**  
**План:** `docs/tasks/BA-AUTONOMY-003_PLAN.md`
**Коммиты:** `ba` `cc18dd9` (tag `ba-autonomy-003`), `ai-dev`
`d09a3f1` (tag `ai-dev-autonomy-003`); checkpoint `214af0d`/`152aa07`.  
**NOW:** `docs/handoff/NOW.md`

## 1. Итог

AI-инфраструктура приведена в рабочее состояние: Pro планирует и проверяет
в text-only режиме, Flash исполняет; добавлены guard'ы, NOW-контекст,
изоляция `ba`/`ai-dev` и исправлены устаревшие указатели. Продуктовый код
не изменялся.

## 2. Модели и фактическая маршрутизация

- Основная сессия: `deepseek-flash[1m]`.
- `ANTHROPIC_DEFAULT_OPUS_MODEL` изменён на `deepseek-v4-pro`; Sonnet,
  Haiku и subagent default — Flash. Backup: `~/backups/20261120-pre-autonomy/bashrc.bak`.
- Pro text-only план выполнен: `architect` / `deepseek-v4-pro`,
  13 836 subagent-токенов, 0 tool calls, 92 с.
- Причина text-only: v4-pro реально маршрутизируется (в subagent-логе
  `message.model=deepseek-v4-pro`), но tool-использование ненадёжно
  (`leading-only`): реальный architect выдал 11 сообщений, 0 tool_use,
  0 text и был остановлен.
- Первый security-review: `security-auditor` / `deepseek-v4-pro`,
  17 557 токенов, 0 tool calls, 193 с; VERDICT **reject (major)**.
  Findings 1–8 исправлены в guard'ах; повторный review — **accept**
  (23 624 токена, 0 tool calls, 38 с). Остаточный R-027 принят;
  owner acceptance pending.

## 3. Что изменено

### 3.1. Правила и контекст

- `CLAUDE.md`: указатель `docs/spec` → `technical_specification/`;
  актуализирован раздел состояния; добавлен AI workflow.
- `README.md`: нормативная база и provenance; ссылка на NOW.
- `docs/handoff/NOW.md`: текущий пакет, следующий шаг, блокеры, проверки,
  модели, Git и риски.
- `docs/handoff/CONTEXT_RECOVERY.md`: NOW первым; исправлен sibling-путь
  `../ai-dev/...`; раздел BA-AUTONOMY-003.
- Skills: новый `ba-plan`; обновлены `ba-development`, `ba-code-review`,
  `ba-testing`, `ba-project-audit`, `ba-debugging`.
- Agents: `architect`, `code-reviewer`, `security-auditor` — text-only
  протокол, tool-heavy задачи им не передаются.

### 3.2. Guard'ы

- `bash_guard.py`: PreToolUse Bash, fail-closed; блокирует destructive
  команды, `rm -r/-rf` вне `/tmp`, `DROP` вне test DB, write-like команды
  к `.env`, `certs`, `creds`, `.git`, `technical_specification`,
  `CLAUDE.md`, `.claude/hooks`, `.claude/settings.json`, user config,
  sibling repo; `git add` защищённых путей, `git add -A/-f`, history
  rewrite, `find -delete/-exec`, `perl -i`, `tar -C`, `unzip -o`, `patch`,
  `git apply`; проверка resolved path (shlex/expanduser/expandvars/realpath).
- `guard_protected_paths.py`: защищены `.claude/hooks` и
  `.claude/settings.json` от Edit/Write.
- `ai-dev/.claude/hooks/guard.py`: блокирует запись вне `ai-dev` (кроме
  `/tmp` и `~/ai-handoff`), запись в `ba`, секреты, destructive Bash.
- `ai-dev/.claude/settings.json` + `ai-dev/.claude/README.md`; дополнен
  `ai-dev/CLAUDE.md`.

### 3.3. Тесты guard'ов

```text
ba bash_guard        32/32 expected
ai-dev guard         29/29 expected
Edit/Write guard      7/7 expected
```

Покрыты literal-формы и evasion-кейсы из security-review: `git add .env`,
`git add -A`, `git reset HEAD --hard`, `push +ref`, `docker-compose down -v`,
`find -delete`, `perl -i`, `tar -C`, `unzip -o`, `patch`, `git apply`,
`sed -i` по hook, `mv /tmp/x .env`, `cd ../ai-dev && git add`.

## 4. Проверки проекта

```text
make test   -> exit 0; 185 passed, 2 skipped
make lint   -> exit 0; ruff check passed; 333 files formatted
make types  -> exit 0; Success: no issues found in 316 source files
```

## 5. Security review: findings и статус

Первый review — **reject (major)**. Findings и реакция:

| # | Finding | Статус |
|---|---|---|
| 1 | Обход подстроки кавычками/`$HOME`/переменными | Частично исправлено: shlex, expanduser/expandvars, realpath; косвенная сборка остаётся residual |
| 2 | Неполный перечень write-глаголов | Исправлено: find -delete/-exec, perl -i, tar -C, unzip -o, patch, git apply |
| 3 | `git add .env/-A/-f` | Исправлено: блок git add защищённых путей и -A/-f |
| 4 | Sibling git через `cd`/`GIT_DIR` | Исправлено: `cd SIBLING`, `cd ../ai-dev`, `git -C`, `GIT_WRITE` |
| 5 | Флаги rm/symlink / realpath | Частично: rm -r/-rf и resolved path; symlink-атаки требуют OS sandbox |
| 6 | Порядок флагов destructive | Исправлено: `reset ... --hard`, `push +ref/--force-with-lease`, `docker-compose`, `clean -xdf` |
| 7 | Self-disable hook | Исправлено: `.claude/hooks`/`settings.json` в protected (Bash + Edit/Write) |
| 8 | False positives | Остаточный minor: `cp sibling→~/ai-handoff`, `cd sibling && rm -rf /tmp`; рекомендуется запускать из целевого workspace |

Повторный text-only review — **accept**; блокеров нет. Остаточный риск
R-027: guard — сигнальный слой, не sandbox; Python/heredoc и косвенная
сборка путей не инспектируются. Для недоверенного кода нужен отдельный
OS/container sandbox.

## 6. Риски

- R-026: v4-pro tool-use `leading-only`; text-only протокол обязателен.
- R-027: guard эвристический, не sandbox; residual обходы.
- R-028: `ai-dev` зарегистрируется как отдельный Claude-проект только при
  запуске из его cwd; guard уже добавлен.
- R-029: дрейф контекста; NOW + правило обновления.

## 7. Что не входит

- Изменение ТЗ, продуктовых требований, legal, production, данных.
- Реализация SDK/ENV/BA-GAME/DB-001…008 без решений владельца.
- Полноценный OS sandbox для guard'ов.

## 8. Следующий шаг

1. Завершить повторный security-review и зафиксировать verdict.
2. Закоммитить инфраструктуру отдельно в `ba` и `ai-dev`.
3. Начать `APPF-SESSION-001`: GameSession + LaunchTicket +
   `POST /api/v1/sessions`, `/activate`, `/heartbeat` по §2.12.1–2.12.4.
4. Подготовить пакет решений по SDK/ENV/BA-GAME/DB-001…008 для владельца.
