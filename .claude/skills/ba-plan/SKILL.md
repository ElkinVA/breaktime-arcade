---
name: ba-plan
description: Pro-led plan before Breaktime Arcade implementation; produces a written plan with acceptance criteria, test matrix and stop conditions.
tools: Read, Grep, Glob, Bash
---

# BA Plan — Pro-led task design

Цель: не дать Flash самостоятельно придумать архитектуру, реализовать её,
самому проверить и объявить готовой. План готовит `architect`
(`deepseek-v4-pro`) в text-only режиме; Flash собирает факты и исполняет.

## Порядок

1. Прочитай `docs/handoff/NOW.md`, `docs/status/PROJECT_STATUS.md`,
   `docs/status/BACKLOG.md`, раздел A `docs/decisions/OWNER_DECISIONS.md` и
   точный пункт ТЗ. Не перечитывай все реестры без необходимости.
2. Собери компактный бриф для Pro:
   - ID задачи и цель;
   - точные пункты ТЗ/acceptance criteria;
   - текущее состояние файлов/моделей/URL (факты, не выводы);
   - ограничения (security, migrations, backward compatibility, secrets);
   - предлагаемый минимальный список файлов;
   - открытые вопросы и варианты.
3. Вызови субагента `architect` (`deepseek-v4-pro`) через Agent tool с
   брифом и явным указанием: **не использовать инструменты, ответить
   только текстом**. Это обход известного ограничения v4-pro
   (`leading-only`): Pro не должен зависеть от tool-вызовов.
4. Сохрани ответ Pro в `docs/tasks/<TASK-ID>_PLAN.md`. Если Pro вернул
   неполный ответ или не ответил — зафиксируй это и используй резервный
   план Flash, но не выдавай его за Pro-план; отметь в отчёте.
5. Сохрани план. В автономном main-режиме не останавливайся только из-за
   плана: продолжай реализацию в этой же сессии, если нет blocking-вопроса
   владельцу. Автор плана (Pro) не реализует его сам.

## Обязательное содержание плана

- ID, цель, статус (PLAN);
- точные ссылки на ТЗ и acceptance criteria;
- факты текущего состояния (файлы, модели, тесты);
- минимальный список изменяемых файлов и миграций;
- security/backward-compat риски;
- тестовая матрица (happy path, edge, отказ, гонки, идемпотентность);
- план review: кто проверяет (Pro `code-reviewer`/`security-auditor`),
  что передаётся на review, критерии accept/reject;
- stop conditions и лимит 2 итерации исправлений;
- что не входит в задачу;
- решения, требующие владельца (если есть).

## Запрещено

- Редактировать код или файлы в этом skill.
- Выдавать план Flash за план Pro.
- Начинать реализацию без сохранённого плана для medium/large,
  архитектурных, security- и migration-задач.
