# BA-CATALOG-001 — публичный каталог

**Дата:** 2026-11-19  
**Статус:** **PARTIAL** — published-only list, фильтры, поиск, detail,
genre page и HTMX partial реализованы на существующих моделях. Нет
дополнительных жанров/тегов (M2M), FTS/`pg_trgm`, рейтингов/популярности,
бейджа покрытия и play runtime. Self-check, не независимый аудит и не
приёмка §2.8/§2.9.

## 1. Реализовано

- `apps/catalog/services/catalog.py`: published-only queryset, фильтры
  genre/mobile/duration/q, сортировка new/old, localized translation с
  fallback `en`, genre options, card items.
- `/games/`: список, фильтры, поиск (минимум 2 символа), HTMX partial
  (`HX-Request`), сортировка.
- `/games/<slug>/`: поиск по `Game.slug` и `GameTranslation.slug`,
  published-only, 404 для draft/unknown.
- `/genres/<slug>/`: жанровая страница с localized fallback.
- Home: latest 6 карточек.
- 5 integration tests: published-only, фильтры, поиск, detail/404,
  fallback/escaping, genre/HTMX.

## 2. Фактические проверки

```text
python -m pytest
182 passed, 2 skipped in 31.85s

python -m ruff check apps config tests
All checks passed!

python -m ruff format --check apps config tests
331 files already formatted

python -m mypy
Success: no issues found in 314 source files

python manage.py check
System check identified no issues (0 silenced).

python manage.py makemigrations --check --dry-run
No changes detected

python manage.py migrate --plan
No planned migration operations.
```

## 3. Не реализовано / ограничения

| §2.8/§2.9 | Состояние |
|---|---|
| Дополнительные жанры и теги | В моделях нет M2M; следующий BA-CATALOG-002 |
| PostgreSQL FTS + `pg_trgm` | Поиск через `icontains`; `search_vector` не заполняется |
| Рейтинг/WR/число голосов | Модели ratings отсутствуют |
| Популярность/зачёты | Модели gameplay отсутствуют |
| Бейдж покрытия локализации | Не реализован |
| Play | App F runtime отсутствует; кнопка заменена пометкой |
| Сортировки rating/popular/votes | Недоступны; только new/old |

## 4. Следующий шаг

`BA-CATALOG-002`: M2M дополнительных жанров/тегов, фильтры и тесты.
