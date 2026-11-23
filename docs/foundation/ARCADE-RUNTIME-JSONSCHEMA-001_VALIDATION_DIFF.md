# ARCADE-RUNTIME-JSONSCHEMA-001 — validation coverage diff evidence

**Date:** 2026-11-23
**Task:** make `host_protocol.js` and `ba-sdk.js` validate postMessage envelopes
against explicit per-message schemas instead of ad-hoc checks.
**Purpose:** diff-evidence for the residual **INCOMPLETE** security review of
BA-APPF-002 runtime A+B (`docs/foundation/BA-APPF-002_RUNTIME_SDK_REPORT.md`
§5: "JSON-Schema validation evidence").
**Status:** implemented; technical review evidence only. This note is not a
product acceptance and does not change the normative ТЗ.

## 1. Baseline (before)

Baseline commit `3e037c4`; validation was hard-coded per hand-written branches:

| Side | Before |
|---|---|
| Host (`static/src/js/host_protocol.js`) | `envelope()` checked presence and primitive types; `validatePayload()` had one `switch` with ad-hoc `Number.isSafeInteger` / `typeof` / key-length checks. Schema violations in the envelope were dropped silently. |
| SDK (`sdk/1.1.0/ba-sdk.js`) | `isEnvelope()` plus `validHostPayload()` with nested ad-hoc type checks. Malformed payloads were dropped silently; an init handshake with a malformed `ba:context` fell through to the 5 s timeout. |

Before line counts: host 234 lines, SDK 521 lines.
No negative tests covered missing envelope fields, wrong field types, oversized
strings or bad `requestId`/`sessionId` on both sides.

## 2. After

Both files now contain an explicit schema table and one JSON-Schema-subset
validator:

| Element | Host | SDK |
|---|---|---|
| Envelope schema (`source`, `protocol`, `type`, `requestId`, `sessionId`, `payload`; all required, `additionalProperties: false`) | `ENVELOPE_SCHEMA` | `ENVELOPE_SCHEMA` |
| Per-message payload table | `SDK_MESSAGE_SCHEMAS` (7 game → host types) | `HOST_MESSAGE_SCHEMAS` (8 host → game types) |
| Validator | `validateSchema()` + `validateEnvelope()` / `validatePayload()` / `validateMessage()` | `validateSchema()` + `validateHostMessage()` |
| Structured violation | `{code: "E_MESSAGE_INVALID", field, reason}`; relayed to the trusted iframe as `ba:error` (`payload.code/field`) | `{code, field, reason}`; rejects the correlated pending request or the init context promise with `error.code === "E_MESSAGE_INVALID"` |

Supported schema keywords: `type` (incl. nullable type arrays), `const`,
`enum`, `required`, `properties`, `additionalProperties`, `minLength`,
`maxLength`, `format: "uuid"`, `minimum`, `maximum`, `items`, `maxItems`.

Message-type coverage:

| Direction | Types | Required fields enforced |
|---|---|---|
| game → host | `ba:hello`, `ba:submit`, `ba:leaderboard`, `ba:storage`, `ba:newSession`, `ba:exit`, `ba:error` | submit `value/durationMs/eventLog/seed` (eventLog `v/seed/events`), storage `op/key`, error `code` |
| host → game | `ba:context`, `ba:result`, `ba:leaderboard:data`, `ba:storage:data`, `ba:session`, `ba:pause`, `ba:resume`, `ba:error` | context 12 required fields, result `status/rank/isPersonalBest/isRecord/trustLevel`, leaderboard `entries/myRank`, storage `value`, session `sessionId/seed`, error `code` |

String-length rules used by the negative tests (grounded in existing
contracts/model limits): storage key 1–128, error code 1–128, message type
1–64, `gameId` ≤40 (`technical_id`), `gameVersion` ≤32 (semver column),
language ≤35 (BCP 47), nickname ≤20, seed ≤128, event kind ≤64, ≤20 000
events, ≤100 leaderboard entries.

Defence-in-depth details:

- The 60 messages/minute limiter now also counts malformed messages from the
  trusted origin, so schema-error replies cannot be used for unbounded
  reflection. The echoed `field` is capped at 64 characters.
- Wrong `event.source` and wrong `event.origin` are still **silently ignored**
  by both sides (cannot safely reply to an unauthenticated peer).
