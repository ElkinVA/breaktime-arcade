# BA-CATALOG-004 — persisted search vector

**Дата:** 2026-11-19  
**Статус:** **PARTIAL** — persisted `search_vector`, backfill и GIN-поиск
реализованы; `unaccent`, `SearchRank`, bulk/import refresh не закрыты.
Self-check, не независимый аудит и не приёмка §2.8.

## 1. Реализовано

- `apps/catalog/signals.py`: post_save `GameTranslation` обновляет
  `search_vector` (`SearchVector` name A / short_description B /
  description C, config `simple`).
- `catalog.0004_backfill_search_vector`: `UPDATE ... to_tsvector('simple',
  ...)` для строк с NULL-вектором.
- `filter_games` добавляет `translations__search_vector=SearchQuery(simple)`
  к query-time FTS/trigram/icontains fallback.
- Тест проверяет, что созданный перевод имеет непустой `search_vector`.

## 2. Фактические проверки

```text
python -m pytest
184 passed, 2 skipped in 37.26s

python -m ruff check apps config tests
All checks passed!

python -m ruff format --check apps config tests
333 files already formatted

python -m mypy
Success: no issues found in 316 source files

python manage.py check
System check identified no issues (0 silenced).

python manage.py makemigrations --check --dry-run
No changes detected

python manage.py migrate --plan
No planned migration operations.
```

## 3. Ограничения

- `unaccent` не применяется; диакритика не нормализуется.
- `SearchRank`/весовой порядок не используется; сортировка остаётся
  new/old.
- `QuerySet.update()`/`bulk_create`/импорт не обновляют vector; нужен
  bulk-refresh/триггер.
- GIN-индекс на `search_vector` существует с `catalog.0001`, но план
  запроса на объёме не проверялся.
- Backfill не пересчитывает уже заполненные, но устаревшие векторы.

## 4. Следующий шаг

`BA-CATALOG-005`: `unaccent`, `SearchRank`, bulk/import refresh.
