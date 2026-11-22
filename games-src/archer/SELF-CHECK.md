# Archer — self-check

Format: requirement → status → evidence. **DEFERRED** means the check needs
the merged portal browser/iframe and is not claimed as passed here.

1. **Package structure, UTF-8/LF, no service files.**
   **PASS (static).** `tests/unit/test_archer_package.py`; reproducible
   `pack.py`; no `pack.py`/`dist/` in the ZIP.
2. **Manifest, score bounds, SDK 1.1.0, six languages, empty external
   origins.**
   **PASS (static).** Manifest schema/semantic validation and import test.
3. **Official SDK, no duplicated platform implementation.**
   **PASS.** `js/ba-sdk.js` is byte-identical to `sdk/1.1.0/ba-sdk.js`;
   the platform replaces it at publish.
4. **No forbidden APIs/URLs/storage/Math.random.**
   **PASS (static).** Security scan and source assertions cover `game.js`,
   `core.js`, `rng.js`.
5. **Start → aim → draw → release → hit → result.**
   **IMPLEMENTED.** Fixed-step simulation; preview path; result after 60 s.
6. **Power and ballistic physics.**
   **PASS (Node).** Bounds/monotonicity, deterministic trajectory, gravity,
   segment/circle collisions.
7. **Frame-rate independence.**
   **IMPLEMENTED.** Fixed 1/120 s accumulator capped at 0.1 s/frame with a
   240-step safety; rendering is separate.
8. **Combo correctness.**
   **PASS (Node).** Every shot resolves once; three hits raise multiplier,
   miss resets; no arrow-count reset bug.
9. **Four distinct target classes.**
   **IMPLEMENTED.** Sun disc, swift wisp, stone guardian, limited-time
   phoenix; distinct silhouette, size, motion, value and effects.
10. **Difficulty phases.**
    **PASS (Node/static).** Four 15 s phases change interval, mix, cap and
    target behaviour; max active targets 6.
11. **Pause/resume/cancel.**
    **IMPLEMENTED.** Pointer capture, pointercancel, blur, visibility,
    host pause; no shot on cancel; timer is game-time only.
12. **Single result submission.**
    **PASS (Node).** `createSubmitState`/`beginSubmit` lock; retry only
    retryable transport/5xx paths; guest normalized.
13. **Localization.**
    **PASS (static).** Six locale files with key parity; six catalogs with
    localized card/SEO/alt text.
14. **Responsive/iframe.**
    **DEFERRED (browser).** CSS/safe-area/pointer-events; verify 360×640,
    390×844, 640×360, 1280×800, 1920×1080 after publication.
15. **No console errors / horizontal overflow.**
    **DEFERRED (browser).** Must be checked in the real iframe.
16. **SDK handshake/heartbeat/result/leaderboard.**
    **DEFERRED (live portal).** Uses only official SDK methods.
17. **ZIP validation/import/publish/update/rollback.**
    **DEFERRED (CRM live).** Package tests preflight the ZIP; live E2E is
    part of acceptance.
18. **Neon Snake regression.**
    **DEFERRED.** Must re-run after Archer publication.

## Evidence commands

```text
node tests/js/archer.test.mjs
python3 devcontrol/sandbox/run_tests.py tests/unit/test_archer_package.py
python3 devcontrol/sandbox/run_tests.py tests/integration/test_archer_import.py
```
