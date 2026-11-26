# LIVE-ROOM-LR3 — production-grade reliability plan

**Дата:** 2026-11-26. **Основание:** owner directive 2026-11-26 (LR-3),
`ADR-LIVE-ROOM-001`, `docs/status/PROJECT_STATUS.md`,
`docs/status/BACKLOG.md`. **Точка старта:** `main = 3ee2f0e`, CI run #156
success. **Статус:** IMPLEMENTED; code+security review ACCEPT; QA PASS
WITH RESERVATIONS; full regression gate **1324 passed, 17 skipped,
exit 0**; exact-commit CI **#157 SUCCESS** (`e3c9d21`), включая
host-loss E2E на fresh published runtime. Live Room не объявляется
production-ready до продуктовой приёмки владельца.

## Цель

Доказать и повысить корректность Live Room при повторных запросах,
конкурентных командах, нагрузке, перезапуске процессов и сбоях Celery.
Не менять polling interval (1200 ms), 120-секундный host-claim и
5-минутный stale-member forfeit без решения владельца.

## Карта рисков

| ID | Риск | Влияние | Мера |
|---|---|---|---|
| LR3-R1 | Повтор create после потери ответа создаёт вторую комнату | дубликат комнаты/host | ключ идемпотентности + уникальная запись в БД в одной транзакции |
| LR3-R2 | Ключ идемпотентности становится токеном доступа к чужой комнате | утечка/захват | жёсткая привязка к subject (user/anon); другой subject → 409; без чтения по ключу |
| LR3-R3 | Потеря Set-Cookie у гостя | нет доступа к созданной комнате | повтор с тем же subject восстанавливает; при утрате identity — понятный 409, без дубликата и без доступа |
| LR3-R4 | Параллельные create/join/ready/vote/claim | два host, переполнение, потеря голосов | row lock Room + unique constraints + реальные PostgreSQL-транзакции |
| LR3-R5 | Read path lock contention | рост latency при 8–12 игроках | baseline нагрузочного теста; оптимизация только после измерений |
| LR3-R6 | Expire/cleanup массовые блокировки | деградация и долгие транзакции | batch/skip_locked, повторный безопасный вызов, метрики |
| LR3-R7 | Restart/crash оставляет частичное состояние | потеря ролей/голосов | атомарные транзакции + тесты повторного чтения/задач |
| LR3-R8 | Observability логирует секреты/PII или имеет высокую cardinality | утечка/стоимость | whitelist полей, запрет role/word/vote/name/key/cookies, тесты caplog |
| LR3-R9 | Host-loss UI не даёт забрать роль в активной игре | блокировка игры | глобальная host-claim кнопка во всех фазах |
| LR3-R10 | Идемпотентные записи растут бесконечно | диск/индексы | TTL 7 дней + cleanup, FK SET_NULL для удалённых комнат |

## 1. Идемпотентность создания

### Контракт

- Клиент генерирует `requestId` UUID (ключ намерения) и передаёт его в
  SDK 1.2 `room.create({requestId})`; host bridge маппит в
  `request_id`; API `RoomCreateSerializer` принимает optional UUID.
- Ключ не является токеном комнаты: он используется только в
  `POST /api/v1/rooms` и только вместе с тем же subject и payload.
- Один и тот же ключ + тот же subject + тот же payload → существующая
  комната/host-member, без новой записи.
- Тот же ключ + другой payload → `409 E_IDEMPOTENCY_CONFLICT`.
- Тот же ключ + другой subject → `409 E_IDEMPOTENCY_CONFLICT`; никакого
  переноса host/member.
- Другой ключ + тот же payload → новая комната.
- `requestId` отсутствует → прежнее поведение (каждый POST — новое
  намерение); UI всегда передаёт ключ.

### DB

Новая модель `RoomCreateRequest`:
`key UUID unique`, `subject_type`, `subject_id`, `payload_hash`,
`room FK SET_NULL`, `host_member_id`, `expires_at`, timestamps.
Запись создаётся в той же транзакции, что Room + RoomMember. Уникальный
`key` — арбитр параллельных запросов. TTL — 7 суток
(`ROOM_IDEMPOTENCY_TTL_SECONDS`, env). Cleanup удаляет только записи с
истёкшим TTL; комната может быть уже удалена (SET_NULL), повтор тогда
возвращает `410 E_IDEMPOTENCY_GONE`, а не создаёт дубликат.

### Ошибки

- `E_IDEMPOTENCY_CONFLICT` (409): ключ уже связан с другим subject или
  payload.
- `E_IDEMPOTENCY_GONE` (410): запись есть, комнаты/участника больше нет.
- `E_IDEMPOTENCY_EXPIRED` (409): запись истекла, но ещё не очищена.
- Существующая комната в статусе finished/expired возвращается как
  текущий snapshot (клиент увидит закрытую комнату), без дубликата.

### Anonymous cookie

`AnonymousIdentity` остаётся единственной identity. Если Set-Cookie
потерян, повтор с тем же ключом, но уже другим anon-subject получает
409; вторая комната не создаётся. Восстановление доступа возможно только
при сохранённой identity cookie. Ключ не логируется и не отдаётся
наружу. Этот компромисс фиксируется для security review.

## 2. Конкурентные сценарии

Реальные `transaction=True` тесты на PostgreSQL, независимые соединения и
`ThreadPoolExecutor`/barrier:
create (same key/parallel/different payload/subject), join at capacity,
ready, start, duplicate command requestId, same expectedVersion, vote
resolution, tie, host claim (two players / claim vs host command), sweep
vs command, expiry vs command, cleanup vs read, room-code collision.

