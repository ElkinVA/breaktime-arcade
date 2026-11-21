---
name: ba-testing
description: Планирование и выполнение тестов Breaktime Arcade, регрессий, coverage и фиксация фактических результатов.
tools: Read, Grep, Glob, Bash
---

# BA Testing

## Матрица

- Unit: services, validators, id/immutability, permissions.
- Integration: views/API, ORM/PostgreSQL, transactions/constraints, Celery,
  cache/Redis.
- E2E: публичные сценарии и CRM (marker `e2e`, Playwright); dev-стек.
- Security/edge: CSRF, CSP, origin, throttling, invalid schema, zip-slip,
  nonce/expiry, гонки и идемпотентность.

## Команды

```bash
make test
make lint
make types
./verify_stack.sh
```

E2E на dev-стеке (host `.venv`, если контейнер без libatomic):

```bash
BA_E2E=1 BA_E2E_BASE_URL=https://portal.test:8443 \
  .venv/bin/python -m pytest tests/e2e -m e2e
```

Текущий факт (2026-11-21): `make test` — 403 passed, 3 skipped; `make lint` —
371 files formatted; `make types` — 338 source files. E2E в контейнере `web`
падает из-за отсутствующего `libatomic.so.1`; host-прогон — 13 passed. Не
выдавай эти команды за успешные, если они не запускались.

## Правила результата

- Для каждой команды фиксируй exact command, exit code и краткий output.
- Не скрывай падения и не заменяй реальные тесты mock-проверками.
- Coverage доменных модулей — ≥70% (§2.26); не заявляй цифру без отчёта.
- После fix запусти регрессию и связанные тесты; проверь отсутствие
  изменений защищённых файлов.
- E2E-данные dev не являются production; не маскируй cleanup под бизнес-операцию.
