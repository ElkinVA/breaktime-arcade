# ARCADE-GENRE-DISCOVERY-STAGE-001 — milestone report

## Goal

Complete the public discovery path:

`home → genres → genre landing page → game card → game detail`

The milestone absorbs READY task `ARCADE-HOME-GENRES-BLOCK-001` and adds the
bounded genre-page completion required by §2.6/§2.8/§2.19. It does not touch
LR-4, protected paths, BLOCKED tasks or schema.

## Base and branch

- Base: `review/platform-integration-baseline-20261128` at `fb2b45f`
  (PR #1 technical CI green; Draft/open/unmerged).
- Branch: `feature/ARCADE-HOME-DISCOVERY-001`.
- Implementation commits: `9f30113`, `3e39a5f`, `4f461e8`.
- A later docs commit records QA/review/CI evidence.

The branch is stacked on the baseline review branch. It must not be turned
into a mixed PR against `main` until PR #1 is owner-integrated; after that,
create a fresh branch from updated `main` and cherry-pick the milestone
commits, verifying the diff contains only this milestone.

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

### Tests

- `tests/integration/test_home_genres.py` — localized links and order,
  home SEO canonical/description/hreflang, empty-genre omission.
- `tests/integration/test_genre_seo.py` — localized description/count,
  sort where supported by existing card projection, canonical, hreflang,
  JSON-LD, English fallback, empty genre page.
- `tests/e2e/test_genre_discovery_e2e.py` — BA_E2E-gated 360px home →
  genre navigation journey.
- Existing home/catalog/SEO/i18n/genre-pagination suites remain in the
  regression matrix.

## Verification

| Check | Result |
|---|---|
| Targeted home/genre/catalog tests | 14 passed; existing home/catalog regression included |
| Full fresh-DB pytest | **1402 passed, 19 skipped, 1 warning; 88.34% coverage; 883.37 s; exit 0** |
| Ruff | pass, 542 files formatted |
| Mypy | pass, 413 source files |
| Django check | no issues |
| makemigrations check | no changes detected |
| JS | not affected |
| Browser E2E locally | not run; dev-lite web unhealthy |
| GitHub CI | pending; no feature PR/credentials |

## QA / Reviewer

Independent code review: **ACCEPT** after fixing two blockers:
- cross-language genre-slug 404/canonical mismatch (now 301 to the
  language-appropriate slug);
- home SEO reading the catalog namespace instead of the new home strings
  (now `namespace="home"`).

Independent QA: **PASS** for targeted/static evidence. QA verified the
data-only migration, targeted home/genre suites, adjacent catalog/home/SEO
a11y tests and the cross-language slug redirects; it did not claim the full
suite or browser E2E.

## Residuals

- Product acceptance remains owner-level.
- Genre page sort is wired through the existing filter/card projection;
  optional filter-parity expansion was deliberately not added.
- E2E is code-only locally; the new BA_E2E-gated test was not executed. The local suite reports 19 skipped; hosted CI requires a PR and a healthy stack.
- Full local run is 1402 passed / 19 skipped on fresh DB; the extra skip is the new module-level E2E gate.
- The feature branch is stacked on PR #1; no PR was created and no merge or
  force operation occurred.
- The feature branch has not been marked product-accepted.
