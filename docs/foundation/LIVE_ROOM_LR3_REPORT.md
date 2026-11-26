# Live Room LR-3 report

**Дата:** 2026-11-26. **Статус:** IMPLEMENTED; независимые code+security
review ACCEPT, QA — PASS WITH RESERVATIONS, exact-commit CI в процессе.
**Live Room не production-ready**, продуктовая приёмка владельца
остаётся обязательной.
**Модели:** implement — `deepseek-flash[1m]`; independent reviews —
`code-reviewer`/`security-auditor` (`deepseek-v4-pro`, text-only); QA —
`qa-engineer` (`deepseek-flash[1m]`).

## Что реализовано

### Идемпотентность создания

- `RoomCreateRequest`: клиентский `requestId` UUID, unique в БД, привязка к
  subject (`user`/`anon`), hash payload, room FK `SET_NULL`, TTL 7 дней.
- Ключ передаётся через SDK 1.2 `room.create({requestId})`, host bridge
  (`request_id`) и `live.js`; create intent сохраняется через SDK storage и
  восстанавливается после reload.
- Комната, host-member и idempotency-запись создаются в одной транзакции;
  параллельный тот же ключ разрешается unique-констрейнтом.
- Повтор того же subject+payload возвращает ту же комнату; другой
  subject/payload → `409 E_IDEMPOTENCY_CONFLICT`; удалённая комната →
  `410 E_IDEMPOTENCY_GONE`; истёкшая запись → `409 E_IDEMPOTENCY_EXPIRED`.
- Потеря anonymous cookie не даёт доступ по ключу и не создаёт вторую
  комнату; ключ не является access token. Cookie-loss retry получает
  conflict, пока сохраняется identity.
- `cleanup_rooms` удаляет только истёкшие idempotency-записи; комнаты
  finished/expired при валидной записи возвращают closed snapshot без
  дубликата.

### Конкурентность

`tests/integration/test_live_room_races.py` — 12 PostgreSQL-сценариев:
последнее место, параллельный ready, двойной start с одной версией,
одинаковый requestId, разные команды с одной expectedVersion, голоса,
tie, host claim, stale sweep vs vote, expiry vs join, cleanup vs read,
host start vs claim. Проверяется итоговая БД, а не только ответы.

Найден и исправлен реальный race: `read_room` мог получить
`Room.DoesNotExist` между membership-read и `select_for_update`, если
cleanup удалял комнату; теперь возвращается `E_ROOM_NOT_FOUND`.

### Load baseline

Команда `manage.py room_loadtest` создаёт 4/8/12-player комнаты и отдельную
lobby-комнату команд, измеряет read/command p50/p95/p99, QPS, SQL count,
DB lock waiters, process CPU/RSS, затем удаляет данные. Результаты,
среда, ограничения и предложенные диагностические budgets —
`docs/foundation/LIVE_ROOM_LR3_LOAD_BASELINE.md`.

Кратко: 12 игроков/1 комната, 30 s — read p95 179.8 ms, p99 507.4 ms,
0 ошибок, lock waiters max 2; 3×4 — p95 164.2 ms, p99 270.6 ms.
`read_room` не оптимизировался: измерения не показали необходимости
усложнять lock/read path.

### Crash/restart

`tests/integration/test_live_room_recovery.py` — повторный
`expire_rooms_task`, failed command без частичного state, сохранение
состояния после закрытия DB connections. Реальный dev smoke:
активная комната `RUY8Q7` (version 8, reveal) пережила `make restart`
web/worker; `expire_rooms_task` через реальный Celery worker выполнился
дважды; state/role/phase/version сохранились. Детали —
`docs/foundation/LIVE_ROOM_LR3_RECOVERY.md`.

### Host-loss E2E

В topbar добавлен `#claim-host`, доступный не-host в lobby/active.
[tests/e2e/test_live_rooms_e2e.py](../../tests/e2e/test_live_rooms_e2e.py)
содержит реальный сценарий с четырьмя независимыми контекстами,
125-секундным ожиданием, отклонением преждевременного claim,
конкурентными claim, продолжением игры и возвратом старого host без
полномочий.

Фактический прогон в текущей dev-среде ограничен: опубликованный
runtime `whos_undercover_live` старше исходника (в нём `#lobby-claim`,
а не topbar `#claim-host`), `V_PUBLISHED_UPDATE_BLOCKED` не обходился,
поэтому committed E2E на опубликованном runtime падает на `#claim-host`
(3/4 passed, host-loss timeout). Ad-hoc route-прогон текущего исходника
(не входит в repo) также не завершил host-loss: после 30 первых
browser-контекстов сработал `sessions` throttle (429). Exact-commit CI
e2e seed'ит картридж из текущего исходника в свежей БД и должен
выполнить сценарий целиком; до его success host-loss E2E считается
**NOT VERIFIED**, а не PASS.

### Observability

