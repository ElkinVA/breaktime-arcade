---
name: ba-testing
description: Планирование и выполнение тестов Breaktime Arcade, регрессий, coverage и проверка результатов. Использовать перед review, после изменений и при подготовке релиза.
tools: Read, Grep, Glob, Bash
---

# BA Testing

## Матрица

- Unit: services, validators, id/immutability, permissions.
- Integration: views/API, ORM/PostgreSQL, transactions/constraints, Celery
  tasks, cache/Redis.
- E2E: публичные сценарии и CRM (marker `e2e`, Playwright), если окружение
  доступно.
- Security/edge: CSRF, CSP, origin, throttling, invalid schema, zip-slip,
  nonce/expiry, гонки и идемпотентность.

## Команды

```bash
make test
make lint
make types
./verify_stack.sh
```

Текущий известный blocker: в dev-контейнере `/opt/venv` отсутствуют
pytest/ruff/mypy; host `.venv` неполный. Не выдавай эти команды за
успешные, если они не запускались. Если доступен корректный dev-контейнер,
запусти полный набор; иначе зафиксируй exit code и причину.

## Правила результата

- Для каждой команды фиксируй exact command, exit code и краткий output.
- Не скрывай падения и не заменяй реальные тесты mock-проверками.
- Покрытие доменных модулей ориентир — ≥70% (§2.26); не заявляй цифру без
  фактического отчёта coverage.
- После fix запусти регрессию и связанные тесты; проверь отсутствие
  изменений защищённых файлов.
