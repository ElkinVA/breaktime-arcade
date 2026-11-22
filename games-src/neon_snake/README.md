# Neon Snake — 1.0.0

**Genre:** arcade (single primary genre)
**Tags:** reflex, skill, endless, neon
**Technical id:** `neon_snake`
**Languages:** English, Deutsch, Nederlands, Русский, Français, Español
**Result:** integer points, `higher_is_better`, range `0…100000`
**Session:** estimated 6 minutes; declared session limit 1800 seconds; minimum normal-session length 15 seconds
**Mobile support:** yes; orientation `any`; responsive from 320×480 to 2560×1440
**Engine:** vanilla HTML5 + CSS3 + JavaScript ES2022, Canvas 2D, classic deferred scripts, official Breaktime Arcade SDK 1.1.0 / protocol 1

## Description

Neon Snake is a complete arcade cartridge: a glowing snake moves across a
dark neon grid, eats energy orbs, grows, and speeds up every five orbs. The
run ends on a wall or on the snake's own trail. Short, readable feedback,
procedural particles and generated WebAudio cues keep the loop immediate
without external media. The start, pause, gameplay, save, and game-over flow
is implemented for guest, user, preview, and autotest modes.

## Controls

* **Desktop:** arrow keys or `W A S D` to steer; `P` or `Escape` to pause.
  Keys are intercepted only while a round is running, so the portal page can
  still scroll before the game starts. The canvas receives focus at start.
* **Touch:** swipe on the playfield or use the four on-screen buttons. Targets
  are at least 44×44 px and `touch-action: none` is set on the game surface.
* **Sound:** off until the first user gesture; the toggle persists through
  `ba.storage` under `settings.v1` with a one-second debounce.

## Result, determinism and verification

All result-affecting randomness comes from `js/rng.js`: a stable string hash
followed by mulberry32, seeded with `ba.context.seed`. The game never uses
ambient randomness. A new session receives a new seed through
`ba.newSession()`; the old seed is discarded. Score is clamped to the
manifest range and the event log uses these kinds:

| Kind | Payload `d` |
|---|---|
| `start` | `{mode}` |
| `eat` | `{x, y, value}` |
| `turn` | `{x, y, dx, dy}` |
| `level` | `{level, value}` |
| `collide` | `{x, y, reason}` |
| `end` | `{reason, score, level, apples}` |

`t` is integer active play time in milliseconds, monotonically non-decreasing
and bounded by `durationMs + 1000`. Pause time is excluded. The logger stops
at 20,000 events and 1,500,000 bytes, well below the 2 MiB raw / 256 KiB gzip
caps. `claimedVerification` is `heuristic_validated`: the game is fully seeded
and emits the declared log, but the platform has not recorded a replay run.

## Failure behaviour

* Offline during a run: the game pauses, shows a localized banner and keeps
  the in-memory board. Reconnecting resumes automatically from the same spot.
* Submission failure: up to three attempts with exponential backoff for
  temporary/network codes only. Guest answers, verification rejection, score
  bounds, and expired sessions are never retried. The result stays on screen
  and a localized retry control appears after the last attempt.
* SDK initialization failure: a localized error screen with a retry button is
  shown instead of an empty page.
* Lost focus or hidden tab: automatic pause and suspended audio; returning
  resumes only an automatically paused round.
* Guest and preview modes: the full result is shown; the non-saving notice and
  registration invitation are displayed; no retries are attempted.

## Autotest

In `mode === "autotest"` the game skips the start screen, disables sound,
starts immediately, and uses a deterministic greedy strategy. The round is
limited to 400 fixed 40 ms ticks (16 seconds of game time, comfortably below
the 25-second real-time ceiling) and reacts to `ba.on("autotest:finish")` by
submitting immediately. No modal screen is opened in this mode.

## Critical path and package size

* Declared and measured critical path (source tree, gzip): **25,320 bytes**.
  The platform recalculates it after replacing `js/ba-sdk.js` with the
  official build; the limit is 2 MiB.
* The full source tree is well below the 8 MiB recommendation and the 25 MiB
  hard package limit. Large media is not used: visuals are Canvas 2D and
  audio is generated in the browser.
* `pack.py` (standard library only) produces a deterministic ZIP with sorted
  entries, a fixed timestamp, normalized permissions, and no packaging tools
  or `dist/` artifacts.

## Local run

```
cd games-src/neon_snake
python3 -m http.server 8080
```

Windows PowerShell:

```
cd games-src\neon_snake
py -m http.server 8080
```

Then open `http://localhost:8080/`. The official SDK expects the portal iframe
handshake; outside it the game shows its localized SDK error screen rather
than a blank page. Portal/iframe acceptance is performed after import, as
specified for this delivery stage.

Build the cartridge ZIP:

```
python3 pack.py
```

The archive is written to `dist/neon_snake-1.0.0.zip`.

## Third-party materials, licences and AI provenance

* Code, CSS, Canvas artwork, cover and screenshots: created for this project,
  CC0-1.0, AI-generated.
* Sound: generated at runtime with the Web Audio API; no audio files.
* Fonts: no font file is bundled. The interface uses a system font stack
  (Segoe UI, Noto Sans, DejaVu Sans, Liberation Sans, Helvetica Neue, Arial)
  chosen for Cyrillic and Western diacritics. See deviations.
* SDK: official Breaktime Arcade `sdk/1.1.0/ba-sdk.js`, embedded byte-for-byte
  in the source package and replaced by the platform at publication.

## Deviations (§16)

1. **No bundled WOFF2 font.** §10 asks for package-local fonts. This cartridge
   uses a system font stack to keep the critical path small and avoid adding a
   binary licence surface. Impact: the exact glyph shapes vary by operating
   system; layout, Cyrillic, and diacritics remain supported.
2. **Cover and screenshots were rendered from the game's deterministic visual
   system with Pillow, not captured from a live browser.** They use the same
   palette, grid, snake, HUD and game-over composition. Live browser capture is
   part of portal acceptance after merge.
3. **Browser/iframe runtime checks are deferred.** The worktree QA gate covers
   Python package/content checks, the official SDK byte comparison, static
   forbidden-API scans, schema/parity/budget checks, reproducible ZIP, and the
   isolated import/publish pipeline. The live iframe, Node event-log execution,
   Playwright, memory, FPS, and real-device checks run in the portal acceptance
   stage after merge.

## Limitations

* The game does not include a local mock SDK in `js/ba-sdk.js`; the official
  build is embedded, as required. Local standalone play therefore needs a
  portal host or an external development harness.
* The heuristic verifier is a platform claim, not a server-side replay result.
* Sound timbre depends on the browser's Web Audio implementation.