Структурированные события `room.create/join/command`, `room.read.slow`,
`room.read` (только error path), `room.idempotency.replay/conflict`,
`room.stale_conflict`, `room.host.transfer/claim`, `room.forfeit`,
`room.leave`, `room.expire/cleanup/expire_task`. Логируются только safe
поля; payload,
имена, роли, слова, голоса, cookies, токены и ключи идемпотентности не
логируются. `command` нормализуется в `other` для неизвестных значений,
чтобы не создавать произвольную cardinality. Негативные тесты:
`tests/integration/test_live_room_observability.py`.

## Проверки

- QA независимо выполнил idempotency/races/observability/recovery:
  **32 passed** (13+12+4+3) на финальном дереве; existing Live Room +
  loadtest guard: **26 passed** (25+1).
- QA воспроизвёл load-точку 1×8×10 s: 69 reads, 4.24 RPS (включая
  setup), p95 128.8 ms, p99 212.1 ms, 0 errors, 0 lock waiters; SQL
  avg 7.12; расхождение с документированной таблицей — в пределах
  run variance.
- JS **40/40**, `check:js` clean; ruff/format clean; mypy clean (409).
- Browser E2E в текущей dev-среде **NOT VERIFIED** (stale published
  runtime, in-container nginx topology, throttle exhaustion); exact-commit
  CI e2e остаётся execution gate.
- Финальный полный regression gate: **1324 passed, 17 skipped, exit 0**
  (640.78 s) на свежей test DB; skip — opt-in/E2E при выключенном
  `BA_E2E` и аналогичные. Exact-commit CI — ожидается.

## Независимое review

- **code-reviewer (Pro, text-only):** ACCEPT. Must-fix: тест
  `test_cleanup_and_read_are_safe` детерминированно требовал удаления
  комнаты, хотя `skip_locked` допускает её сохранение; тест переведён
  на consistency-assertions обоих легальных порядков, delta review
  ACCEPT. Также исправлена потеря `forfeited`-флага для `room.forfeit`
  при explicit host leave. Принятые non-blocking: one-poll stale
  `isHost/isReady`, failed command не обновляет `last_seen_at`,
  неиспользуемый `member_id`, rejoin в active как spectator.
- **security-auditor (Pro, text-only):** ACCEPT; блокеров/критических
  нет. M2 (env-bypass guard loadtest) и M3 (удаление пользователей по
  префиксу логина) исправлены: dev-only guard теперь требует `DEBUG`,
  cleanup идёт по списку созданных `user.pk`. M1 — major hardening gap:
  нет IP-secondary throttle на read/command/leave; ставки требуют
  решения владельца, оставлено как управляемый residual. M4
  (различимые коды ошибок idempotency при угаданном ключе), M5
  (транзиентный snapshot sweep/read) и N1 (неиспользуемый `member_id`)
  — принятые non-blocking остатки.
- **QA (Flash):** PASS WITH RESERVATIONS. Выполнены 32 targeted tests,
  26 existing+guard, load-точка, ruff/format/mypy/JS. Host-loss E2E
  локально не выполнен (stale runtime; in-container nginx topology;
  30/30 `sessions` throttle после серии прогонов). RPS включает setup,
  throttle headroom `make e2e` — 26/30 контекстов, recovery-комната
  `RUY8Q7` уже очищена. Это residuals; CI e2e должен доказать
  host-loss на свежем runtime.
- Reviews не заменяют продуктовую приёмку владельца.

## Остатки / ограничения

- Host-loss browser E2E не подтверждён независимым выполнением в
  текущей среде; exact-commit CI e2e — обязательный gate. До него
  LR-3 не считается CI-stable.
- `make e2e` создаёт ~26 первых browser-контекстов против общего
  `sessions` bucket 30/hour; запас 4 контекста. Любой дополнительный
  play-сценарий/повтор в течение часа даёт 429. Не ослаблять throttle;
  при росте набора сценариев нужен отдельный test-only лимит/свежий
  Redis, решение владельца.
- Load baseline — сервисный слой в одном процессе, не HTTP/nginx/TLS;
  RPS считается от wall time, включающего setup, и не является
  steady-state QPS. WSL2 4 vCPU/3.8 GiB, web 1 GiB/db 768 MiB; не
  production SLO.
- Нет длительного soak, multi-host, Redis/Celery под одновременной
  нагрузкой, SIGKILL посреди транзакции, staging/production.
- `expire_rooms` обрабатывает пачку комнат в одной транзакции; на
  production-объёме нужен batch/soak.
- side-effecting GET `read_room` и отсутствие IP-secondary command
  throttle остаются принятыми residual risk из LR-2b.
- Create без client requestId (прямой API/старый клиент) не может быть
  идемпотентным; UI/SDK всегда передаёт ключ. Replay комнаты в статусе
  expired и точное значение TTL отдельным тестом не покрыты; код
  status-agnostic.
- Race suite: часть сценариев проверяет инварианты/финальную БД, но не
  все outcome-коды; это принято как тестовая глубина, не серверный
  дефект.
- Product acceptance, реальные плейтесты и production deploy — владелец.