- Payload byte caps are unchanged (`E_PAYLOAD_TOO_LARGE` for >64 KiB, and
  >2 MiB + 64 KiB for `ba:submit`).

## 3. Negative test evidence

New file `tests/js/message_schema.test.mjs` (419 lines, 11 tests) runs under
`npm run test:js` and covers, on both sides:

- missing envelope fields (`payload`, `requestId`, `seed`, …) and missing
  payload fields;
- wrong types (`protocol: "1"`, `type: 7`, `payload: []`, `gameId: 42`,
  non-integer `durationMs`, non-array `entries`, non-boolean `bestOnly`);
- oversized strings (`storage.key` 129, `gameId` 41, nickname 21, error code
  129, event kind 65);
- wrong source window / origin (silent drop) and wrong `source` field
  (structured violation);
- bad `sessionId` and `requestId`, unknown message type and unknown envelope
  field;
- replay of an already-processed `requestId` (no redispatch);
- a bad `requestId` or foreign origin leaves a pending SDK request open, while
  a correlated schema violation rejects it with `E_MESSAGE_INVALID`.

`tests/js/player_race.test.mjs` fixture was corrected to the contract eventLog
shape `{v: 1, seed, events}` so the now-enforced `ba:submit` schema accepts it;
the race scenario itself is unchanged.

## 4. Diff evidence

`git diff --numstat` (tracked files):

```text
317  76  games-src/archer/js/ba-sdk.js
317  76  games-src/neon_snake/js/ba-sdk.js
317  76  sdk/1.1.0/ba-sdk.js
280  62  static/src/js/host_protocol.js
  1   1  tests/js/player_race.test.mjs
```

New (untracked) test file: `tests/js/message_schema.test.mjs` — 419 lines.

After line counts: SDK 762 lines, host 452 lines.
The two `games-src/*/js/ba-sdk.js` copies remain byte-identical to
`sdk/1.1.0/ba-sdk.js` (verified with `md5sum`).

Commands actually run:

```text
npm run test:js
  -> 19 tests, 19 pass, 0 fail (8 pre-existing + 11 new)
python3 devcontrol/sandbox/run_tests.py tests/unit/test_sdk_runtime_contract.py --timeout 300
  -> 4 passed
python3 devcontrol/sandbox/run_tests.py tests/unit/test_foundation_002_contracts.py --timeout 300
  -> 11 passed
python3 devcontrol/sandbox/run_tests.py tests/unit/test_archer_package.py --timeout 600
  -> 14 passed
python3 devcontrol/sandbox/run_tests.py tests/unit/test_neon_snake_package.py --timeout 600
  -> 13 passed
python3 devcontrol/sandbox/run_tests.py tests/unit/test_publish_runtime.py --timeout 300
  -> 3 passed
python3 devcontrol/sandbox/run_tests.py tests/unit/test_contract_schemas.py --timeout 300
  -> 10 passed
ruff check -> All checks passed
git diff --check -> clean
```

## 5. Known limitations (not hidden)

1. The JS schema tables mirror `schemas/messages/*.json` by hand; there is no
   automated cross-check that the embedded tables equal the JSON files (the
   classic-script SDK cannot import JSON). The Python contract tests validate
   the JSON files independently.
2. `ba:leaderboard` in JavaScript still enforces the SDK API limit
   `∈ {10, 100}` (BA-SDK-1.1 §2/§7), which is stricter than `minimum: 1,
   maximum: 100` in the draft JSON schema.
3. `leaderboard.myBest()` receives `{value, achievedAt, rank}`, but
   `schemas/messages/ba_leaderboard_data.json` and both schema tables require
   `entries`/`myRank`. This divergence existed before the task; the SDK still
   rejects the `myBest` payload (now with an immediate structured
   `E_MESSAGE_INVALID` instead of a 5 s timeout). Resolving it needs a contract
   decision, not a validation change.
4. Envelope violations from an untrusted `event.source`/`event.origin` are
   dropped silently by design; no reply is sent to an unauthenticated peer.
5. Payload byte limits remain the pre-existing values; no new normative limit
   for "other messages" was invented beyond the accepted 64 KiB ([PROP]
   BA-SDK-1.1 §4.4).
