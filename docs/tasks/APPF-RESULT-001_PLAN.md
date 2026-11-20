# APPF-RESULT-001 — результат и запись в таблицу рекордов

**Дата:** 2026-11-20  
**Статус:** PLAN / READY (после APPF-SESSION-002)  
**Основание:** BA-PLAT-4.2 §2.11–§2.13, §2.22–§2.23; DB-001/002/003/007
утверждены/делегированы; BA-SDK-1.1 v1.1.0 (на утверждении).

## Цель

`POST /api/v1/sessions/{id}/result` с `Idempotency-Key`: принять результат
пользователя, завершить сессию, записать `GameResult` и пересчитать
`LeaderboardEntry` в той же транзакции. Гость получает
`403 E_GUEST_FORBIDDEN`; результат не сохраняется.

## Модели (DB-001/002/003/007)

`GameResult`:
- `session` OneToOne (unique), `game` FK, `game_version` FK, `epoch`;
- `subject_type ∈ {user, anon, deleted}`; `user` FK nullable, `anon` FK
  nullable; CHECK: user→user only, anon→anon only, deleted→оба NULL
  (DB-001);
- `value`, `unit`, `duration_ms`, `trust_level`, `is_public` (default true),
  `is_quarantined` (false), `is_test` (false), `idempotency_key`,
  `response` JSONB (сохранённый ответ), `verifier_flags` JSONB, `created_at`;
- `UNIQUE(session)`, `UNIQUE(session, idempotency_key)` (§2.11.3).

`LeaderboardEntry`:
- `game`, `epoch`, `user` FK (non-null), `best_result` FK, `value`,
  `achieved_at`, `is_public`, `trust_level`;
- `UNIQUE(game, epoch, user)`; частичные индексы по value +/- и achieved_at
  (§2.11.3).

## API и проверки

`POST /api/v1/sessions/{id}/result`, same-origin, CSRF, `Idempotency-Key`
(1–128 символов). Тело: `{value:int, durationMs:int, eventLog?:object,
seed?:string, clientMeta?:object}`.

Проверки по порядку: сессия существует; принадлежит субъекту; mode=user
(guest → 403 E_GUEST_FORBIDDEN, preview/autotest — позже CRM); состояние
active; окно/срок; версия результата = версия сессии; диапазон value по
`score_min/max`; `duration_ms ≤ maxSessionSeconds*1000`,
`≥ min_session_seconds*1000` (user), `|duration−credited_ms| ≤ 5000`;
повторный ключ возвращает сохранённый ответ; другой ключ после завершения →
E_SESSION_FINISHED; rate limit 60/час субъект (Прил. E).

Транзакция: `select_for_update` сессии → проверки → создать результат →
`session.state=finished`, `finished_at` → upsert leaderboard (advisory-lock
по game/epoch/user; лучшее значение по направлению игры, тай-брейк
achieved_at ASC) → сохранить response. `is_test`/quarantined/preview не
попадают в leaderboard.

Ответ: `{status:"saved", rank, is_personal_best, is_record, trust_level}`;
`is_record=true` только если результат стал лучшим в таблице эпохи.

## Acceptance criteria

- user result: 200, `GameResult` создан, сессия finished, запись рекорда
  создана/обновлена; повтор с тем же ключом → тот же ответ, без новой строки.
- lower value не заменяет лучший результат; `lower_is_better` работает.
- гость: 403 `E_GUEST_FORBIDDEN`, строк нет.
- чужая сессия: 403 `E_OWNERSHIP`; неактивная: 410/400 по коду.
- score вне диапазона → `E_SCORE_RANGE`; duration вне допуска →
  `E_DURATION_INVALID`; version mismatch → `E_VERSION_MISMATCH`.
- 100 параллельных результатов одного пользователя: ровно один лучший,
  0 дубликатов, 0 дедлоков (§2.11.2).
- CSRF отсутствует → 403; rate limit → 429 `E_RATE_LIMIT`.
- lint/types/migrations/полный suite — зелёные.

## Вне среза

`GET` leaderboard API, storage, EventLog-персистенция/реплей, верификатор,
`UserGamePlaytime`, статистика, CRM-модерация. `trust_level` в v1 —
`client_reported`; верификатор — отдельный пакет.

## Риски

- DB-002: composite FK `(session_id, game_id)` требует UNIQUE(session.id,
  game_id); реализовать в миграции.
- DB-003: условный upsert в ORM; при 100 параллельных — advisory-lock по
  (game, epoch, user) + select_for_update.
- `response` JSONB хранит ответ бессрочно (§2.12.5); retention — до удаления
  аккаунта.
- Гонка result vs heartbeat: result завершает сессию; heartbeat после finished
  → 410.
