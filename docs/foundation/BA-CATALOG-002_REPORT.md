# BA-CATALOG-002 — дополнительные жанры и теги

**Дата:** 2026-11-19  
**Статус:** **IMPLEMENTED / AWAITING INDEPENDENT REVIEW**. Self-check, не
независимый аудит и не приёмка §2.8.

## 1. Реализовано

- `GameGenre`/`GameTag` — through-модели M2M с unique constraint.
- `Game.additional_genres` и `Game.tags`.
- Фильтр `genre` матчит основной или дополнительный жанр.
- Фильтр `tag` — мультивыбор через повторяющийся query-параметр, OR.
- `tag_options` с локализованными названиями и fallback `en`; checkbox-блок
  в форме каталога.
- Миграция `catalog.0003_gamegenre_game_additional_genres_gametag_game_tags_and_more`
  применена в dev.
- 6 integration tests, включая published-only и фильтр по доп. жанру/тегу.

## 2. Фактические проверки

```text
python -m pytest
183 passed, 2 skipped in 43.70s

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

- Теги/доп. жанры ещё не создаются импортом (пайплайн отсутствует).
- FTS/`pg_trgm`, ratings/popularity, coverage badge и play runtime не
  реализованы.
- Фильтр тегов — OR, не AND; нормативная семантика мультивыбора отдельно
  не зафиксирована.

## 4. Следующий шаг

`BA-CATALOG-003`: PostgreSQL FTS + `pg_trgm` с конфигурацией языка.
