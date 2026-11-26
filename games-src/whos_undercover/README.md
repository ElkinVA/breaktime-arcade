# Who's Undercover? — Breaktime Arcade cartridge

A social deduction party game for 4–12 players on one device.

## Gameplay

- One device is passed privately to reveal each player's role.
- Civilians share a secret word; Undercover players receive a close but
  different word; Mr. White receives no word.
- Each player gives one short clue. The table discusses, then passes the
  device again for a secret vote.
- Civilians win when all infiltrators are eliminated. Infiltrators win when
  they match the civilians. A caught Mr. White gets one guess at the civilian
  word and can steal the game.
- Replay the same table or start a new setup; ten word decks, two languages,
  clue timer, sound, projector view and full final reveal.

Live Room (separate devices) is **not** part of this cartridge: the platform
SDK 1.1 has no shared room or authoritative realtime state. This package is
the complete Pass & Play product.

## Package

```text
manifest.json          BA-GAME-2.2 cartridge manifest (id: whos_undercover)
index.html             entry
css/style.css          responsive noir UI
js/ba-sdk.js           official BA SDK 1.1.0, byte-identical to sdk/1.1.0/
js/rng.js              seeded deterministic RNG
js/core.js             pure setup, role, vote and win rules
js/game.js             DOM, SDK handshake, storage, timer and sound
locales/<lang>.json    UI strings and word decks (en, ru)
catalog/<lang>.json    card text, SEO and screenshot alt text
assets/                cover and two screenshots
pack.py                reproducible stdlib-only ZIP builder
```

## Build

```bash
python3 pack.py --output dist/whos_undercover-1.0.1.zip
```

The ZIP is deterministic: sorted entries, fixed timestamps, normalized modes,
no `dist/`, `pack.py` or cache files.

## Controls

- Touch/mouse: large primary buttons and player cards.
- Keyboard: Tab to move, Enter/Space to activate.
- Privacy: the role card is only rendered after the named player taps their
  handoff button; it is cleared before the next handoff.
- Projector view enlarges the public board on a shared screen.
