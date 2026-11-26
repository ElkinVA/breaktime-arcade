# BA SDK changelog

## 1.2.0 — 2026-11-26

- Additive Live Room protocol: `ba:room` (game → host) and
  `ba:room:data` (host → game).
- `ba.room.create/join/state/command/leave` methods.
- `room.create` accepts an optional client `requestId`; safe create retries
  are idempotent per subject and payload.
- Room messages use a separate 120/min limiter; existing SDK 1.1 limits are
  unchanged.
- SDK 1.1 games and the Pass & Play cartridge are unchanged.

## 1.1.0 — baseline

- Initial public SDK slice: context, submit, leaderboard, storage,
  newSession, exit, error.
