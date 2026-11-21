# BA-APPF-002 / DB-001 — tombstone-анонимизация сессий при удалении

**Дата:** 2026-11-21
**Статус:** **TECHNICALLY ACCEPTED** (agent; независимый re-review — см. §6).
**Связанные решения:** OD-DB-001 (субъект `user/anon/deleted`; сессии при
удалении — закрывать/удалять, не оставлять half-null). Решение владельца
2026-11-21: выбран вариант **tombstone-анонимизации** завершённых сессий.

## 1. Проблема

`anonymize_user` уже анонимизировал `GameResult` (subject_type=deleted, оба
FK NULL), удалял leaderboard/storage/playtime/ratings, но **не закрывал и не
анонимизировал** `GameSession` пользователя. Created/active сессии могли
оставаться активными после удаления; finished/expired сохраняли
`subject_id` UUID пользователя, то есть связь с удалённым аккаунтом.

Первый вариант (только abort created/active) был отклонён независимым
review: finished-сессии сохраняли UUID, а анонимизация результатов могла
гоняться с отправкой нового результата.

## 2. Изменение

### Модель и миграция

- `GameSession` получает `SUBJECT_DELETED = "deleted"` и choice
  `user/anon/deleted`; check constraint `ck_gameplay_session_subject`
  расширен.
- Миграция `gameplay.0011_remove_gamesession_ck_gameplay_session_subject_and_more`
  снимает/добавляет constraint и alter choices. Применена; `migrate --plan`
  пуст.

### `anonymize_user`

Внутри существующей транзакции, **до** `anonymize_user_results`:

```python
open_states = {GameSession.STATE_CREATED, GameSession.STATE_ACTIVE}
for session in GameSession.objects.select_for_update().filter(
    subject_type=GameSession.SUBJECT_USER,
    subject_id=user.id,
):
    session.subject_type = GameSession.SUBJECT_DELETED
    session.subject_id = uuid4()
    update_fields = ["subject_type", "subject_id", "updated_at"]
    if session.state in open_states:
        session.state = GameSession.STATE_ABORTED
        session.ticket_hash = None
        session.ticket_expires_at = None
        session.binding_nonce_hash = ""
        update_fields.extend([...])
    session.save(update_fields=update_fields)
```

- Все сессии пользователя (created/active/finished/expired) теряют связь с
  `user.id`: тип `deleted`, случайный per-session UUID.
- Created/active закрываются (`aborted`) и теряют ticket/binding hashes.
- Finished/expired сохраняют состояние (история), но не идентификатор.
- Anon-сессии не затрагиваются.
- Строки блокируются `select_for_update` до анонимизации результатов;
  `submit_result`/`activate_session`/`heartbeat`/`close_session` уже берут
  `select_for_update`/проверяют state и subject. Результат, закоммиченный до
  блокировки, попадает в последующий `anonymize_user_results`; после
  tombstone новая отправка получает `E_OWNERSHIP`.

## 3. Тест

`tests/integration/test_game_sessions.py::test_user_deletion_tombstones_sessions_and_keeps_finished_history`:
created/active/finished/expired → `subject_type=deleted`, разные случайные
`subject_id`; created/active → `aborted`, ticket/binding очищены;
finished/expired состояния сохранены; anon не изменена; `submit_result`
после удаления → `E_OWNERSHIP`.

## 4. Проверки

```text
pytest (full)              -> 403 passed, 3 skipped, 1 warning
ruff check / format --check-> clean; 371 files formatted
mypy                       -> Success: no issues found in 338 source files
makemigrations --check     -> No changes detected
migrate --plan             -> No planned migration operations
showmigrations gameplay    -> 0011 applied
```

## 5. Остатки

- Retention сессий/результатов по-прежнему не утверждён (APPF-OD-030);
  tombstone сохраняет историю, но не решает сроки хранения.
- `GameResult` уже имеет `subject_type=deleted` и NULL FK; его `session`
  указывает на tombstoned-сессию, что сохраняет историческую целостность.
- Строгая гарантия «ни одного результата после удаления» обеспечена
  порядком блокировок в текущем коде; отдельный DB-trigger не добавлялся.
  Отдельный `TransactionTestCase` с реальным interleaving двух транзакций
  не добавлен: тест проверяет post-hoc `E_OWNERSHIP`, а не одновременную
  конкуренцию за row lock (review note, non-blocking).

## 6. Независимый review

- Первый review: code-reviewer — **REJECT** (finished UUID, race); этим
  вызван переход к tombstone. security-auditor — **INCOMPLETE** (race,
  termination, linkability).
- Re-review после tombstone/lock: code-reviewer — **ACCEPT**;
  security-auditor — **ACCEPT**. Оба подтвердили, что linkability, race,
  termination и constraint-риски закрыты. Проверены: результат
  анонимизируется по `GameResult.user`, а не через session; subject_id не
  имеет FK на users; ownership — положительное сравнение subject_type+
  subject_id под `select_for_update`; потребители `subject_type=deleted`
  обрабатывают значение как «не user/anon» (ownership/aggregate-safe).
