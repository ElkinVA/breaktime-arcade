# SELF-CHECK — Who's Undercover? 1.0.1

## Rules

- [x] 4–12 players; unique trimmed names; exactly one device.
- [x] 1–3 Undercover; optional Mr. White; infiltrators fewer than civilians.
- [x] Civilians share one word; Undercover receives a close different word;
      Mr. White receives none.
- [x] Secret role card is scoped to the current player and cleared on handoff.
- [x] Public snapshot never exposes roles or words before elimination/final.
- [x] Secret vote rejects self, dead and duplicate voters; ties eliminate none.
- [x] Civilians win with no infiltrators; infiltrators win when equal; a
      caught Mr. White gets one guess and can steal the win.
- [x] Replay keeps the table; new setup clears the game.

## Product

- [x] Ten word decks, English and Russian UI/words, fallback to English.
- [x] Clue timer, sound toggle, reduced-motion support, 360 px layout.
- [x] Projector view for a shared public screen.
- [x] SDK handshake, `ready`, storage of table settings, pause/resume and
      session reset.
- [x] Live Room is explicitly out of scope until the platform provides a room
      contract.

## Verification

- JS core tests: `node --test tests/js/whos_undercover.test.mjs`.
- Package: `python3 games-src/whos_undercover/pack.py --output <zip>` then
  import through the isolated ZIP pipeline.
- Browser E2E: setup → role reveal → clues → vote → result → replay.
- Manual privacy check: before tapping a handoff button, the role and word
  are absent from the visible card; after hiding, they are cleared.
