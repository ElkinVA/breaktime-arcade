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
  `c577416` + fixes); both moderation queues are paginated 50/page with
  filters and both page positions preserved (`ARCADE-CRM-MODERATION-PAGINATION-001`,
  `07a287a` + `380cd11`).
- CRM taxonomy: `/crm/genres/` and `/crm/tags/` CRUD with translations,
  delete guards and requires-translation queue (`ARCADE-CRM-TAXONOMY-001`,
  `98b848c` + fixes).
- CRM customer accounts: `/crm/users/` search/filters, detail, block/unblock,
  deletion window, export; step-up and staff-target guards
  (`ARCADE-CRM-USERS-001`, `4095ed8` + fixes). R-049 follow-ups now abort
  open SDK sessions on block and clear tombstone credentials
  (`a9e7d2b`, `08ab9c7`); narrow create_session race remains.
- Session creation, submit_result, heartbeat and storage writes are
  serialized with block/anonymise via a User row lock
  (`ARCADE-SESSION-RACE-001`/`LOCK-ORDER-001`/`STORAGE-LOCK-ORDER-001`);
  R-056 closed. Abandoned ACTIVE sessions lazily expire and are swept by a
  5-min beat task (`ARCADE-SESSION-LIFECYCLE-001`, `7da168a`); GET /play no
  longer creates a session and the player creates it via API
  (`ARCADE-SESSION-PLAY-001`, `35ae98f`); final heartbeat precedes submit
  and pagehide sends a close beacon.
- AI HQ P0: developer/QA checks run only through five exact trusted sandbox
  commands (no wildcard), source-root is task-bound, host-exec surfaces are
  protected, commit file set is Git-derived, reviewer has no Bash
  (`AI-HQ-A1`, `1f46062`); candidate is committed before QA, QA runs on the
  exact clean SHA, diff is full and verdicts are strict (`AI-HQ-A2`,
  `45a69f1`). OS sandbox R-040 and model trust remain.
- Game API throttling: create/activate/close use separate subject buckets,
  results have the Appendix E 1200/hour IP cap, and complaints are 5/day
  subject + 30/day IP (`ARCADE-THROTTLE-001`, `b953419`).
- External audit 2026-11-25 response: imports of published/hidden/archived
  cards are blocked until draft isolation; production publish requires a
  `playwright=true` report (rollback stays available); empty eventLog is
  quarantined under a verification profile; pagehide does not close a session
  with an in-flight submit. AI HQ OS sandbox, Redis broker isolation, draft
  isolation, browser runner/override and PB `is_public` remain owner-gated.
- Leaderboard rank: a non-personal-best submit returns the position of the
  user's existing best row, not the hypothetical position of the worse run;
  `is_record` is true only for a personal best that is also #1
  (`ARCADE-RANK-NONPB-001`, `df8cad6`/`910f268`). The scalar rank formula now
  lives in one `entry_rank` shared by submit and read-side queries, with a
  full tie-break test (`c7bc92e`/`40264c2`); only the `is_public` filter for
  the previous row remains open.
- Result payload: the eventLog 2 MiB limit is enforced on UTF-8 bytes, and
  lone surrogates now yield a structured validation error in both the
  serializer and semantic validator (`ARCADE-EVENTLOG-BYTES-001`,
  `ea47229`/`0a0dbfb`). Exact-boundary tests and a duplicated constant remain.
- Player: result submissions are serialized per session and share an
  idempotency key; `newSession`/`exit` await the chain before closing, so a
  restart cannot abort an in-flight result; restarts are serialized and each
  API attempt times out after 10 s (`ARCADE-SUBMIT-RESTART-001`, `24d9979`/
  `a81ec48`). JS 31/31; exit/pending-restart edge cases are a follow-up.
- Ratings: a daily task and `recalculate_ratings --dry-run/--limit` command
  recompute all vote/aggregate games in pk order, one transaction and one
  advisory lock per game, skip unchanged rows, and isolate per-game failures
  (`ARCADE-RATINGS-NIGHTLY-001`, `006aaca`/`b24ff78`/`4c5dd02`). Live beat is
  untested; `--limit` has no offset.
- ZIP security: the untrusted-input `zip-worker` no longer receives the full
  `.env`; it gets a 13-key non-secret allowlist (settings, broker, quota,
  worker limits/TTL) interpolated from `.env`, with no `env_file` in base or
  staging and a pinned empty prod overlay (`ARCADE-ZIP-WORKER-SECRETS-001`,
  `1c19af5`/`d90af22`/`1cbbec3`). Live dev worker/probe extraction passed;
  staging/prod untested; dev-lite repo mount and no-Sentry residuals remain.
- Test infrastructure: the reuse-DB fixture now reseeds every i18n
  `*_seed_*.py` migration after a transaction-test flush, discovered in
  migration order with fail-loud guards (`ARCADE-TEST-DB-SEED-001`,
  `8e5f507`/`995f5d2`); full reuse-DB suite is green (1201/13). One rare
  step-up moderation flake remains unreproduced and unfixed.
