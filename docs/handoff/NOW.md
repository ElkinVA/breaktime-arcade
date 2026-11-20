# NOW — Breaktime Arcade

**Дата:** 2026-11-20
**Текущий пакет:** BA-AUTONOMY-003 — AI infrastructure
**Статус:** IMPLEMENTED / AWAITING OWNER ACCEPTANCE (security review accept)

## Активная задача

Привести AI-инфраструктуру к рабочему состоянию: Pro text-only
планирует/проверяет, Flash исполняет; guard/permissions; изоляция
`ba`/`ai-dev`; NOW/реестры; исправление устаревших указателей.

## Следующий шаг

`APPF-SESSION-001` — серверный срез App F: `GameSession` + `LaunchTicket`
+ `POST /api/v1/sessions`, `/activate`, `/heartbeat` по BA-PLAT-4.2
§2.12.1–2.12.4. SDK/ENV/BA-GAME для этого среза не требуются.

## Блокеры продукта

- `BA-SDK-1.1` и `BA-ENV-1.1` отсутствуют; DRAFT не нормативны.
- Канонический вариант `BA-GAME-2.2` не выбран.
- `DB-001…DB-008` требуют решений владельца до App F-миграций.
- Legal texts/versions, email provider/bounce, CRM roles/step-up.
- Container E2E: Playwright driver без `libatomic.so.1`; host E2E — 13 passed.

## Решения владельца, ожидающие

- Смена `ANTHROPIC_DEFAULT_OPUS_MODEL` на `deepseek-v4-pro` (Pro включается
  через opus-алиас; основная модель остаётся Flash). Применяется с backup
  `~/.bashrc` и фиксируется в отчёте.
- Продуктовые/нормативные вопросы App F (SDK/ENV, BA-GAME, DB-001…008) —
  пакет рекомендаций будет подготовлен до реализации зависимых частей.

## Последние фактические проверки

```text
make lint   -> exit 0; ruff check passed; 333 files formatted
make test   -> exit 0; 185 passed, 2 skipped
make types  -> ранее exit 0; 316 source files
```

## Модели

- План: `architect` / `deepseek-v4-pro`, text-only (0 tool calls).
- Реализация: основная сессия / `deepseek-flash[1m]`.
- Security review: `security-auditor` / `deepseek-v4-pro`, text-only — **accept**.
- Code review: `code-reviewer` — не проводился отдельно; security-review покрыл guard'ы.
- Факт маршрутизации подтверждается `message.model` в subagent-транскриптах.

## Git

- `ba`: `main`, HEAD `cc18dd9` (BA-AUTONOMY-003), tag `ba-autonomy-003`;
  checkpoint `214af0d` / tag `checkpoint-2026-11-20-pre-autonomy`.
- `ai-dev`: `main`, HEAD `d09a3f1` (AI infrastructure), tag
  `ai-dev-autonomy-003`; checkpoint `152aa07` / tag
  `checkpoint-2026-11-20-pre-autonomy`.
- Финальная фиксация реестров — отдельный docs-коммит; product-код не
  изменялся.
- Backup: `~/backups/20261120-pre-autonomy/` (worktree tar + git bundles).

## Активные риски

- v4-pro tool-use ненадёжен (`leading-only`); text-only паттерн обязателен.
- Bash-guard — эвристика, не sandbox; основной контроль — review и
  минимальные права.
- App F заблокирован нормативными пробелами; нельзя выдумывать SDK/ENV.
- `ai-dev` не зарегистрирован как отдельный Claude-проект; guard добавлен,
  регистрация произойдёт при запуске из `ai-dev`.

## Ссылки

`PROJECT_STATUS.md`, `BACKLOG.md`, `CONTEXT_RECOVERY.md`, `TASK_HISTORY.md`,
`OWNER_DECISIONS.md`, `AUDIT_REGISTER.md`, `RISK_REGISTER.md`,
`docs/tasks/BA-AUTONOMY-003_PLAN.md`.