Проверки: ровно один host, `active` members ≤ max_players, ровно один
RoomCommand на requestId, голоса не теряются/не дублируются, финальная
фаза соответствует правилам, приватные поля не попадают в чужие
snapshot.

## 3. Load baseline

Отдельный воспроизводимый load-скрипт/management command:
- комнаты 4/8/12, 1/5/20 комнат, polling 1200 ms, 60–120 s;
- измерять RPS, p50/p95/p99, SQL count, DB lock wait, CPU/RAM контейнеров,
  errors, command latency, version rate, Celery/expiry latency;
- зафиксировать машину/WSL, версию, seed/БД и baseline;
- performance budgets предложить только по baseline, не выдумывать.

`read_room()` — отдельный замер: текущий `select_for_update` на каждом
чтении; при подтверждённой деградации разделить read/mutation path,
сохранив авторитетность и атомарность. `expire_rooms()`/`cleanup_rooms()`
проверить на batch/skip_locked и длительность.

## 4. Crash/restart

- повторный `expire_rooms_task` и `cleanup_rooms` — идемпотентны;
- рестарт web/worker во время активной игры — состояние и роли
  сохраняются; reconnect возвращает то же;
- оборванное соединение и неопределённый результат команды — повтор с
  requestId не дублирует действие;
- тесты отката транзакции при ошибке; отсутствие частично применённых
  состояний; Celery task безопасен при повторной доставке.

## 5. Host-loss E2E

Глобальная кнопка `#claim-host` в topbar (видна не-host в lobby/active).
Отдельный Playwright-сценарий с реальным 120-секундным окном:
до порога claim отклоняется, после — один игрок становится host, игра
продолжается; старый host возвращается без полномочий; одновременные
claim не создают двух host. Для остальных сценариев — контролируемые
часы/прямые сервисные тесты.

## 6. Observability

Существующий JSON logger + Celery events. События:
`room.create`, `room.join`, `room.command`, `room.read.slow`,
`room.idempotency.replay`, `room.idempotency.conflict`,
`room.stale_conflict`, `room.host.transfer`, `room.host.claim`,
`room.forfeit`, `room.expire`, `room.cleanup`.

Поля — только безопасные: event, outcome, error_code, game_id, room_id,
command, phase, duration_ms, lock_wait_ms, row counts, replayed/conflict
bool, counts. Запрещены: name, role, word, vote target, request/key,
cookies, session/auth tokens, payload. Добавить caplog-тесты на
отсутствие запрещённых данных. Cardinality — ограниченный набор
событий/полей; room_id в логи не является метрикой.

## 7. Последовательность

1. Plan + idempotency model/migration/service/API/SDK/host/UI/tests.
2. Concurrency tests и исправления найденных гонок.
3. Load baseline, затем минимальная оптимизация по измерениям.
4. Restart/crash/repeat Celery tests.
5. Host-claim UI + 120-s browser E2E.
6. Observability events + negative leak tests.
7. Independent code-reviewer/security-auditor/QA; fixes.
8. Full gate, CI exact commit, docs/registers.

## Критерии завершения

Все пункты §8 owner directive: idempotency, PostgreSQL concurrency,
measured load baseline/results, crash/restart, repeatable Celery,
host-loss E2E, observability without leaks, full regression, independent
review ACCEPT, GitHub Actions success on exact commit, updated registers.
Product acceptance remains owner-only.

## Evidence (2026-11-26)

- Idempotency: `RoomCreateRequest` + migration `0002`; 13 integration
  tests; SDK 1.2/host bridge/live.js key; strict subject+payload binding.
- Races: 12 PostgreSQL tests; cleanup/read race fixed.
- Load: `docs/foundation/LIVE_ROOM_LR3_LOAD_BASELINE.md`.
- Recovery: `docs/foundation/LIVE_ROOM_LR3_RECOVERY.md`; real web/worker
  restart, two Celery expiry tasks through the worker.
- Host-loss: 4 независимых контекста, real 125 s wait. Локальная
  dev-среда NOT VERIFIED (stale published runtime; in-container topology;
  30/30 `sessions` throttle). Exact-commit CI **#157** e2e job
  **completed success** на fresh DB + `make undercover-live-seed`,
  `pytest tests/e2e -m e2e` прошёл целиком, включая host-loss.
- Observability: 4 negative/redaction tests; bounded command values.
- Reviews: code-reviewer ACCEPT (must-fix race assertion fixed; delta
  ACCEPT), security-auditor ACCEPT (M1 residual), QA PASS WITH
  RESERVATIONS.
- Full gate: **1324 passed, 17 skipped, exit 0** (640.78 s) на свежей
  test DB; ruff/format/mypy clean.
- Full report: `docs/foundation/LIVE_ROOM_LR3_REPORT.md`.

## Остатки

- Code/security reviews ACCEPT; QA PASS WITH RESERVATIONS; exact-commit
  CI #157 success, включая host-loss E2E. CI-green не заменяет
  продуктовую приёмку владельца.
- Load numbers are service-layer, WSL2; RPS includes setup, not
  steady-state; not HTTP/production SLO.
- E2E throttle headroom: ~26/30 first-visit contexts per `make e2e`;
  additional play scenarios/reruns within an hour can hit 429. Do not
  weaken throttling.
- No long soak, SIGKILL mid-transaction, Redis/broker failure, staging or
  production load.
- Product acceptance remains owner-only.
