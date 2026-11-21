---
name: ba-development
description: Автономный цикл разработки Breaktime Arcade по утверждённому ТЗ: Pro-план, Flash-реализация, независимый Pro-review, тесты и обновление реестров.
tools: Read, Grep, Glob, Edit, Write, Bash
---

# BA Development Cycle

Работай в `/home/elkinva/projects/ba`. Не меняй защищённые файлы без
явного разрешения: `CLAUDE.md`, `technical_specification/**`, `docs/spec/**`,
`.env*`, `certs/**`, `creds/**`, глобальные настройки Claude/DeepSeek.

## Маршрутизация моделей

| Работа | Модель | Как |
|---|---|---|
| План, архитектура, БД, security-развилки | v4-pro | `ba-plan` → агент `architect` (text-only) |
| Реализация, тесты, рутина, docs | Flash | основная сессия / `developer` |
| Независимый code review | v4-pro | агент `code-reviewer` (text-only бриф + diff) |
| Security review | v4-pro | агент `security-auditor` (text-only бриф + evidence) |
| QA-прогон | Flash | `qa-engineer` / основная сессия |

Pro-агенты не используют tools (известное ограничение `leading-only`):
Flash собирает факты/дифф и передаёт их в текстовом брифе. Не выдавай
Flash-план или self-review за Pro-план/Pro-review.

## Порядок

1. Прочитай `docs/handoff/NOW.md`, `docs/status/PROJECT_STATUS.md`,
   `docs/status/BACKLOG.md`, раздел A `docs/decisions/OWNER_DECISIONS.md` и
   точный пункт ТЗ. Полные реестры — только по необходимости.
2. Сними baseline: `git status --short --branch`, `git diff --check`,
   целевые тесты/lint/types. Зафиксируй, если проверка недоступна.
3. Для medium/large, архитектурных, security- и migration-задач выполни
   `ba-plan`: Pro-архитектор готовит план, сохрани его в
   `docs/tasks/<TASK-ID>_PLAN.md`. Для мелкой механической правки достаточно
   короткого плана, но не придумывай архитектуру.
4. Реализуй минимальное изменение в рамках плана: доменная логика в
   `services/`, thin views/serializers; type hints, ruff (100, double quotes),
   mypy. Не расширяй scope.
5. Добавь/обнови тесты: happy path, edge cases, отказ, гонки,
   идемпотентность. Запусти целевые тесты, затем `make lint`, `make types`;
   для миграций — `makemigrations --check --dry-run`, `migrate --plan`.
6. Независимый review: передай `code-reviewer` (v4-pro) acceptance criteria,
   `git diff`, результаты тестов и релевантные фрагменты файлов. Для
   security-sensitive изменений — `security-auditor`. Требуй
   severity/файл:строка/сценарий отказа/исправление; self-review на Flash
   не считается.
7. Исправь замечания; максимум 2 итерации. Если после 2 итераций есть
   blocker/major — остановись, сформулируй один конкретный вопрос/эскалацию.
8. Проведи финальные проверки и зафиксируй exact command/exit code/output.
9. Обнови `docs/handoff/NOW.md`, шесть реестров и `PROJECT_STATUS.md`,
   если задача меняет контекст. Укажи, какая модель планировала,
   реализовывала и проверяла.
10. Commit/push в существующую `main` разрешены, если это следует из текущего
    задания или `OD-AUTONOMY-004` и проверки зелёные; deploy/publish/force —
    нет. Не ставь продуктовый `ACCEPTED`: техническая приёмка агента —
    `OD-AUTONOMY-003`, продуктовая/юридическая — владелец.

## Критерий завершения

- План (для medium/large) сохранён; acceptance criteria выполнены.
- Тесты/lint/types/миграционные проверки выполнены; exit codes записаны.
- Независимый Pro-review выполнен; blocker/major закрыты или эскалированы.
- Нет незакоммиченных изменений защищённых файлов.
- NOW и реестры обновлены; фактическая evidence приложена.
- Статус `IMPLEMENTED / AWAITING OWNER ACCEPTANCE`, а не `ACCEPTED`.
