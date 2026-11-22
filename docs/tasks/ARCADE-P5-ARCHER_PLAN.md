# ARCADE-P5 — ARCHER technical plan

**Дата:** 2026-11-23
**База:** `b4fd9f4` (P4 accepted/verified; Neon Snake is the integration reference).
**Worktree:** `.worktrees/archer`, branch `archer-p5`.
**Статус:** PLAN → IMPLEMENTATION.

## 1. Факты

- Исходный `index4(1).html` в рабочей среде отсутствует: поиск по
  `/mnt/c/Users/User`, `~/Downloads`, Desktop и репозиторию не нашёл файл.
  Реализация использует описанную механику (лучник, натяжение, баллистика,
  движущиеся цели, sunset fantasy) и не выдаёт её за дословный порт.
- Neon Snake (`games-src/neon_snake`) — рабочий эталон пакета: manifest,
  catalog/locales, official SDK byte-identical, seeded RNG, reproducible
  `pack.py`, package/import tests, isolated worker и CRM upload/publish.
- Пакет игры не меняет SDK, CRM, worker, quota, CSP или публикацию.

## 2. Файлы

```text
games-src/archer/
  manifest.json
  index.html
  css/style.css
  js/ba-sdk.js        (official 1.1.0, byte-identical; replaced at publish)
  js/rng.js           (seeded deterministic RNG)
  js/core.js          (pure physics/score/spawn logic, Node-testable)
  js/game.js          (canvas, input, loop, SDK, UI)
  locales/{en,de,nl,ru,fr,es}.json
  catalog/{en,de,nl,ru,fr,es}.json
  assets/{cover.webp,screen-1.webp,screen-2.webp}
  README.md
  SELF-CHECK.md
  pack.py
tests/unit/test_archer_package.py
tests/integration/test_archer_import.py
tests/js/archer.test.mjs
docs/... (ARCHER_GAME_SPEC, progress, acceptance, owner list)
```

## 3. Механика

- 60 s round; fixed timestep 1/120 s, accumulator capped; rendering independent.
- Pointer Events: angle from archer to pointer, clamped 15°..165° upward;
  hold 0..1.2 s → power exponential 0.18..1.0; release shoots.
- Ballistic: speed 520..1180 px/s, gravity 980 px/s²; preview dotted path.
- Four target classes with distinct silhouettes, motion, radius, value:
  `sun` (36 px, 20 pts, sine drift), `wisp` (22 px, 35 pts, fast zigzag),
  `guardian` (56 px, 12 pts, slow vertical patrol, armored ring),
  `phoenix` (30 px, 75 pts, rare, lifetime 4 s, circular flight).
- Combo: hit increments streak; multiplier `1 + floor(streak/3)` capped 5;
  miss resets streak. Every shot resolves exactly once; no "arrow left on
  screen" logic.
- Phases: 0–15 / 15–30 / 30–45 / 45–60 s control spawn interval, target mix,
  speed, simultaneous cap (max 6), not pure speed.
- Audio: WebAudio generated tones only after gesture; toggle.
- Pause: manual, blur, visibility, host pause; timer uses game-time only.
- Result once per session; retry only on retryable transport/5xx errors; guest
  normalized by SDK.

## 4. Tests

- Node: power bounds/monotonicity, angle clamp, ballistic positions/determinism,
  hit test, miss, combo/multiplier/score, accuracy, 60 s finish, pause/resume,
  no double submit state machine.
- Python package: required files, manifest, locale/catalog parity, forbidden
  APIs, byte-identical SDK, reproducible ZIP, assets budgets.
- Import: isolated-worker path, card/runtime/translations/assets, publish.
- Browser: PC/mobile viewport, iframe, SDK handshake/result/leaderboard,
  console, update/rollback, Neon Snake regression.

## 5. Risks / stop conditions

- Source prototype missing → concept from brief; do not claim faithful port.
- No external/paid art or audio; all vector canvas + generated tones.
- Do not alter platform components. If a platform defect blocks publication,
  document and propose separately.
- Stop before production deployment; staging remains owner-gated.
