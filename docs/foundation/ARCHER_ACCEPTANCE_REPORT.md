# ARCADE-P5 ARCHER — acceptance report

**Date:** 2026-11-23
**Base:** `b4fd9f4`
**Game:** Archer v1.3.3, package id `archer`
**Status:** **IMPLEMENTED; AUTOMATED + LIVE DEV E2E PASS; INDEPENDENT
PRO REVIEW ACCEPT; PRODUCT/STAGING/PRODUCTION NOT ACCEPTED.**

## 1. Status matrix

| Area | Status | Evidence |
|---|---|---|
| Game code | IMPLEMENTED | `games-src/archer` |
| Package structure/manifest | TESTED | 13 package tests |
| Physics/score/combo core | TESTED | 11 Node tests |
| ZIP reproducibility/preflight | TESTED | package test + pack.py |
| Isolated-worker import/publish | TESTED | 1 integration test; live worker 137 ms |
| CRM upload → analysis → publish | TESTED LIVE | v1.0…v1.3.3 |
| Public detail/iframe/runtime | TESTED LIVE | 200; no console errors |
| SDK handshake/heartbeat/result | TESTED LIVE | result 200, credited 60122 ms |
| Leaderboard | TESTED LIVE | 200; #1 321, #2 214 |
| Update/rollback/republish | TESTED LIVE | v1.3.0 → v1.2.1 → v1.3.3 |
| Responsive matrix | TESTED LIVE | 360×640, 390×844, 640×360, 1280×800, 1920×1080 |
| Neon Snake regression | TESTED | package 13, import 1, live pages 200 |
| Independent Pro review | ACCEPT; major closed | initial major end-event fixed; delta review accept |
| Staging/production | NOT TESTED | owner-gated |
| Missing original prototype | NOT PORTED | `index4(1).html` absent |

## 2. Automated tests

```text
node tests/js/archer.test.mjs                         -> 11 passed
sandbox tests/unit/test_archer_package.py             -> 13 passed
sandbox tests/integration/test_archer_import.py       -> 1 passed
sandbox tests/unit/test_neon_snake_package.py         -> 13 passed
sandbox tests/integration/test_neon_snake_import.py   -> 1 passed
```

Core tests cover power bounds, aim clamp, deterministic ballistic path,
gravity, swept collision, combo/multiplier/score, miss reset, accuracy,
60 s finish, pause/resume, single-submit lock, phase spawn caps and target
spawn bounds.

## 3. Live dev E2E

- ZIP `archer-1.3.3.zip`, deterministic, 24 entries.
- CRM upload → analysis: **0 blockers**.
- zip-worker completed; runtime published.
- Detail: cover + 2 screenshots render 200.
- Play page creates session and iframe; no page/iframe console errors.
- Full 60 s user runs: **321 points**, 13 hits / 22 shots (59%), best combo 5 (v1.3.0) and **156 points**, 9 hits / 22 shots (41%), best combo 4, rank 3 (v1.3.3),
  result API `200 {"status":"saved","rank":1,"is_record":true,
  "trust_level":"heuristic_validated"}`; `credited_ms=60122`; heartbeat set.
- Leaderboard: 321 (#1), 214 (#2), 156 (#3) after the final v1.3.3 run.
- Rollback to v1.2.1 and republish v1.3.3 successful.
- Invalid ZIP path already covered by P4 (`V_MANIFEST_SCHEMA`); package tests
  run `preflight_zip` and import rejection paths.
- Responsive: no horizontal overflow; start screen visible at all five
  viewports; 1280 stage 798×532, 1920 1082×721, 360 314×209, 640×360 336×240.

## 4. Defects found/fixed

| Defect | Fix |
|---|---|
| HUD visible behind start overlay (`[hidden]` overridden by `.hud`) | `.hud[hidden] { display:none }` |
| Pause button displayed literal "Pause" next to icon | removed text node, localized aria-label |
| Stage aspect distorted by max-height | width from `(100dvh - 28px) × 1.5`, 3:2 preserved |
| Bow rendered as near-circle | half-arc bow + string/grip |
| Combo semantics ambiguity | third hit pays ×2; miss resets; tests |
| Result "personal best" line showed — | known cosmetic: leaderboard myBest loading race; score/rank/leaderboard are correct |

## 5. Source limitation

`index4(1).html` was not present anywhere searched. Archer follows the
written concept; it is **not** a verified port. Owner can supply the file
for a behaviour-diff review. This is a NOT TESTED item, not a PASS.

## 6. What was not tested

- Original prototype fidelity (file absent).
- Staging/production deploy; no production changes.
- Cross-browser beyond Chromium; real mid-range 60 FPS benchmark.
- Network failure/retry UI under real packet loss (code paths exist and are
  unit/static checked; not browser-fault-injected).
- Full 60 s run under mobile touch (desktop mouse run used for result;
  mobile layout/start checked).
- Product/legal acceptance and content rights — owner only.

## 7. Evidence / artifacts

- Plan: `docs/tasks/ARCADE-P5-ARCHER_PLAN.md`
- Spec: `docs/foundation/ARCHER_GAME_SPEC.md`
- Progress: `docs/foundation/ARCHER_PROGRESS.md`
- Owner list: `docs/foundation/ARCHER_OWNER_ACTION_LIST.md`
- Package: `games-src/archer`
- Tests: `tests/js/archer.test.mjs`, `tests/unit/test_archer_package.py`,
  `tests/integration/test_archer_import.py`
- Review: initial Pro review ACCEPT with one major (end event never emitted)
  and minors; fixed in 7ae216b/8ebfb0c; delta review **ACCEPT, major
  CLOSED**. Reviewer did not execute the live/browser checks itself.
