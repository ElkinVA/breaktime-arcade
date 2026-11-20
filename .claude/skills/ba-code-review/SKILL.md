---
name: ba-code-review
description: Независимый Pro-review diff Breaktime Arcade. Flash готовит бриф и evidence, вердикт выносит text-only code-reviewer (deepseek-v4-pro).
tools: Read, Grep, Glob, Bash
---

# BA Code Review

Read-only review. Не редактируй код во время review.

## Кто проверяет

Независимый вердикт выносит субагент `code-reviewer`
(`deepseek-v4-pro`) в **text-only** режиме. Flash не проверяет сам себя и
не пересказывает свои выводы как review. Если `code-reviewer` недоступен,
зафиксируй это; не подменяй Pro-review self-review на Flash.

## Что передаёт Flash

- точный пункт ТЗ и acceptance criteria;
- `git diff` и список изменённых файлов;
- фактические `make test` / `make lint` / `make types` с exit code;
- релевантные выдержки файлов (не весь проект);
- известные риски и что не проверено;
- для security-sensitive — дополнительно `security-auditor`.

## Вердикт

`VERDICT: accept | reject | incomplete` + findings:
severity (blocker/major/minor), файл:строка, сценарий отказа, исправление.
Если замечаний нет — что проверено и что не проверено.

## Правила

- Максимум 2 итерации Flash → Pro → Flash → Pro.
- Второй `reject` или противоречие — остановка и один вопрос владельцу.
- `accept` от Pro не равен `ACCEPTED` владельцем; статус —
  `IMPLEMENTED / AWAITING OWNER ACCEPTANCE`.
- Не ослабляй permissions/CSRF/CSP/секреты ради прохождения review.
