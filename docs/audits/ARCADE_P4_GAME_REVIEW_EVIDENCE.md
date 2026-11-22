# ARCADE-P4 Neon Snake — independent review evidence

**Дата:** 2026-11-22
**Reviewer:** `autonomy-reviewer`, `deepseek-v4-pro`, read-only.
**Scope:** `git diff 16fb095..c5e3947` (game cartridge, catalogue/media
fixes, CSP/mobile fixes, tests), plus delta of the media-directory fix.
**Status:** initial review **ACCEPT with a major finding**; delta review
**ACCEPT (major CLOSED)**; remaining minor (`except A, B` style) fixed with
`contextlib.suppress` after the delta; re-tested.

## 1. Initial verdict (verbatim JSON)

```json
{"verdict":"accept","findings":[{"severity":"major","file":"/home/elkinva/projects/ba/apps/pipeline/services/importer.py","summary":"_make_public_media() chmods only the file to 0644, not the containing media directories. Django's FileSystemStorage creates MEDIA_ROOT/games/assets with FILE_UPLOAD_DIRECTORY_PERMISSIONS=0o750, while nginx serves /media/ as nginxinc/nginx-unprivileged (uid 101) and the web/worker create files as uid 10001. On a fresh import that creates the directory, nginx cannot traverse the 0750 directory, so cover/screenshots return 403 until the next container restart (entrypoint 'chmod -R o+rX /app/media' only runs when RUN_COLLECTSTATIC=1). This leaves the follow-up acceptance criterion 'imported cover/screenshots must be publicly readable' not reliably met.","scenario":"Fresh deployment -> first import of Neon Snake -> GET /media/games/assets/neon_snake-cover.webp via nginx returns 403 because games/assets is 0750 (no o+rx). test_neon_snake_import.py:125 only asserts the file mode is 0644, not the directory mode, so it does not catch this."},{"severity":"minor","file":"/home/elkinva/projects/ba/apps/pipeline/services/importer.py","summary":"'except OSError, ValueError:' uses legacy Python 2 comma syntax. Verified via dis that Python 3.14 compiles it as 'except (OSError, ValueError):' (BUILD_TUPLE + CHECK_EXC_MATCH), so it is functionally correct on the pinned interpreter, but is non-idiomatic, misleading, and would be a SyntaxError on Python <=3.13. Should be 'except (OSError, ValueError):'.","scenario":"Anyone reading/backporting this code, or a CI job running a pre-3.14 interpreter, would hit a SyntaxError or misread the intent."},{"severity":"minor","file":"/home/elkinva/projects/ba/apps/catalog/templates/catalog/game_detail.html","summary":"width/height attributes render 'width=\"None\"' when the nullable GameAsset.width/height fields are unset (e.g., assets created outside the importer, including the test fixtures in tests/integration/test_catalog_public.py). Also _asset_alt returns '' for assets with no alt, yielding an empty alt on a meaningful image. Low impact because the importer always sets dimensions and six-language alts, but the template should guard with '{% if cover.width %}' and supply a non-empty alt fallback.","scenario":"A GameAsset created without width/height renders invalid HTML width=\"None\" height=\"None\"; browsers ignore it, but it is invalid markup and a minor a11y issue for the cover alt."}],"tested":["Byte-identity of games-src/neon_snake/js/ba-sdk.js vs sdk/1.1.0/ba-sdk.js (cmp + md5 identical)","manifest.json contract fields (id, version, sdkVersion, genre, 6 languages, score bounds, eventKinds, capabilities, limits, criticalPathBytes)","rng.js determinism (mulberry32/hashSeed, no Math.random) and index.html structure","forbidden-API scan of game.js/rng.js (no Math.random/localStorage/sessionStorage/indexedDB/document.cookie/postMessage/eval/new Function/parent.*/window.top/http(s) URLs; only relative locale fetch and boot-retry location.reload)","autotest budget (40ms x 400 ticks = 16s < 25s) and pause/resume/guest/user/autotest wiring in game.js","pack.py reproducibility (fixed 1980-01-01 timestamp, sorted entries, normalized 0644 external_attr, excludes pack.py/dist)","WebP assets valid 1280x720 (file command)","Python compile of all changed files (py_compile) and 'except OSError, ValueError' semantics via dis (Python 3.14 tuple)","media serving model: nginx-unprivileged uid 101 vs web uid 10001, FILE_UPLOAD_PERMISSIONS=0640 / DIRECTORY_PERMISSIONS=0750, dev.conf /media alias","catalog/locales content substantiveness (en/ru spot check) and tests content (unit package + integration import + catalog public)","no protected files or secrets in the diff (name-status + content review)"],"not_tested":["Full pytest suite execution (requires PostgreSQL/Docker; the '966 passed, 12 skipped' claim is from the main session, not re-run here)","Browser E2E / live stack behavior (360px no overflow, no console errors, real SDK handshake/result save) — claimed by the main session, not executed by me","ruff/mypy (not installed on the host; the clean-lint/type claim not independently verified)","Actual nginx serving of media in a running stack (directory-traversal 403 reasoned from compose/settings/nginx config, not empirically reproduced)"],"note":"The game cartridge itself (manifest, index, css, seeded rng/game JS, six locales/catalog, real cover/screenshots, README/SELF-CHECK, reproducible pack.py) is complete and substantive, and the SDK is byte-identical. The only substantive defect is the incomplete public-media fix (directory permissions); it should be addressed (chmod parent dirs to o+rx, e.g., os.chmod on the asset directory or relax FILE_UPLOAD_DIRECTORY_PERMISSIONS for this path) before claiming the 'publicly readable' criterion is met."}
```

## 2. Findings and fixes

| # | Severity | Finding | Fix | Status |
|---|---|---|---|---|
| 1 | **major** | Media directories created `0750`; nginx uid 101 cannot traverse on a fresh import → 403 | `_make_public_media()` walks from file parent to `MEDIA_ROOT`, chmod dirs `0755`; file `0644`; import test asserts dir/file modes | **fixed, delta re-review** |
| 2 | minor | Python 2-style `except A, B:` (valid in 3.14, misleading) | Codebase/ruff target is 3.14; retained consistent syntax, documented | accepted minor |
| 3 | minor | `width="None"` / empty alt when asset metadata missing | Template guards `{% if asset.width %}`; localized fallback alt from translation/technical_id | **fixed** |

## 3. What the reviewer did not test

- Full pytest, ruff/mypy, browser E2E/live stack: main-session claims only.
- Actual live nginx media serving of a **freshly created** media directory:
  reasoned, not reproduced; the live stack had an existing dir chmodded.
- Staging/production.
- Hard FS quota/load.

## 4. Delta review

After the fixes, a delta review of `git diff c5e3947 -- <changed files>` was
requested from the same Pro reviewer. Verdict: **accept**, `major_closed:
true`; `width/height`/empty-alt minors closed; header fix confirmed. The only
remaining minor was the Python-2-comma `except` form; it was replaced with
`contextlib.suppress(OSError, ValueError, NotImplementedError)` after the
delta and the import test was re-run successfully.

## 5. Independent status

The game cartridge is accepted technically by the independent reviewer;
product/legal acceptance remains owner-only. This is not a claim of full
production readiness.
