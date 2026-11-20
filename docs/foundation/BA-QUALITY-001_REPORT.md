# BA-QUALITY-001 — coverage и CI-порог

**Дата:** 2026-11-19  
**Статус:** **IMPLEMENTED / AWAITING INDEPENDENT REVIEW**. Self-check
исполнителя, не независимый аудит и не приёмка §2.26.

## 1. Результат

- Добавлен `make coverage`.
- `pyproject.toml`: `[tool.coverage.run]` (omit migrations/tests/`__init__`)
  и `[tool.coverage.report]` с `fail_under=70`, `show_missing=true`.
- CI уже запускает `pytest --cov=apps`; порог читается из конфигурации.

## 2. Фактический замер

```text
make coverage
TOTAL 2594 statements, 476 missed, 82 %
Required test coverage of 70.0% reached. Total coverage: 81.65%
177 passed, 2 skipped
```

Модули ниже 70 %:

| Модуль | Coverage |
|---|---|
| `apps/accounts/services/hibp.py` | 39 % |
| `apps/core/health.py` | 59 % |
| `apps/i18n/templatetags/ba_i18n.py` | 63 % |
| `apps/i18n/services/coverage.py` | 36 % |
| `apps/theme/views.py` | 40 % |
| `apps/core/storage.py` | 0 % |

Аккаунтные сервисы в основном 79–100 %; i18n-сервисы 90–97 %;
`views.py` accounts — 81 %.

## 3. Ограничения

- Порог считается по совокупности всех `apps`, а не по каждому доменному
  модулю; отдельные модули ниже 70 %.
- Coverage не доказывает корректность поведения и не заменяет E2E/аудит.
- Пустые/будущие модули (0 statements) дают 100 % и не должны считаться
  реализованными.
- E2E по умолчанию skip и не входит в coverage.

## 4. Следующий шаг

`BA-CATALOG-001`: публичный каталог (список/фильтры/поиск) на существующих
моделях, без App F/рейтингов. Параллельно можно повышать покрытие
`hibp/health/storage/i18n coverage/theme views`.
