# BA-APPF-002 / DB-006 — immutable GameVersion

**Дата:** 2026-11-21
**Статус:** **TECHNICALLY ACCEPTED** (agent; code-reviewer и
security-auditor — **ACCEPT**); остатки minor/owner-confirm.
**Связанное решение:** OD-DB-006 / APPF-DEC-040: content/hash/version
immutable; при удалении пользователя только `created_by` и
`manual_review_by` могут стать NULL.

## 1. Проблема

`GameVersion` объявлена immutable, но в Django-модели не было ORM-guard, а
trigger из `ba_schema.sql` (безусловный `REJECT`) конфликтовал с
`ON DELETE SET NULL` у audit-FK. Удаление пользователя, создавшего версию,
могло падать; `QuerySet.update()`/raw SQL могли изменить content/hash.

## 2. Реализация

### Модель

`GameVersion` в [apps/catalog/models/version.py](../../apps/catalog/models/version.py):

- `IMMUTABLE_FIELDS` — id, game/semver/hashes/sdk/size/manifest/entry path/
  critical bytes/supported languages/verification/reports/`manual_review_at`/
  `created_at`.
- `save()` сравнивает записываемые поля (`update_fields` учитывается) с
  persisted-значениями; content change → `ValidationError`.
- `created_by`/`manual_review_by`: разрешено только неизменное значение или
  переход в `NULL`; `NULL → user` и `A → B` запрещены.

### БД

- `catalog.0006_gameversion_immutability` создаёт trigger-функцию/trigger.
- `catalog.0007_fix_gameversion_audit_trigger` заменяет функцию корректными
  именами FK-колонок `created_by_id`/`manual_review_by_id` (0006 содержит
  ошибочные `created_by`/`manual_review_by`; 0006 не редактировался после
  применения; 0007 — немедленная замена в той же цепочке).
- Trigger проверяет все content-колонки через `IS DISTINCT FROM`; audit-FK
  разрешает только NULL; `ON DELETE SET NULL` проходит.

### Тесты

`tests/integration/test_game_version_immutability.py` — 16 тестов:
model content/audit, `update_fields`, raw QuerySet, `bulk_update` content/
audit, A→B audit, `bulk_create(update_conflicts=True)`, JSONB-выражение,
nullable-переход, no-op save, user deletion SET_NULL, trigger coverage всех
content-колонок и `prosecdef=false` (без SECURITY DEFINER).

## 3. Проверки

```text
pytest tests/integration/test_game_version_immutability.py -> 16 passed
pytest (full)      -> 419 passed, 3 skipped, 1 warning
ruff check/format  -> clean; 372 files formatted
mypy               -> Success: no issues found in 338 source files
makemigrations --check -> No changes detected
migrate --plan     -> No planned migration operations
catalog 0006/0007  -> applied
```

## 4. Review

- **architect** (text-only): dual-layer (DB trigger + save guard) accepted as
  medium package; `manual_review_at` strict-immutable recommended and kept;
  `update_fields` must be scoped; parameterized/drift coverage requested.
- **security-auditor** (text-only): **ACCEPT**. Подтверждены полный список
  content-колонок, `IS DISTINCT FROM`, audit-переходы, `prosecdef=false`,
  отсутствие обхода через QuerySet/bulk/raw/ON CONFLICT/JSONB.
- **code-reviewer** (text-only): **ACCEPT**. Подтверждены column completeness,
  NULL-safe `IS DISTINCT FROM`, audit transition matrix, `update_fields`
  scoping, ON CONFLICT/bulk paths и user-deletion SET_NULL; blockers нет.
  Minor: 0006/0007 intermediate, DRF `ValidationError` (content fields должны
  быть read-only), strict `manual_review_at`, отсутствие concurrency/reverse
  test.

## 5. Остатки

- 0006 — промежуточная ошибочная версия функции, немедленно заменённая 0007;
  при сбое 0007 между миграциями trigger может остаться неработоспособным.
  Это осознанный компромисс политики «применённые миграции не редактировать».
- `manual_review_at` нельзя изменить/обнулить (буквальное чтение OD-DB-006);
  будущий manual-review flow потребует отдельного согласованного migration.
- `GameVersion.game` имеет `CASCADE`; запрет физического удаления Game —
  DB-004, вне scope. Trigger защищает UPDATE, не DELETE; DELETE+re-INSERT с
  тем же id — известный путь вне scope (FK/retention/DB-004).
- `save()` raises `django.core.exceptions.ValidationError`; future DRF write
  APIs must expose content fields read-only or translate it to HTTP 400.
- `manual_review_at` strict immutable: future post-import review stamping
  requires a separate approved migration.
- Нет отдельного concurrency-теста `save()`-guard против raw UPDATE; DB
  trigger — авторитетный слой.
