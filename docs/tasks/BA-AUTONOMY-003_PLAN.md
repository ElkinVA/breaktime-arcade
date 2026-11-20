# BA-AUTONOMY-003 — AI infrastructure plan

**Статус:** PLAN / IN_PROGRESS  
**Дата:** 2026-11-20  
**План подготовлен:** `architect` (`deepseek-v4-pro`, text-only, 0 tool calls;
13 836 subagent-токенов, 92 с).  
**Реализация:** Flash. **Независимый review:** `code-reviewer` (v4-pro,
text-only) и `security-auditor` при необходимости.

## Цель

Привести AI-инфраструктуру в рабочее состояние: Pro планирует и проверяет,
Flash исполняет; guard/permissions; изоляция `ba`/`ai-dev`; NOW/реестры;
исправление устаревших указателей. Не превращать работу в бесконечное
улучшение инфраструктуры.

## Принятые решения

1. Основная сессия — Flash. Pro вызывается как text-only
   `architect`/`code-reviewer`/`security-auditor`; инструменты у Pro не
   используются.
2. `ANTHROPIC_DEFAULT_OPUS_MODEL` изменён на `deepseek-v4-pro` (backup
   `~/.bashrc`); `ANTHROPIC_MODEL`, Sonnet, Haiku и subagent default
   остаются Flash. `/model opus` → Pro; default → Flash.
3. Причина: v4-pro маршрутизируется (`message.model` подтверждён), но
   tool-использование ненадёжно (`leading-only`; реальный architect: 11
   сообщений, 0 tool_use, 0 text). Text-only — обязательный паттерн.
4. Первый продуктовый срез после инфраструктуры — `APPF-SESSION-001`
   (GameSession/LaunchTicket + `/api/v1/sessions`, `/activate`,
   `/heartbeat` по §2.12.1–2.12.4). SDK/ENV/BA-GAME для него не нужны.

## Изменения

- Skills: новый `ba-plan`; обновлены `ba-development`, `ba-code-review`,
  `ba-testing`, `ba-project-audit`.
- Agents: Pro-роли переведены в text-only; Flash-роли без изменений.
- Hooks: `bash_guard.py` (PreToolUse Bash, fail-closed); существующий
  `guard_protected_paths.py` сохранён.
- Settings: добавлен Bash hook.
- `ai-dev`: `.claude/hooks/guard.py`, `.claude/settings.json`,
  `.claude/README.md`; guard блокирует запись в `ba`, секреты и
  destructive-команды; output разрешён в `/tmp` и `~/ai-handoff`.
- Context: `docs/handoff/NOW.md`; исправлены `CLAUDE.md`, `README.md`,
  `CONTEXT_RECOVERY.md`; обновлены реестры.
- Реестры: BA-AUTONOMY-003, риски R-022…R-025, решения владельца
  OD-AUTONOMY-001/OD-MODEL-001.

## Acceptance criteria

- Pro text-only plan и review реально выполнены; `message.model` =
  `deepseek-v4-pro` в subagent-логах.
- Bash-guard и ai-dev guard проходят unit-тесты; обычные `make test`,
  `make lint`, `git status/diff/log`, `create_report`, handoff не блокируются.
- `ai-dev` имеет собственный `.claude` guard и README; запись в `ba`
  блокируется.
- NOW/README/CLAUDE/CONTEXT_RECOVERY указывают на
  `technical_specification/`; `docs/spec` не используется как ТЗ.
- Реестры согласованы; тесты/lint/types зелёные; фактические exit codes
  записаны.
- Ни один секрет не попал в артефакты; protected files не изменены без
  явной фиксации.

## Stop conditions

- Destructive command или запись в защищённый путь — остановка, откат,
  отчёт.
- Pro снова не отвечает text-only после 2 попыток — fallback на Flash-план
  с явной пометкой; вопрос владельцу.
- Противоречие требованиям ТЗ — остановка и один конкретный вопрос.
- Любое касание `.env`, `certs/`, `creds/` — остановка.

## Что не входит

- Изменение ТЗ, продуктовых требований, legal, production, данных.
- Реализация SDK/ENV/BA-GAME/DB-001…008 без решений владельца.
- Массовое удаление skills/agents; только фиксация неиспользуемых.
