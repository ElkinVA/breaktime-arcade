# ARCADE-P5 ARCHER — progress journal

**Date:** 2026-11-23
**Base:** `b4fd9f4` (P4).
**Worktree:** `.worktrees/archer`, branch `archer-p5`.
**Status:** IMPLEMENTED, live dev E2E PASS, independent Pro review
**ACCEPT** (major end-event fixed).

## 1. Research

- Read Neon Snake package, manifest, catalog/locales, pack.py, official
  SDK, package/import tests, CRM wizard, worker and browser runtime.
- Requested `index4(1).html` was not found in workspace or Windows user
  folders; recorded as a source limitation, not invented as a port.
- Verified current platform paths: `/crm/games/add/`, wizard steps,
  `/en/games/<slug>/play/`, runtime host `<label>.games.test`, result and
  leaderboard APIs.

## 2. Plan

Plan: `docs/tasks/ARCADE-P5-ARCHER_PLAN.md`. Package `games-src/archer`;
pure `core.js` for physics/score/spawn; `game.js` for Canvas/input/SDK;
six locales/catalogs; generated assets; reusable pack.py; Node package tests,
Python package/import tests; live CRM E2E.

## 3. Implementation

- `games-src/archer` complete cartridge.
- Fixed 60 s round, four phases, four target types, combo ×5, ballistic
  preview, pointer capture, pause/blur/visibility, sound, localization.
- Official SDK byte-identical; no gateway changes.
- Assets: 1280×720 WebP cover + two screenshots (live frame/result).
- `tests/js/archer.test.mjs` — 11 core tests.
- `tests/unit/test_archer_package.py` — 14 package/content tests.
- `tests/integration/test_archer_import.py` — isolated-worker import/publish.

## 4. Live dev E2E

1. `archer-1.3.3.zip` built deterministically (24 entries).
2. CRM upload → analysis: **0 blockers**.
3. zip-worker: `zip.received`/`zip.extract`/`zip.complete`, 24 files,
   137 ms for v1.0; later versions OK.
4. Published versions: v1.0.0, v1.1.0, v1.2.0, v1.2.1, v1.3.0, v1.3.3.
5. Public detail/play/iframe loaded; cover and both screenshots 200.
6. Played full 60 s as test user:
   - score **321**, hits 13, shots 22, accuracy 59%, best combo 5;
   - result API `200`, `saved`, rank 1, `is_record`, `heuristic_validated`;
   - session `credited_ms=60122`, heartbeat timestamp present.
7. Leaderboard 200: 321 (#1), 214 (#2).
8. Rollback v1.3.0 → v1.2.1 and republish v1.3.3.
9. Corrupt ZIP test: previous P4 pipeline already rejected with
   `V_MANIFEST_SCHEMA`; Archer package tests cover preflight/import rejection.
10. Capacity: 360×640, 390×844, 640×360, 1280×800, 1920×1080:
    start visible, no horizontal overflow, no console errors.

## 5. Bugs found/fixed

- HUD was visible behind the start overlay because `.hud{display:flex}`
  overrode `[hidden]`; added `.hud[hidden]{display:none}`.
- Pause button rendered literal "Pause" next to the CSS icon; removed text
  node, kept localized `aria-label`.
- Stage aspect ratio was distorted by `max-height` without width constraint;
  width now derived from available height ×1.5, preserving 3:2.
- Combo hit now pays the multiplier it raises (third hit ×2), matching the
  documented test/balanced intent; no "last arrow" reset.
- Bow rendering changed from a near-circle to a half-arc with string/grip.

## 6. Neon Snake regression

- `tests/unit/test_neon_snake_package.py` 13 passed.
- `tests/integration/test_neon_snake_import.py` 1 passed.
- Live `/en/games/neon-snake/`, `/play/`, `/leaderboard/` 200; existing
  5-point entry remains.
- No platform files changed in Archer branch.

## 7. Not tested / limits

- Source prototype port: **NOT POSSIBLE** (file absent).
- Staging/production: NOT TESTED.
- 60 FPS proof on real mid-range devices: not benchmarked; fixed-step and
  capped particles are implemented.
- Cross-browser: Chromium only.
- Independent review: initial **ACCEPT** with major (end event dropped)
  and minors; fixed; delta **ACCEPT, major CLOSED**.
