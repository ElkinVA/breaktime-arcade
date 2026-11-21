# BA-APPF-002 / DB-004 + DB-001/DB-007 residuals

**Дата:** 2026-11-21
**Статус:** **TECHNICALLY ACCEPTED** (agent; code/security review ACCEPT).
**Решения:** OD-DB-004 (technical_id/host_label immutable после первой
публикации; Game физически не удаляется), DB-001 (privacy cleanup),
DB-007 (mode↔subject).

## 1. DB-004 — identity и DELETE Game

- `Game.save()` проверяет `technical_id`/`host_label` для существующей
  опубликованной записи (`published_at IS NOT NULL` или status
  published/hidden/archived); `update_fields` учитывается; INSERT не
  затрагивается.
- Migration `catalog.0009_game_identity_and_delete_guard`:
  - BEFORE UPDATE trigger `ba_game_identity_immutable`;
  - BEFORE DELETE trigger `ba_game_delete_forbidden` — Game нельзя удалить
    физически (архивирование остаётся статусом).
- Tests: draft identity change allowed; published model/raw change rejected;
  DELETE rejected; row remains.
- `GameVersion` / FK cleanup: Game delete trigger срабатывает до каскадов;
  существующий protected-session test сохраняет `ProtectedError`.

## 2. DB-001 residual — GamePlayCredit

`anonymize_user` теперь удаляет `GamePlayCredit` для
`subject_type=user, subject_id=user.id`. `GameDailyStats` — агрегат без
subject-ссылки; его исторические counters не пересчитываются (отдельный
retention/aggregate срез). Test DB-001 создаёт credit и проверяет удаление.

## 3. DB-007 residual — mode immutable

- `GameSession.save()` запрещает изменение `mode` (update_fields scoped).
- Migration `gameplay.0013_gamesession_mode_immutable` — BEFORE UPDATE
  trigger, отклоняет `NEW.mode != OLD.mode`.
- DB-001 tombstone меняет `subject_type`, но не `mode`, поэтому проходит.
- Tests: model ValidationError, raw update DatabaseError.

## 4. Проверки

```text
targeted DB-004/residuals -> 5 DB-004 + mode + DB-001 checks passed
pytest (full)             -> 439 passed, 3 skipped, 1 warning
ruff/format               -> clean
mypy                      -> Success: no issues found in 338 source files
makemigrations --check    -> No changes detected
migrate --plan            -> No planned migration operations
catalog 0009 / gameplay 0013 -> applied
```

## 5. Review

- **code-reviewer** (text-only): **ACCEPT**. Подтверждены NULL-safe
  `IS DISTINCT FROM`, universal DELETE guard, model `_state.adding`/
  `update_fields`, atomic/idempotent GamePlayCredit cleanup, mode tombstone.
- **security-auditor** (text-only): **ACCEPT**. Обходов QuerySet/raw/bulk/
  cascade нет; delete trigger не конфликтует с PROTECT; daily stats остаётся
  анонимным агрегатом. Остаток minor — citext case-only identity comparison
  и отсутствие отдельного bulk_update identity/GameDailyStats теста.

## 6. Остатки

- `GameDailyStats` после удаления `GamePlayCredit` остаётся историческим
  агрегатом; пересчёт/retention — отдельный срез.
- DELETE trigger запрещает физическое удаление всех Game, включая
  административные/тестовые; это намеренно, архивирование — статус.
- `Game` identity можно менять до первой публикации; после установки
  published_at/статуса — только DB trigger.
- GameVersion.game CASCADE остаётся, но DELETE Game блокируется
  DB-004-триггером.
- Citext identity: trigger `IS DISTINCT FROM` сравнивает case-insensitive,
  а model guard — case-sensitive; case-only change через raw SQL проходит
  trigger. Семантически citext/DNS identity case-insensitive; оставлено как
  minor, нормализация/ужесточение — будущий guard.
- `TRUNCATE`/`flush` не вызывает row-level DELETE trigger; это
  operator-level bypass, вне scope DB-004.
