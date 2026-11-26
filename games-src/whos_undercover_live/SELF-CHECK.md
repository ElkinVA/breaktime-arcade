# SELF-CHECK — Who's Undercover? Live 1.0.0

## Rules

- [x] 4–12 players, each on an independent device; room code join; host starts.
- [x] 1–3 Undercover; optional Mr. White; civilians must outnumber infiltrators.
- [x] Civilians share one word; Undercover receives a close different word;
      Mr. White receives none.
- [x] All phases: lobby → private reveal → clues → secret vote → result or
      Mr. White guess → game over → restart.
- [x] A tied vote eliminates nobody and starts the next round.
- [x] Civilians win with no infiltrators; infiltrators win at parity; a caught
      Mr. White gets one guess and can steal the win.
- [x] The host advances the clue speaker and can replay the table.
- [x] The server rejects self-votes, dead voters, duplicate voters and stale
      commands; command request ids are idempotent.

## Privacy and authority

- [x] The server owns roles, words, votes, phases and the winner in PostgreSQL.
- [x] Snapshots are viewer-scoped: another player's role and word are absent
      until elimination or the final reveal.
- [x] The iframe receives no portal cookies, launch ticket or secret material.
- [x] The client renders names, roles and words with `textContent` only.
- [x] No `localStorage`, `sessionStorage`, direct `postMessage`, `eval`,
      external URLs or clipboard API in the cartridge.
- [x] The current room id is stored through the SDK storage namespace only.
- [x] Reload/reconnect restores the same private role from the server.
- [x] A stale command is refreshed and retried with the same request id (up to
      three collisions), so simultaneous secret votes serialize safely.

## Product

- [x] English and Russian UI; other portal languages fall back to English with
      a visible coverage badge.
- [x] Large touch targets, keyboard operation and a readable 360 px layout.
- [x] Lobby shows readiness and blocks Start until the table is balanced.
- [x] Connection state and structured room errors are visible to the player.
- [x] Host claim is available when the host is stale.

## Verification

- [x] Server: `pytest tests/integration/test_live_rooms.py`.
- [x] Four independent browser contexts: `pytest tests/e2e/test_live_rooms_e2e.py -m e2e`
      (create, join, readiness, private reveal, reconnect, clues, vote,
      elimination and game over).
- [x] Package: `python3 games-src/whos_undercover_live/pack.py --output <zip>`
      then import through the isolated ZIP pipeline.