- ZIP pipeline: same-game imports serialize on a technical_id advisory
  lock and adopt a concurrently created card; V_ID_CONFLICT is distinct
  from V_VERSION_DUP, and runtime rename races adopt an identical bundle
  (`ARCADE-ZIP-CONCURRENT-IMPORT-001`, `03aaf0f`).
- ZIP pipeline: runtime bundles with no `GameVersion` reference are deleted
  after a 24 h TTL by a daily idempotent beat task; the default worker now
  mounts `runtime_data` rw, otherwise the cleanup would silently no-op
  (`ARCADE-RUNTIME-ORPHAN-001`, `34f237f`). §5.5 is closed; live beat and
  staging remain untested.
- ZIP pipeline: RUNNING extraction jobs older than 600 s are reaped to
  TIMEOUT/X_JOB_STALE by a 5-minute beat task, idempotently
  (`ARCADE-ZIP-JOB-REAPER-001`, `1687517`). Live beat untested.
- Account email security: changing/removing an email invalidates reset and
  verify tokens atomically; reset confirm rechecks current verified email
  and active status (`ARCADE-EMAIL-RESET-INVALIDATION-001`, `26d8075`).
  Submission-order race remains a documented minor follow-up.
- Backup/DR: restore-check verifies dump SHA-256 before and after
  pg_restore, rejects empty/unreadable dumps, checks required tables and
  django_migrations, records control counts (`ARCADE-RESTORE-CHECK-001`,
  `cdb567a`); live dev restore passed, staging/production untested.
- API robustness: malformed/negative Content-Length returns 400 and
  oversized returns 413, never 500 (`ARCADE-CONTENT-LENGTH-001`,
  `ab62a7d`). Restore-check hardening is the next P1 slice.
- Ratings/account integrity: blocked users' votes leave all rating
  aggregates immediately and return on unblock; vote() rechecks is_active
  under the User row lock; multi-game recalc is ordered by game id
  (`ARCADE-RATINGS-BLOCK-001`, `766029e`). Nightly recalc/backfill remains.
- CRM customer accounts: explicit idempotent block/unblock with audit and
  session revocation replaces the toggle; repeated actions are no-ops
  (`ARCADE-CRM-BLOCK-IDEMPOTENT-001`, `88c2a64`). Immediate rating-aggregate
  exclusion on block remains the next ratings slice.
- Publication safety: publish/rollback audit rows are written atomically
  with the version switch; rollback only targets previously published
  versions with green validation/autotest and matching score rules, and
  preserves hidden/archived status (`ARCADE-ROLLBACK-SAFE-001`, `ecfb419`).
  Import isolation and browser-autotest gating remain owner-gated.
- Account throttling: login/2FA/reset/registration counters use the
  dedicated noeviction throttle cache with a JSON serializer (atomic INCR);
  security-critical limits fail closed (`ARCADE-AUTH-THROTTLE-001`,
  `de08292`). Registration enforces device 3/day + IP 30/day, but the
  CSRF-derived device key rotates on login and the Appendix E challenge/
  hard-block-100 semantics remain owner decisions
  (`ARCADE-REGISTRATION-LIMITS-001`, `bbfdcaf`).
- Result integrity: verification-profile results missing `eventLog` or a
  non-empty `seed` are quarantined and never enter the leaderboard
  (`ARCADE-RESULT-VERIFICATION-001`, `1fc0e97`); empty-event heuristic
  remains a gap.
- App F concurrency/idempotency coverage: result/leaderboard races, rating
  limits, storage If-Match and Idempotency-Key (`ARCADE-APPF-RACE-TESTS-001`,
  `7af18bb`).
- Catalog genre pages: paginated with sort/filter persistence and
  canonical/noindex parity (`ARCADE-CATALOG-GENRE-PAGINATION-001`,
  `0c4e64d`).
- CRM game records: read-only current/archived epoch board in the game card
  with public ordering parity and pagination (`ARCADE-CRM-GAME-RECORDS-001`,
  `db8a835` + `551e73e`).
- Session API create response is camelCase `sessionId` only
  (`ARCADE-SESSION-API-CAMELCASE-001`, `16068f4`); `expires_at` and no-alias
  are R-054 residuals.
- Host message schemas are generated from `schemas/messages/*.json` with a
  parity test and unsupported-keyword guard
  (`ARCADE-RUNTIME-SCHEMA-SINGLE-SOURCE-001`, `f9a75d4`); build integration is
  BLOCKED on Docker assets-stage changes; R-055 await owner/contract
  confirmation.
- SDK settles pending requests on exit/newSession
  (`ARCADE-SDK-ABORT-PENDING-001`, `ebe7d30`).
- Runtime validation: host/SDK messages are schema-driven with
  `E_MESSAGE_INVALID` (`ARCADE-RUNTIME-JSONSCHEMA-001`, `855caa1`); myBest
  now matches `ba_leaderboard_data` (`ARCADE-SDK-MYBEST-001`, `20f379c`);
  R-053 schema mirroring remains.
- CRM artifact downloads: staff-only original ZIP (single-pass SHA-256 +
  verified spool), runtime zip (tree digest verified vs `runtime_hash`) and
  per-version reports with step-up (`ARCADE-ARTIFACTS-*`, `8f9f7ac`); R-050
  closed in code, E2E residual.
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
