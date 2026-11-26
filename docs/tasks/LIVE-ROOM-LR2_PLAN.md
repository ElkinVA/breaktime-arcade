# LIVE-ROOM-LR2 — SDK 1.2 room protocol + host bridge + UI

**Дата:** 2026-11-26. **Основание:** `docs/decisions/ADR-LIVE-ROOM-001.md`,
owner directive 2026-11-26. **Статус:** PLAN / READY после приёмки LR-0/LR-1.

## Цель

Дать статическому картриджу единственный разрешённый канал к Live Room:
аддитивные сообщения SDK 1.2, host bridge на портальной странице и UI
комнаты. Server authority остаётся в `apps/rooms`; Pass & Play 1.0.1 и
BA-SDK-1.1 не меняются.

## Границы

- SDK 1.2 — новый каталог `sdk/1.2.0/`; старый `sdk/1.1.0/` не редактируется.
- Новые типы: `ba:room` (game → host) и `ba:room:data` (host → game).
- Команды: `create`, `join`, `state`, `command`, `leave`.
- Iframe не получает CSRF-cookie, launch ticket или чужие роли/слова;
  host bridge вызывает `/api/v1/rooms` от портальной сессии.
- Сервер уже проверяет membership, phase, role, expectedVersion,
  idempotency; bridge не является границей доверия.
- Polling интервал 1200 ms; room-запросы имеют отдельный лимит, чтобы не
  исчерпать общий 60/min SDK.

## Контракт (черновик)

`ba:room` payload:

```json
{
  "op": "create|join|state|command|leave",
  "roomId": "uuid (optional for create/join)",
  "code": "ABC234 (join)",
  "name": "Player (optional)",
  "gameId": "whos_undercover (create)",
  "maxPlayers": 4,
  "undercoverCount": 1,
  "mrWhite": false,
  "categoryId": "food (optional)",
  "command": "ready|start|reveal_ack|advance_clue|vote|advance|mrwhite_guess|restart|claim_host",
  "commandPayload": {},
  "expectedVersion": 12
}
```

`ba:room:data` payload — sanitized snapshot (`room`, `you`, `players`,
`game`, `setup`), только для зрителя. Ошибки — существующий `ba:error`
с `code` (`E_ROOM_*`, `E_ROOM_STALE`, `E_NOT_MEMBER`, ...).

## Этапы

1. Schema files + generator parity; host bridge schema table; SDK 1.2
   `room.*` methods and host-response validation; rate buckets.
2. `player.js`/host bridge: room API calls, CSRF, response relay, room id
   from `?room=`/sessionStorage; no secret in context.
3. Live Room UI: join/create screen, code/link, lobby, ready/start, private
   role, reveal/clues/vote/Mr. White/results, reconnect, host controls.
4. Two-browser E2E: independent contexts/devices, join by code, private
   roles not visible to each other, vote/tie/Mr. White/reconnect/expiry.
5. Regression: Pass & Play 1.0.1 unchanged; SDK 1.1 tests; full gate.

## Acceptance criteria

- SDK 1.1 files byte-identical; existing games keep working.
- A room member can create/join by code/link, see only own role/word, act in
  phase, reconnect and recover state; stale commands return 409 + snapshot.
- Host can start/advance; explicit host leave transfers; stale host claim
  works through UI; room expires/cleans up.
- No room secret/CSRF/ticket in iframe URL or logs.
- Two-browser E2E passes locally; hosted CI evidence recorded separately.
- Pass & Play E2E and JS core tests remain green.

## Риски

- UI game cartridge must be a new version/game because published updates are
  blocked; do not bypass `V_PUBLISHED_UPDATE_BLOCKED`.
- 5-min stale forfeit and 120-s host claim need product/UX sign-off.
- Polling load and mobile background behavior need LR-3/load checks.
