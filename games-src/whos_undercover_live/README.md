# Who's Undercover? Live — Breaktime Arcade cartridge

A real-time social deduction party game for 4–12 players, each on their own
screen. One player hosts a room; everyone else joins with a six-character code.

## Gameplay

- The host creates a room, chooses the table size and the number of
  infiltrators, and shares the room code.
- Every player gets a private role on their own device. Civilians share a
  secret word; Undercover players receive a close but different word; Mr. White
  receives no word.
- The table reveals privately, then gives one short clue in turn order. The
  host advances the speaker.
- Everyone votes in secret. A tied vote eliminates nobody and starts the next
  round. A caught Mr. White gets one guess at the civilian word and can steal
  the game.
- Civilians win when all infiltrators are eliminated. Infiltrators win when
  their count reaches the civilians.
- The host can replay the same table without rejoining.

The server owns the room and every rule. The cartridge only renders the
viewer-scoped snapshot and sends intents through the SDK 1.2 room transport.
Reloading the page restores the same room and private role from the SDK
storage; the server rejects stale commands and the client refreshes and
retries the same request id (up to three collisions). Role words, other
players' roles and the vote choices never reach a player who is not entitled
to them.

## Package

```text
manifest.json          BA-GAME-2.2 cartridge manifest (id: whos_undercover_live)
index.html             Live Room entry, lobby, reveal, clue, vote and result UI
css/style.css          shared noir design system
css/live.css           Live Room layout additions
js/ba-sdk.js           SDK placeholder replaced with BA SDK 1.2 at publish time
js/live.js             viewer-scoped room client
js/rng.js              seeded deterministic RNG (shared runtime baseline)
js/core.js             Pass & Play rules kept for the shared package contract
js/game.js             Pass & Play UI kept for the shared package contract
locales/<lang>.json    UI strings and word decks (en, ru)
catalog/<lang>.json    card text, SEO and screenshot alt text
assets/                cover and two screenshots
pack.py                reproducible stdlib-only ZIP builder
```

The Live Room UI uses only the SDK room namespace; it has no local game-state
authority, no `localStorage`/`sessionStorage` and no direct `postMessage`
usage. Persistence of the current room id goes through `sdk.storage`.

## Build

```bash
python3 pack.py --output dist/whos_undercover_live-1.0.0.zip
```

The ZIP is deterministic: sorted entries, fixed timestamps, normalized modes,
no `dist/`, `pack.py` or cache files.

## Controls

- Touch/mouse: large primary buttons, room code entry and player lists.
- Keyboard: Tab to move, Enter/Space to activate; the join code is typed with
  the normal keyboard.
- Privacy: each device renders only its own role, word and vote. The final
  screen reveals all roles and both words.
- Localization: English and Russian; other portal languages fall back to
  English with a visible coverage badge.
