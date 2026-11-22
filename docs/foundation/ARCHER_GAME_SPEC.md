# Archer — game specification (ARCADE-P5)

**Version:** 1.3.3
**Date:** 2026-11-23
**Package id:** `archer`
**Genre:** arcade / skill / aim & shoot
**Reference:** BA-GAME-2.2, BA-SDK-1.1, Neon Snake integration conventions.

## 1. Source note

The requested prototype `index4(1).html` was not present in the workspace
(`/mnt/c/Users/User`, Downloads/Desktop, repository) at implementation time.
The implementation follows the written concept and mechanics from the task:
a bottom-centre archer, aim/draw/release, ballistic arrows, moving target
types, sunset fantasy. It is **not** claimed as a line-by-line port of the
missing file. If the prototype is later provided, a diff review can align
specific original behaviours.

## 2. Round

- Fixed 60-second round, four 15-second phases.
- Archer fixed at bottom centre; aim angle clamped to the upward arc.
- Fixed timestep 1/120 s; accumulator capped (0.1 s/frame, 240 safety
  steps). Rendering is independent of step count; 30/60/120 FPS produce the
  same simulation for the same elapsed time.
- Timer advances only while running and not paused; hidden tabs/blur pause.
- Round ends exactly once; every live arrow resolves as a miss at the end.

## 3. Controls

| Input | Action |
|---|---|
| Pointer move / touch | aim |
| Pointer down / hold | draw, power grows 0.18→1.0 over 1.2 s |
| Pointer up | shoot |
| pointercancel, lost capture, blur | cancel draw without shooting |
| Arrow keys / WASD | aim |
| Space | draw; release to shoot |
| P / Escape / pause button | pause |
| Sound toggle | start/result screen |

Pointer capture is enabled; `touch-action: none`; no page scroll. The
trajectory preview is visible while drawing.

## 4. Physics

- Speed = 520 + 660 × power (px/s).
- Gravity = 980 px/s².
- Arrow velocity updated with fixed dt; collision uses the swept
  previous→current segment against a target circle.
- Arrows are removed after hit or when outside the field.
- Targets are data-driven and updated with the same dt.

## 5. Targets

| Type | Radius | Value | Motion | Visual |
|---|---:|---:|---|---|
| Sun | 34 | 20 | sine drift | glowing sun disc + rays |
| Wisp | 21 | 35 | fast zigzag from side | cyan flame with glow |
| Guardian | 54 | 12 | slow patrol/float | stone octagon + rune |
| Phoenix | 30 | 75 | circular, 4.2 s lifetime | rose-gold phoenix + timer ring |

`MAX_TARGETS=6`. Phase plans change interval/mix/cap; phoenix is rare.
No four-colour-only clones.

## 6. Score and combo

- Successful hit: `value × current multiplier`; current multiplier is the
  multiplier after this hit (so the third consecutive hit pays ×2).
- Every 3 consecutive hits raise multiplier, capped ×5.
- Miss: streak 0, multiplier 1.
- Every shot resolves once; shots/hits/misses/accuracy/best combo tracked.
- Result sends: score, duration 60000 ms, seed, bounded event log,
  clientMeta hits/shots/bestCombo/source.
- Server remains authoritative; client numbers are heuristic-validated.

## 7. SDK / platform

- Official `js/ba-sdk.js` only; `BreaktimeArcade.init`, `ready`,
  `newSession`, `submitResult`, `leaderboard.top`, `leaderboard.myBest`,
  `storage`, `exit`, `on("pause"/"resume"/"visibility"/"autotest:finish")`.
- No custom SDK channel; no cookies/localStorage; guest results normalized.
- One result per session via `createSubmitState/beginSubmit`; retry only
  transport/5xx/retryable codes.
- `newSession` on Play Again; no duplicate submission.

## 8. UI/localization

- Start, HUD (score/combo/time), pause, result (score/hits/shots/accuracy/
  best combo), leaderboard, sound.
- Six languages: en, de, nl, ru, fr, es; locale/catalog key parity tested.
- Responsive 360×640, 390×844, 640×360, 1280×800, 1920×1080; no horizontal
  overflow; safe areas, pointer controls, readable HUD.
- Sound is generated WebAudio only after a gesture; mute persists via SDK.

## 9. Assets

- `assets/cover.webp`, `screen-1.webp`, `screen-2.webp`: 1280×720 WebP,
  generated from the same sunset visual system / live game frame; bounded
  cover/screenshot budgets. No unlicensed external art/audio.

## 10. Package

`manifest.json`, `index.html`, `css/style.css`, `js/ba-sdk.js`,
`js/rng.js`, `js/core.js`, `js/game.js`, six `locales/*.json`, six
`catalog/*.json`, assets, `README.md`, `SELF-CHECK.md`, stdlib `pack.py`.
ZIP is deterministic; original package immutable; published runtime is a
separate copy with the platform SDK.
