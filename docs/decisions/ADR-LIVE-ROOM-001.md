# ADR-LIVE-ROOM-001 — server-authoritative Live Room

**Дата:** 2026-11-26. **Статус:** proposed → implementation LR-0. **Основание:**
owner directive 2026-11-26; BA-PLAT-4.2, BA-SDK-1.1, BA-GAME-2.2.

## Context

Pass & Play уже работает как static cartridge на одном устройстве. Live Room
требует разных устройств, общего состояния, приватных ролей, тайного
голосования и reconnect. Статический game origin не может держать сервер;
BA-SDK-1.1 не имеет room API. Нельзя ломать существующие SDK-контракты и
Pass & Play.

## Decision

1. **Server authority:** состояние комнаты живёт в PostgreSQL и меняется
   только серверными командами. Клиент присылает намерение
   (`command`, `expectedVersion`, `requestId`), получает sanitized snapshot.
2. **Transport:** HTTP polling через SDK/host, без WebSocket/Channels. Polling
   interval 800–1200 ms, `version`/`updatedAt` для long-poll-подобной
   дедупликации. Это не добавляет ASGI/новый стек и переживает мобильные
   сети; для социальной игры задержка <2 s достаточна.
3. **Data:** `Room` (code, game, host, status, state JSONB, version,
   expires_at, max_players), `RoomMember` (subject_type/id, name, role,
   ready, last_seen), `RoomCommand` (идемпотентный request id), optional
   `RoomEvent` history. Секреты (`role`, `word`) хранятся только в
   server-side JSON и никогда не попадают в чужой snapshot.
4. **Auth:** portal session/AnonymousIdentity, CSRF on write; membership by
   subject; host commands guarded; room code 6 chars from unambiguous
   alphabet and join throttled. No room token in iframe URL.
5. **Concurrency:** `select_for_update` на Room; каждая команда проверяет
   membership, phase, expectedVersion, idempotency; версия увеличивается в
   одной транзакции. Stale command → 409 + latest snapshot.
6. **Lifecycle:** lobby TTL 30 min, active TTL 2 h, idle TTL 30 min; beat
   cleanup marks expired rooms and deletes finished/abandoned/expired rooms
   after a 24 h retention window; explicit leave during an active game
   forfeits that player and resolves the affected phase; members that stop
   polling for 5 min are forfeited on the next room read, and a stale host is
   replaced by the earliest active member; a member may also claim host after
   the host has not been seen for 120 s; a leaving host transfers host to the
   earliest active member; members reconnect by same subject; duplicate joins
   are idempotent; account deletion scrubs room identity and closes affected
   rooms.
7. **SDK extension (later LR-2):** additive `ba.room` request/response
   messages in a new SDK 1.2.0; old SDK games remain unchanged. Host bridge
   calls the room API with the existing session/CSRF identity. No secret in
   `postMessage` payloads other than the viewer's own role.
8. **Game boundary:** room engine is game-specific server code. Who's
   Undercover rules are ported to Python; static cartridge only renders
   sanitized snapshots/commands. Pass & Play remains independent.

## Alternatives rejected

- **Channels/WebSocket:** new ASGI stack and deployment surface; not needed
  for turn-based party play.
- **Redis-only room state:** weaker durability/reconnect, harder audit;
  PostgreSQL is the system of record, Redis only for throttling.
- **SDK-less direct API from game origin:** violates "SDK is the only
  channel", CSRF/cookies cross-origin.
- **Client-authoritative roles:** leaks secrets and permits tampering.

## Acceptance / staged plan

**LR-0 (first READY):** models/migrations, create/join/leave, lobby
ready/start for Who's Undercover, server role/word assignment, sanitized
snapshot per viewer, version/idempotency, TTL fields, API tests. No UI yet.

**LR-1:** phases/clues/secret vote/tie/Mr. White/win, reconnect and stale
command tests, cleanup beat.

**LR-2:** SDK 1.2 room messages, host bridge, Live Room game UI; E2E
two-browser lobby/reveal/vote.

**LR-3:** throttles, room limits, observability, load/crash tests, product
acceptance.

## Security invariants

- A member never receives another member's role/word or vote identity.
- Host cannot see secret roles except their own.
- Commands validate subject membership and phase; replay is idempotent.
- Room codes are not authentication; membership is.
- Expired/abandoned rooms reject commands; cleanup is idempotent.
- Account deletion removes room nicknames/stable subject ids and closes the
  affected rooms; the pseudonymous room id may remain for the retention window.
- No room secret in logs, metrics, URLs or static bundles.
