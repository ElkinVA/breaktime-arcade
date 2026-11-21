# BA-APPF-002 / DB-005 + DB-007 — public name и mode↔subject

**Дата:** 2026-11-21
**Статус:** **TECHNICALLY ACCEPTED** (agent; независимый review — см. §5).
**Решения:** OD-DB-005 (публичное название 60), OD-DB-007 (разделение
user/guest/preview/autotest; preview/autotest вне публичных агрегатов).

## 1. DB-005 — длина публичного названия

`GameTranslation.name`: `max_length=128 → 60`; migration
`catalog.0008_alter_gametranslation_name` применена. Длинное manifest name
остаётся отдельным полем будущего импортёра; это не входит в текущий срез.
Тест: 60 символов проходит `full_clean`, 61 — `ValidationError`.

**Риск/guard:** migration 0008 сначала выполняет `RunPython`-проверку
`Length(name) > 60`; при найденных длинных именах она останавливается с
понятной ошибкой до `ALTER`, без усечения данных. Dev/staging с длинными
именами потребуют ручной/согласованной очистки, а не автоматического
truncation.

## 2. DB-007 — mode ↔ subject

Добавлен `GameSession` CHECK `ck_gameplay_session_mode_subject`:

| mode | допустимый subject_type |
|---|---|
| `user` | `user` |
| `guest` | `anon` |
| `preview` | `user` или `anon` (предпросмотр как гость разрешён) |
| `autotest` | `user` (служебный/тестовый аккаунт) |
| любой | `deleted` (DB-001 tombstone) |

`gameplay.0012` добавляет финальный constraint сразу с исключением для
`deleted` (иначе DB-001 tombstone при удалении аккаунта нарушал бы
user/guest branch). Промежуточная 0013-замена удалена до коммита: она была
опасна на populated DB, где уже есть tombstone-строки.

Текущий `create_session` создаёт только `user`/`guest` по фактическому
запросу; preview/autotest пока не имеют отдельного API. Constraint
фиксирует семантику для будущего CRM/autotest flow. Публичные агрегаты:
`GameResult.is_test = mode != user`, leaderboard исключает `is_test`,
popularity `credit_session` принимает только user/guest, playtime — только
mode user. Таким образом preview/autotest не попадают в агрегаты.

## 3. Тесты

- `tests/integration/test_game_session_mode_subject.py`: 5 валидных
  комбинаций (user/user, guest/anon, preview/user, preview/anon,
  autotest/user), 3 невалидных (user/anon, guest/user, autotest/anon),
  4 tombstone-комбинации (`deleted` для каждого mode) и проверка, что
  preview/autotest не кредитуют popularity.
- `tests/integration/test_catalog_translation_name.py`: 60/61 символов.
- Существующие preview result/leaderboard и DB-001 tombstone tests проходят.

## 4. Проверки

```text
targeted DB-005/007 -> 14 passed
pytest (full)       -> 433 passed, 3 skipped, 1 warning
ruff/format         -> clean; 374 files formatted
mypy                -> Success: no issues found in 338 source files
makemigrations --check -> No changes detected
migrate --plan      -> No planned migration operations
catalog 0008 / gameplay 0012 -> applied
```

## 5. Review

- **code-reviewer** (text-only): **ACCEPT**. Первая версия была
  отклонена за потенциально data-dependent 0012/0008; после rewrite —
  один финальный 0012, precheck 0008, aggregate evidence; blockers нет.
- **security-auditor** (text-only): **ACCEPT**. NULL/NOT VALID/truncation
  сняты, aggregates фильтруют по mode; остатки — tombstone в агрегатах и
  возможная смена mode через UPDATE (см. §6).

## 6. Остатки

- 0012 — финальный constraint; промежуточная 0013 удалена до коммита.
- DB-005 migration 0008 проверяет `Length(name)>60` до ALTER и падает с
  sample; production-данные с длинными именами требуют ручной очистки,
  автоматического truncation нет.
- Tombstone-сессии (`subject_type=deleted`, mode=user) не исключены из
  старых popularity-кредитов/иных агрегатов на уровне DB-007; это
  DB-001-остаток, требует отдельного aggregate/cleanup решения.
- `mode` не является immutable на уровне БД: UPDATE `(preview,user) →
  (user,user)` валиден; отдельный mode-immutability guard — будущий срез.
- preview/autotest creation flow и CRM-права пока не реализованы; constraint
  защищает только будущие записи.
