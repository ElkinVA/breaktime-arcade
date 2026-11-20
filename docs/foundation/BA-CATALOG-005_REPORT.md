# BA-CATALOG-005 — unaccent, ranking, bulk refresh

**Дата:** 2026-11-19  
**Статус:** **IMPLEMENTED / AWAITING INDEPENDENT REVIEW** для пакета;
каталог в целом остаётся **PARTIAL** (ratings/popularity/play/benchmark).
Self-check, не независимый аудит и не приёмка §2.8.

## 1. Реализовано

- `Unaccent` Func в `translation_search_vector` и query-time SearchVector.
- `SearchRank` по persisted vector при поиске; sort=old сохраняет
  хронологический порядок.
- Celery Beat `catalog.refresh_catalog_search_vectors` → `refresh_search_vectors()`
  для bulk/import.
- Backfill `catalog.0005_backfill_unaccent_search_vector` (unaccent).
- 8 integration tests, включая `Café` → `Cafe` и refresh после обнуления
  вектора.

## 2. Фактические проверки

```text
python -m pytest
185 passed, 2 skipped in 46.76s

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

- Benchmark/EXPLAIN на реалистичном объёме не выполнен; GIN для
  unaccent-выражения отдельно не добавлен (используется существующий
  `search_vector` GIN).
- Поиск по всем переводам, а не строго по языку интерфейса; fallback —
  `en` для отображения.
- `SearchRank` не проверен на стабильность порядка при равных рангах.
- Ratings/popularity/coverage badge/play runtime остаются вне пакета.

## 4. Следующий шаг

`BA-QUALITY-002`: benchmark/EXPLAIN, GIN-выражение, покрытие
`hibp/health/storage/theme`.
