# BA-CATALOG-003 — FTS и pg_trgm

**Дата:** 2026-11-19  
**Статус:** **PARTIAL** — query-time FTS/trigram реализованы; persisted
`search_vector`, GIN-индекс, `unaccent` и нормативное ранжирование не
закрыты. Self-check, не независимый аудит и не приёмка §2.8.

## 1. Реализовано

- `filter_games(filters, language_code)`:
  - `SearchVector` по названию (A), short_description (B), description (C)
    с конфигурацией `Language.fts_config` или `simple`;
  - `SearchQuery(..., search_type="websearch")`;
  - `TrigramSimilarity` по названию как fallback к опечаткам;
  - `icontains` fallback для совместимости;
  - `distinct()`.
- Поиск по-прежнему минимум 2 символа, published-only.
- 7 integration tests; добавлен тест терминов из разных полей, который
  `icontains` не покрывает.

## 2. Фактические проверки

```text
python -m pytest
184 passed, 2 skipped in 35.44s

python -m ruff check apps config tests
All checks passed!

python -m ruff format --check apps config tests
332 files already formatted

python -m mypy
Success: no issues found in 315 source files

python manage.py check
System check identified no issues (0 silenced).

python manage.py makemigrations --check --dry-run
No changes detected

python manage.py migrate --plan
No planned migration operations.
```

## 3. Ограничения

| §2.8 | Состояние |
|---|---|
| `tsvector`/GIN | Вектор вычисляется в запросе; `GameTranslation.search_vector` не заполняется, GIN по выражению нет |
| `unaccent` | Не применяется в FTS-запросе |
| Ранжирование | Нет `SearchRank`/весового порядка |
| Конфигурация языка | Используется `Language.fts_config` или `simple`; fallback-пометка в CRM не реализована |
| `pg_trgm` | Trigram similarity по названию, без отдельного GIN trgm-индекса |
| Производительность | Не проверялась на объёме |

## 4. Следующий шаг

`BA-CATALOG-004`: persisted `search_vector`, GIN, `unaccent`, backfill и
ранжирование.
