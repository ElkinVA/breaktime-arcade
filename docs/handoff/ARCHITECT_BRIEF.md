# ARCHITECT_BRIEF — routing context for `autonomy-architect`

**Updated:** 2026-11-23. This is a compact routing map, not a substitute for the
normative ТЗ. Refresh it when NOW/PROJECT_STATUS changes materially. Before
proposing a task, read the exact specification section or file that the task
depends on; do not re-read whole registers unless this brief marks an
ambiguity.

## Priority

1. Continue Breaktime Arcade product work: App F runtime gaps, catalog,
   accounts, CRM, game-facing features.
2. AI HQ is frozen: propose control-plane work only for a concrete operational
   defect, never cosmetic hardening.
3. Do not propose owner-only external actions (staging/production deploy,
   domains/TLS, S3/CDN, legal texts, email provider, real game rights).
4. Prefer bounded, testable tasks with observable acceptance criteria. Do not
   duplicate READY/queued tasks supplied in the orchestrator prompt.

## Current product state (verified)

- Project is **framework, not MVP**; Stage 0/1 not formally closed. Agent
  technical acceptance ≠ owner product acceptance.
- Implemented and technically reviewed slices:
  - core, accounts §2.10 (PARTIAL), staff 2FA (PARTIAL), catalog
    (PARTIAL: published-only, filters, search, detail/genre/HTMX), i18n
    (6 locales), theme, CRM backup/restore-check, dev-lite/staging nginx.
  - App F server slices: session, result, leaderboard, storage, playtime,
    ratings, popularity — implemented, awaiting owner product acceptance.
  - App F runtime review A+B/C: SDK/host/player/play, origin/session/CSRF/
    eventLog/storage race fixes; code+security review ACCEPT.
  - Games: `games-src/archer` v1.3.3 and Neon Snake package were imported,
    published and exercised live through CRM → zip-worker → runtime.
- `games-src` as a general source tree is not complete; new games are added
  only as ZIP per the product invariant.
- Remaining product gaps (verify in BACKLOG/PROJECT_STATUS before use):
  App F runtime race/idempotency tests and live E2E coverage; catalog rating
  vote UI/CRM diagnostics; accounts history/records/email/legal texts; 2FA
  CRM step-up; retention classes; moderation/antifraud owner gaps.
- CRM ratings moderation: `/crm/moderation/` filters by game/value/visibility
  with average and per-value distribution (`ARCADE-CRM-RATINGS-001`,
  `c577416` + fixes).
- CRM taxonomy: `/crm/genres/` and `/crm/tags/` CRUD with translations,
  delete guards and requires-translation queue (`ARCADE-CRM-TAXONOMY-001`,
  `98b848c` + fixes).
- CRM customer accounts: `/crm/users/` search/filters, detail, block/unblock,
  deletion window, export; step-up and staff-target guards
  (`ARCADE-CRM-USERS-001`, `4095ed8` + fixes). R-049 follow-ups now abort
  open SDK sessions on block and clear tombstone credentials
  (`a9e7d2b`, `08ab9c7`); narrow create_session race remains.
- App F concurrency/idempotency coverage: result/leaderboard races, rating
  limits, storage If-Match and Idempotency-Key (`ARCADE-APPF-RACE-TESTS-001`,
  `7af18bb`).
- Catalog genre pages: paginated with sort/filter persistence and
  canonical/noindex parity (`ARCADE-CATALOG-GENRE-PAGINATION-001`,
  `0c4e64d`).
- CRM game records: read-only current/archived epoch board in the game card
  with public ordering parity and pagination (`ARCADE-CRM-GAME-RECORDS-001`,
  `db8a835` + `551e73e`).
- CRM artifact downloads: staff-only original ZIP, runtime zip and per-version
  reports with step-up for binary artifacts (`ARCADE-ARTIFACTS-DOWNLOAD-001`,
  `f8c3a52` + `91c9c0f`); R-050 TOCTOU residual.
- CRM SEO diagnostics: `/crm/seo/` reports empty descriptions, duplicate
  titles, missing alt and incomplete translations by language
  (`ARCADE-CRM-SEO-DIAGNOSTICS-001`, `f5474d8`).
- Slug hardening: shared fallback constant, race-safe history insert and
  cross-language negative test (`ARCADE-SLUG-HISTORY-HARDENING-001`,
  `bf33191`).
- Catalog slug history: changed Game/GameTranslation slugs return 301 to the
  current canonical URL (`ARCADE-CATALOG-SLUG-301-001`, `cf0936c`).
- App F retention cleanup: daily beat tasks for sessions (30d, result-linked
  excluded), play credits (90d), import drafts (7d), guest storage TTL
  (`ARCADE-RETENTION-001`, `8e42426`).
- Token observability: OBS-001 success invocations and OBS-002 lifecycle
  events are implemented; timeout/cancel/interrupted usage remains unknown and
  must not be estimated.

## Non-negotiable architecture and product rules

- Published games are public without registration; guests play but their
  results never enter records and never transfer to an account.
- Each game has its own leaderboard per epoch; no global rating. Rating and
  record are independent.
- Exactly one mandatory primary genre; tags/extra genres optional.
- Email optional; verified email is the only self-service password recovery.
- One game failure must not break the portal.
- Game language = site language; missing locale = fallback + coverage badge.
- Game add/update only via ZIP; no manual re-entry of fields. Original ZIP is
  byte-identical; runtime is a separate copy with replaced SDK; publish only
  the runtime.
- Portal/CRM/API are the main domain; every game is a separate origin on a
  separate registered domain, not a portal subdomain. Game code never runs in
  Django; a static runtime bundle is published.
- SDK is the only game↔platform channel; validate origin, source window,
  schema, session, nonce, expiry, state.
- Launch ticket is a one-time parent-page secret; never pass it into the
  iframe.
- Stack is frozen: Python 3.14, Django 5.2 LTS, DRF, PostgreSQL 18 (psycopg 3),
  Redis cache/broker separated, Celery, Nginx, Gunicorn, Compose, Django
  Templates + HTMX 2 + Vanilla JS ES2022 + Tailwind v4. No React/Vue/SPA/
  Alpine; no SQLite tests; no floating production versions.
- Protected files: `CLAUDE.md`, `technical_specification/`, `.env*`, `certs/`,
  `creds/`, `.claude/hooks` and settings. Never propose changing them.

## Where to look (targeted only)

- `technical_specification/` — normative BA-PLAT-4.2 / BA-GAME-2.2 / BA-SDK /
  BA-ENV. Read only the section needed for the proposed task.
- `docs/decisions/OWNER_DECISIONS.md` — only section **A** is approved owner
  decisions. Read a specific decision by ID if the task depends on it.
- `docs/status/BACKLOG.md` — queue/status; the orchestrator prompt already
  includes the current task list, so do not re-read the whole file.
- `docs/status/PROJECT_STATUS.md` — panorama and residuals; read only the
  section relevant to a proposed task.
- `docs/handoff/NOW.md` — current work/blockers; read only the relevant
  section.
- App F runtime plan/report: `docs/tasks/APPF-RUNTIME-REVIEW-001_PLAN.md`,
  `docs/foundation/APPF-RUNTIME-REVIEW-001_REPORT.md`.
- Code: use Grep/Glob and Read only the files needed to judge feasibility.

## Output contract

Return exactly one JSON object with `tasks[]`. Each task: `id` (`ARCADE-` or
`AUTONOMY-`), `title`, `priority`, `acceptance[]`, `dependencies[]`. Tasks must
be bounded, testable and observable. If nothing useful exists, return
`{"tasks": []}`.
