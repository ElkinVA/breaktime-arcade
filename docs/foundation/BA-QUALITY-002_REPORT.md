# BA-QUALITY-002 — search benchmark, GIN и покрытие

**Дата:** 2026-11-21
**Статус:** **TECHNICALLY ACCEPTED** (agent, 2026-11-21); code/security
review — **ACCEPT**. Продуктовая приёмка — владелец.
**Исполнитель:** основная сессия / `deepseek-flash[1m]`.
**Основание:** `BACKLOG.md` BA-QUALITY-002; R-022; §2.8; BA-QUALITY-001.

## 1. Scope

- benchmark/EXPLAIN поиска каталога на объёме;
- проверка существующего GIN и кандидатных trigram/unaccent-индексов;
- подъём покрытия модулей ниже 70 %.

Не входит: изменение продуктовой логики поиска, fallback-семантики,
App F, ratings/popularity.

## 2. Benchmark

Dev-only команда `manage.py catalog_benchmark`:
- seed `Game`/`GameTranslation` в `transaction.atomic`, затем rollback;
- `search_vector` пересчитывается SQL `to_tsvector('simple', unaccent(...))`;
- `EXPLAIN (ANALYZE, BUFFERS)` для listing 24, fts-only, trigram-only,
  unaccent icontains, full `filter_games(q)`;
- кандидатные индексы создаются вне транзакции и всегда удаляются в finally;
- `--query` передаётся только через ORM-параметры (`SearchQuery`), `EXPLAIN
  (ANALYZE)` выполняет SELECT, не DML; `--games` ограничен 100 000;
- `ANALYZE` выполняется после seed и обновления `search_vector` в каждой
  фазе, до планов. FTS-план может выбирать Seq/Bitmap GIN в зависимости от
  cost/статистики; trigram-индекс не может обслуживать FTS-предикат. Поэтому
  вывод об индексах опирается на trigram/full планы (Seq в baseline и
  candidate) и forced-GIN план, а не на разницу fts-планов;
- валидность масштаба — до 10k строк; пересмотр при 100k+/p95 > 200 мс,
  тогда возможен immutable `unaccent` wrapper/generated column;
- stale `bench_*` индекс при SIGKILL удаляется первым `DROP ... IF EXISTS`
  следующего запуска;
- seed всегда откатывается; проверено: `bench%` игр и `bench_*` индексов
  после запуска нет.

Факты (WSL2, dev PostgreSQL 18, seed selectivity 10 %):

| Запрос | 1 000 игр | 10 000 игр |
|---|---|---|
| listing 24 | ~1.4 мс | ~13 мс |
| fts-only, persisted `search_vector` | Seq Scan 0.49 мс | Seq Scan 3.0 мс; **forced GIN Bitmap 2.37 мс** (`enable_seqscan=off`) |
| trigram-only raw name | Seq Scan 2.15 мс | Seq Scan 21.7 мс даже с `gin(name gin_trgm_ops)` |
| unaccent icontains | Seq Scan 0.74 мс | Seq Scan 7.3 мс |
| full `filter_games(q)` | ~15 мс | **~150 мс, Seq Scan** |

Выводы:

- Существующий **GIN `catalog_gam_search__7ca393_gin(search_vector)`**
  используется для FTS-ветки на 10k и ускоряет её (~2.4 vs ~3.4 мс).
- Кандидатный `gin(name gin_trgm_ops)` **не выбирается** планировщиком для
  trigram/full OR; пользы не доказано.
- `gin(unaccent(name) gin_trgm_ops)` **невозможен**: `unaccent` в БД
  `STABLE`, PostgreSQL требует IMMUTABLE; нужен отдельный immutable wrapper,
  но измеренной пользы нет.
- Full OR остаётся Seq Scan из-за `SearchVector`/`TrigramSimilarity`/
  `icontains` в OR; оптимизация требует изменения формы запроса/продуктовой
  семантики fallback — не делалось.
- **Новый индекс не добавлен.** Модели/миграции не менялись.

## 3. Coverage

До: 85.7 %, 13 модулей <70 %. После добавления тестов:
**90.88 %, ни одного модуля <70 %**.

Покрыты:
- `accounts/services/hibp` — disabled, hit/miss, invalid count, fail-closed;
- `core/health` — db/cache/broker/i18n/backup ok/missing/stale/fail;
- `core/storage` — fallback для внешних CSS-импортов;
- `theme/views` — активный хэш, 404, immutable-cache;
- `i18n/services/coverage` — published/total, zero total;
- `i18n/templatetags/ba_i18n` — контекст/ключ/язык/параметры/switcher;
- `pipeline/tasks` — success/WorkerError/timeout/cleanup/enqueue;
- `crm` backup service/tasks/commands/views — success/failure/rotation/
  restore/no-backup/missing-file;
- benchmark smoke (baseline + candidate).

## 4. Проверки

```text
pytest (full)              -> 397 passed, 3 skipped, 1 warning
coverage                  -> 90.88 %, no module < 70 %
ruff/mypy                 -> clean
catalog_benchmark 1k/10k  -> plans above; bench_* indexes dropped
```

## 5. Остатки

- Full search OR at 10k ~150 мс; Seq Scan by design of fallback OR.
  Продуктовое изменение формы запроса — отдельное решение.
- Нет immutable `unaccent` wrapper; expression GIN не добавлен.
- Benchmark command dev-only; при SIGKILL возможны orphan `bench_*` indexes;
  следующий запуск удаляет их.
- CRM backup tests mock pg_dump/pg_restore; реальный backup/restore-check
  подтверждается `make backup`/`make restore-check`.

## 6. Следующий шаг

Независимый code/security review; затем следующая READY-задача.
