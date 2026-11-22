# Archer — Breaktime Arcade cartridge

A 60-second ballistic archery game for the Breaktime Arcade portal.

## Gameplay

- The archer stands at the bottom centre of a layered sunset valley.
- Move the pointer/finger to aim. Hold to draw; release to shoot.
- Draw time controls power (18%–100%); arrows follow a gravity-driven arc.
- A dotted preview shows the current trajectory while drawing.
- Four target types: sun disc, swift wisp, stone guardian and rare phoenix.
- Three consecutive hits raise the multiplier (max ×5); a miss resets it.
- The round lasts 60 seconds and ends with score, hits, shots, accuracy and
  best combo.

## Package

```text
manifest.json          BA-GAME-2.2 cartridge manifest (id: archer)
index.html             entry
css/style.css          responsive UI
js/ba-sdk.js           official BA SDK 1.1.0, byte-identical to sdk/1.1.0/
js/rng.js              seeded deterministic RNG
js/core.js             pure physics, hit, combo, spawn and result rules
js/game.js             canvas rendering, input, SDK and UI
locales/<lang>.json    six interface languages
catalog/<lang>.json    card text, SEO and asset alt text
assets/                cover and two screenshots
pack.py                reproducible stdlib-only ZIP builder
```

The platform replaces the packaged SDK with the official runtime copy at
publish time. Game code never touches cookies, localStorage or the portal.

## Build

```bash
python3 pack.py --output dist/archer-1.3.1.zip
```

The ZIP is deterministic: sorted entries, fixed timestamps, normalized modes,
no `dist/`, `pack.py` or cache files.

## Controls

- Desktop: mouse aim, hold left button, release; arrow keys/WASD + Space.
- Mobile: hold anywhere to aim/draw; release to shoot; pointer capture keeps
  the gesture inside the iframe.
- P/Escape pause; pause button; sound toggle on the start/result screens.

## Limits / verification

The package is validated by the portal ZIP preflight, imported by the isolated
`zip-worker`, and autotested by the platform. Score and duration are checked
server-side; the game does not assume its own values are trusted. Product
acceptance and real-content rights belong to the owner.
