# APPF-RESULT-001 — результат и таблица рекордов

**Дата:** 2026-11-20  
**Статус:** IMPLEMENTED / AWAITING OWNER ACCEPTANCE; independent review —
`code-reviewer` и `security-auditor` (deepseek-v4-pro, text-only):
**accept**, блокеров нет.  
**План:** `docs/tasks/APPF-RESULT-001_PLAN.md`  
**Основание:** BA-PLAT-4.2 §2.11–§2.13, §2.22–§2.23; OD-DB-001/002/003/005/
006/007; DB-002/003/004/008 делегированы техническому руководителю.

## 1. Итог

Реализован `POST /api/v1/sessions/{id}/result` с `Idempotency-Key`:
пользовательский результат сохраняется, сессия завершается, строка
`LeaderboardEntry` пересчитывается в той же транзакции. Гость получает
`403 E_GUEST_FORBIDDEN`, ничего не записывается. Preview/autotest
сохраняются с `is_test=true` и не попадают в рекорды.

## 2. Модели

`GameResult`: `session` OneToOne, `game`/`game_version` FK PROTECT,
`subject_type ∈ {user, anon, deleted}` (DB-001) с CHECK XOR, `user`/`anon`
FK PROTECT nullable, `epoch`, `value`, `unit`, `duration_ms`, `trust_level`,
`is_public`, `is_quarantined`, `is_test`, `idempotency_key`, `response` JSONB,
`verifier_flags`, `created_at`; `UNIQUE(session)`,
`UNIQUE(session, idempotency_key)`; частичные индексы лучших результатов.

`LeaderboardEntry`: `game`, `epoch`, `user` PROTECT, `best_result` PROTECT,
`value`, `achieved_at`, `is_public`, `trust_level`;
`UNIQUE(game, epoch, user)`; частичные индексы по value/achieved_at.

DB-002/DB-003 — Postgres-триггеры BEFORE INSERT OR UPDATE:
result ↔ session (game/version) и entry ↔ best_result
(game/epoch/user/value/created_at=achieved_at), ERRCODE 23514.

## 3. API и проверки

`POST /api/v1/sessions/{id}/result`, CSRF, `AllowAny`, throttle `results`
60/час на субъект; `Idempotency-Key` 1–128 обязателен. Тело:
`{value:int, durationMs:int, eventLog?, seed?, clientMeta?}`.

Проверки: сессия существует; гость → 403 без записи; ownership; state
active; idle/max → 410; seed (если передан) = session.seed; score range;
duration ≤max, ≥min (кроме `is_test`), autotest ≤60 с,
`|duration−credited| ≤ 5000`; идемпотентность по ключу (тот же — сохранённый
ответ, другой после завершения — 410).

Транзакция: result insert → advisory-lock (game, epoch, user) → сравнение с
предыдущим лучшим (direction + tie-break achieved_at/user_id) → upsert
entry → rank → `is_record = rank==1` → session finished.
`response` JSONB хранит ответ для replay.

DB-001: `anonymize_user_results` вызывается из
`accounts.services.profile.anonymize_user`: leaderboard rows удаляются,
results → `subject_type=deleted`, оба FK NULL. PROTECT на FK гарантирует,
что прямое удаление пользователя не осиротит данные.

## 4. Тесты (19)

Happy path + row/entry/session/response; идемпотентный повтор; другой ключ →
410; гость → 403 без строк; чужой пользователь → 403; score/duration
валидация; lower не заменяет лучший; `lower_is_better` заменяет; disabled
leaderboard; `leaderboard_only_verified`; анонимизация; CSRF; throttle 429;
seed mismatch; отсутствующий ключ; eventLog-лимиты; preview → `is_test` без
entry; trigger negative (result mismatch, foreign best_result INSERT/UPDATE);
100 параллельных результатов одного пользователя → 1 entry, максимум,
0 дублей/дедлоков.

## 5. Проверки

```text
pytest tests/integration/test_game_results.py -> 19 passed
pytest (full) -> 241 passed, 2 skipped
make lint -> All checks passed
make types -> Success: 317 source files
makemigrations --check -> No changes detected
migrate --plan -> No planned migration operations
```

## 6. Review

- `code-reviewer` — **accept** (финал); minors закрыты: liveness-семантика
  (секунды vs ms, max duration → 400), `is_test`, negative-триггеры,
  eventLog-лимиты, seed, `leaderboard_only_verified`, missing key,
  reverse 0004; вакуумный unique оставлен как декларативная страховка;
  replay rank — свойство идемпотентности.
- `security-auditor` — **accept** (финал): F-1 preview/autotest, F-2
  negative-триггеры, F-3 eventLog/seed закрыты; F-4 retention — owner item;
  F-5 PROTECT — документированное fail-safe поведение.
- Дополнительно: ранний отказ по Content-Length > 2 МиБ + 64 КиБ
  (`E_PAYLOAD_TOO_LARGE`) для result-эндпоинта.

## 7. Остаточные риски

- `trust_level=client_reported`: верификатор/реплей — следующий слой;
  anti-cheat не заявляется.
- `response` JSONB и idempotency keys растут до retention-решения владельца.
- Rank фиксируется на момент submit; последующие результаты его устаревают.
- Пересчёт при карантине/удалении результата — будущая модерация (§2.11.1).
- Гость: API отвечает 403 и не сохраняет (согласовано с §2.12.5).
