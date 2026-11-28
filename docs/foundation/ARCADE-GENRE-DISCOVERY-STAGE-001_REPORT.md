# ARCADE-GENRE-DISCOVERY-STAGE-001 — milestone report

**Status: Partial.** Code/test closeout on `b2309a7`; genre browser E2E 2/2
and independent reviewer/QA complete. The full fresh-DB Python gate is **not
green** (two reruns, one unrelated time/order-sensitive failure each, both
passing in isolation), and the full local browser suite is 37/38 due the
pre-existing LR-3 host-loss R-060. Product acceptance remains owner-level.

## Goal

Complete the public discovery path:

`home → genres → genre landing page → game card → game detail → play/runtime`

The milestone absorbs READY task `ARCADE-HOME-GENRES-BLOCK-001` and adds the
bounded genre-page completion required by §2.6/§2.8/§2.19, followed by the
owner-requested acceptance closeout: a real deterministic browser journey,
redirect/ambiguity regressions and a local dev-lite recovery. It does not touch
LR-4, protected paths, BLOCKED tasks or schema.

## Base and branch

- Base: `review/platform-integration-baseline-20261128` at `fb2b45f`
  (PR #1 technical CI green; Draft/open/unmerged).
- Branch: `feature/ARCADE-HOME-DISCOVERY-001`.
- Earlier implementation commits: `9f30113`, `3e39a5f`, `4f461e8`, `901cdc7`.
- Acceptance closeout code commit: `b2309a7`.
- A docs-only commit follows the closeout code commit.

The branch is stacked on the baseline review branch. It must not be turned
into a mixed PR against `main` until PR #1 is owner-integrated; after that,
create a fresh branch from updated `main` and cherry-pick the implementation
and closeout commits, verifying the diff contains only this milestone.

## Implemented

### Home discovery

- `apps/catalog/views.py`: home context now includes localized `genres` and
  `seo`.
- `apps/catalog/templates/catalog/home.html`: localized `home-genres` nav
  block after the New block; each link points to the localized
  `catalog:genre_detail` slug. The block is omitted when `genres` is empty.
  Popular/Rated/New blocks and the catalog CTA remain unchanged.
- Home SEO: canonical `/<lang>/`, description, hreflang alternates and
  x-default through the existing SEO partial.
- `apps/i18n/migrations/0016_seed_home_discovery_strings.py`: data-only en/ru
  strings for `home.block_genres`, home meta title/description, genre game
  count, Apply/All games and `nav.games`; no schema change.

### Genre landing page

- `apps/catalog/services/seo.py`: `home_seo()` and `genre_seo()` add
  localized title/description, canonical, active-language hreflang +
  x-default, BreadcrumbList and CollectionPage JSON-LD.
- `apps/catalog/views.py`: genre page resolves localized translation with
  existing English fallback, passes description, image, game count, active
  sort filters and SEO; primary/additional genre filtering and pagination
  remain unchanged.
- `apps/catalog/templates/catalog/genre_list.html`: breadcrumb navigation,
  localized H1/description, optional genre image with alt, game count,
  sort control, empty state, existing card grid and pagination.
- Existing slug/301 behavior and deep-page noindex are preserved.

### Acceptance closeout

- Genre pages now pass page-specific localized alternate paths to the shared
  language switcher. This prevents a same-slug collision across genres from
  opening a different genre when only the URL language prefix changes.
  `language_url` accepts only local absolute paths and falls back to its
  existing prefix swap for any external/non-local value.
- Cross-language genre 301s continue to preserve the raw query string,
  including `sort`, `page` and unrelated tracking parameters. The canonical
  URL of the redirected page keeps the page language and active query state.
- A same-slug ambiguity test covers two genres where `shared` is English for
  one and Russian for the other: the current language wins deterministically,
  and both language-switcher links lead back to the same genre.

### Dev-lite recovery

- The dev-lite `web` container was unhealthy with
  `PermissionError: [Errno 13] Permission denied: '/app/config/urls.py'`.
  Source files were mode `600` owned by the host developer while the container
  runs as UID `10001`.
- Local recovery used `chmod -R a+rX apps config templates static` followed by
  `docker compose restart web`. No source content, secrets, protected files or
  volumes were changed.
- The restarted web container applied `i18n.0014`–`0016`, passed Django system
  checks and returned HTTP 200 on both `http://127.0.0.1:8000/healthz` and
  `https://portal.test:8443/healthz`. This repair is environmental and is not
  part of the Git diff.

### Browser E2E

- `tests/e2e/test_genre_discovery_e2e.py` is now a full EN and RU journey:
  localized home → home genre block → genre page → game card → published game
  detail → play page → runtime iframe loading.
- The module creates a disposable genre, game, translation, version and a
  minimal static runtime (`index.html` + JavaScript) through `manage.py shell`
  in the live dev stack. It never selects a random existing game for the
  scenario. `--host-resolver-rules` maps the generated game origin without
  editing system files.
- The test proves the iframe loaded the generated runtime from nginx, the
  runtime script executed (`data-runtime-script="executed"`) and the play page
  did not show its start-error status.
- Teardown removes the exact runtime files, sessions, translations and
  version, then archives the Game row because PostgreSQL permanently forbids
  physical `catalog_game` deletion. The fixture genre is deleted after the
  Game reference is cleared.

## Verification

| Check | Result |
|---|---|
| Genre browser E2E (`BA_E2E=1`) | **2 passed (en, ru); exit 0; ~46 s** |
| Full `tests/e2e` suite | **37 passed, 1 failed** — pre-existing LR-3 host-loss test (`#claim-host` timeout; R-060 stale local runtime), unrelated to genre discovery |
| Targeted six-file integration fresh DB (QA) | **97 passed** |
| Wider nine-file targeted selection (implementer) | 108 passed (six QA files + catalog accessibility/structured-data/sitemap) |
| Full fresh-DB pytest | **two runs: 1405 passed, 19 skipped, 1 failed each; failures differ and are outside this diff** |
| Ruff | 497 files formatted; all checks passed |
| Mypy | Success: no issues in 371 source files |
| Django check | no issues |
| Django check --deploy | only expected dev warnings (HSTS/SSL/DEBUG/SECRET_KEY) |
| makemigrations check | no changes detected |
| migrate --plan | no planned operations |
| JS | not affected |
| Hosted GitHub CI | not run; no feature PR |

Full fresh-DB note: the two attempts each failed one test outside the
`b2309a7` diff — CRM rating restore in the first, GameSession activation
expiry in the second. Both tests pass in isolation; the failures are
order/time-sensitive and the full gate is **not green**. They are retained as
a residual, not reported as PASS.

## QA / Reviewer

Independent code review of `b2309a7`: **ACCEPT**. No blocker was found. The
reviewer cross-checked the SEO alternate producer, the language-switcher
consumer, the genre resolver and the E2E fixture. It recorded these
non-blocking residuals: latent backslash/dot-segment override validation for
future callers, the no-target-translation slug fallback, seed cleanup only
after a successful seed, and direct runtime-file creation instead of the real
import path.

Independent QA of `b2309a7`: **PASS WITH RESERVATIONS**. On a fresh test DB it
ran the six targeted integration files (**97 passed**), reran both full-gate
failures in isolation (**1 passed** each) and together with their modules
(**70 passed**), and ran the new EN/RU browser E2E (**2 passed, ~46 s**).
nginx logs independently showed both generated runtime requests returning 200
and the test proved the served JS executed. Cleanup left zero fixture genres,
translations, published fixtures or runtime directories; one archived Game
row per run remains by design. QA confirmed the full gate is not green and
retained the override-validation, fallback-collision, minimal-runtime and
count-discrepancy reservations below.

## Residuals

- Product acceptance remains owner-level; this report records technical
  closeout only.
- The E2E runtime is a deterministic minimal HTML/JS bundle served through
  nginx, not a re-import of a production game ZIP. It proves the play-page
  runtime URL, iframe load, script execution and cleanup path; full cartridge
  behavior remains covered by the existing game E2E suites.
- The fixture's Game row is archived rather than physically deleted following
  the permanent `catalog_game` DELETE invariant; UUID-suffixed archived rows
  accumulate.
- Genre sort is wired through the existing filter/card projection; optional
  filter-parity expansion was deliberately not added.
- If a genre has no translation for a target language, the language switcher
  falls back to the genre-code path. A pathological collision between that
  code and another genre's translated slug cannot be resolved without a
  product-level canonical identifier; no hidden workaround was added. The
  current test covers the both-translated collision; the no-target-translation
  fallback needs a separate regression/product decision.
- `_local_override` rejects external and protocol-relative values, but a
  backslash or dot-segment value such as `/\evil.example` remains a latent
  validation gap for future callers. The sole current producer builds
  `/{language}/genres/{slug}/` from Citext slugs/codes that cannot contain
  `/`, so this closeout does not expose it. Hardening and tests are a
  follow-up.
- The browser fixture cleans up after a successful seed; a mid-seed failure
  (before the fixture yields) can leave partial dev-only rows. The E2E writes
  a minimal runtime directly rather than exercising the real import/atomic
  publish path; the existing game-runtime E2E covers the real pipeline.
- The full local browser suite is **37 passed, 1 failed**: the pre-existing
  LR-3 host-loss test timed out waiting for `#claim-host`, matching R-060
  (local published runtime is older than source and cannot be re-imported
  because of `V_PUBLISHED_UPDATE_BLOCKED`). The genre E2E and all other browser
  scenarios passed; CI uses a fresh DB/runtime.
- The feature branch is stacked on PR #1; no PR was created and no merge or
  force operation occurred.
- The feature branch has not been marked product-accepted.
