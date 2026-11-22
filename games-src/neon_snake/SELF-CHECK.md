# Neon Snake — self-check (BA-GAME-2.2 §15)

Format: requirement → status → evidence. “Deferred” means the check needs a
browser/iframe or Node runtime that is explicitly scheduled for portal
acceptance after merge; it is not reported as passed here.

1. **Package structure, UTF-8 without BOM, LF, no service files.**
   **PASS (static).** `tests/unit/test_neon_snake_package.py` checks the
   required tree, UTF-8/LF, allowed extensions, no empty files, and no
   `pack.py`/`dist/` entries. `pack.py` itself validates sources and uses ZIP
   preflight-compatible entry metadata.
2. **Manifest fully filled, score bounds, empty `externalOrigins`,
   `storage: "sdk"`.**
   **PASS.** Schema and semantic checks in
   `tests/unit/test_neon_snake_package.py`; accepted by
   `validate_manifest()` and the isolated import.
3. **No forbidden APIs/URLs/absolute paths/`<base>`; no `Math.random`.**
   **PASS (static).** `scan_root()` returns no diagnostics; direct source
   assertions reject storage APIs, cookies, direct messaging, eval/Function,
   string timers, external URLs and `Math.random`.
4. **Starts from a local static server with a clean console; works from a
   subdirectory.**
   **DEFERRED (browser).** Entry uses only relative paths and deferred classic
   scripts. Standalone mode intentionally shows the localized SDK error screen
   because the official SDK requires the portal handshake.
5. **All declared locales work, key sets match, German does not break layout,
   unknown language falls back to `en`.**
   **PASS (static) / DEFERRED (visual).** Locale parity and placeholder checks
   pass for all six files. The loader merges portal `strings`, requested
   locale, fallback locale, then `en`; CSS uses wrapping, `min-width: 0`, and
   responsive panels. German copy is the longest and is included in the
   package.
6. **Full cycle: start → play → GAME OVER → submit → result → PLAY AGAIN →
   EXIT.**
   **IMPLEMENTED / DEFERRED (browser).** State transitions, submission,
   result screen, `ba.newSession()` reset and `ba.exit()` are implemented.
   The Python import/publish test confirms the cartridge is accepted.
7. **Guest: unlimited play, notice, no retries.**
   **IMPLEMENTED / DEFERRED (browser).** Guest and preview modes show the
   guest notice and registration invitation; a guest response is handled once
   and never retried.
8. **Autotest finishes within 25 s, in bounds, reacts to `autotest:finish`.**
   **IMPLEMENTED / STATIC PASS.** 400 ticks × 40 ms = 16 s of game time;
   listener `autotest:finish` calls immediate submit; test asserts the
   constants and listener. Runtime execution deferred.
9. **Focus loss pauses; return resumes.**
   **IMPLEMENTED / DEFERRED (browser).** `visibilitychange`, `blur`, and
   `focus` handlers pause the only animation-frame loop and suspend audio;
   only automatic pauses resume.
10. **Network loss during submission retries and does not lose the result.**
    **IMPLEMENTED / DEFERRED (browser).** Offline pauses the round; submission
    retries only temporary/network codes up to three times with backoff and
    keeps the pending result until a new round starts.
11. **360×640 and 1280×720 render without clipping or horizontal scrolling.**
    **DEFERRED (visual).** Responsive CSS covers 320×480…2560×1440, safe-area
    insets, portrait/landscape stage sizing, wrapping controls and scrollable
    panels.
12. **20 restarts: no memory/listener growth and a new seed each time.**
    **IMPLEMENTED / DEFERRED (stress).** Global listeners are bound once;
    round state, event log, particles, timers and the frame loop are reset.
    `PLAY AGAIN` takes the seed from the new session context.
13. **Sound after a gesture only; toggle works; game works muted.**
    **IMPLEMENTED / DEFERRED (browser).** Audio context is created on the
    start/toggle gesture; generated tones are optional and failures are
    swallowed.
14. **No blinking faster than 3 Hz; `prefers-reduced-motion` respected.**
    **PASS (static).** CSS uses a 2.4 s brand pulse, no strobing; the media
    query disables animation/transition and the renderer disables particles.
15. **Critical path ≤2 MiB gzip (full package ≤25 MiB).**
    **PASS (measured).** Declared and measured source critical path:
    **25,320 bytes gzip**. The import test confirms the measured value and the
    package budget; the platform recalculates after SDK replacement.
16. **Real cover/screenshots; catalog, alt and SEO text in every language.**
    **PASS (assets/content) / PARTIAL (capture).** 1280×720 WebP cover and two
    screenshots are present within 200 KB/300 KB budgets; catalog schema,
    lengths and two `screenshotAlts` per language pass. The images were
    rendered from the game's visual system rather than captured live; live
    capture is deferred to portal acceptance (documented deviation).
17. **`id` matches the regex and is not reserved; version is semver.**
    **PASS.** `neon_snake`, version `1.0.0`; schema and `pack.py` checks pass.
18. **Opaque-origin mode: no localStorage/IndexedDB/cookies.**
    **PASS (static).** Forbidden-storage scan passes; all persistence goes
    through `ba.storage` with versioned keys.

## Evidence commands

* `python3 devcontrol/sandbox/run_tests.py tests/unit/test_neon_snake_package.py`
* `python3 devcontrol/sandbox/run_tests.py tests/integration/test_neon_snake_import.py`
* `/home/elkinva/projects/ba/.venv/bin/python -m ruff check ...`
* `/home/elkinva/projects/ba/.venv/bin/python -m mypy ...`

Browser/iframe, Node event-log execution and stress checks are intentionally
not claimed here; they are part of portal acceptance after merge.
