# ARCADE-P4 — Operational Hardening & First Real Game

**Started:** 2026-11-22
**Base:** `99ea95a` (P3 isolated worker accepted; Product Acceptance Report).
**Status:** IN PROGRESS. This file is the live journal; final report is
`ARCADE_P4_ACCEPTANCE_REPORT.md`.

## 1. Audit baseline

- P3 worker: durable `ZipExtractionJob`, isolated `zip-worker`, no in-process
  extraction, source/hash verification, cleanup split (default worker).
- ZIP storage today: per-archive limits, worker disk reserve, TTL cleanup;
  **no system-wide quota** (R-033).
- Upload retention today: uploads cleaned after successful import, abandoned
  uploads via `cleanup_zip_uploads` TTL; policy not fully documented (R-037).
- Import waits synchronously up to 75 s in the CRM request (R-041).
- Staging runtime: base compose has runtime volume/env/init; **no `.env.staging`
  in environment**, so live staging remains NOT TESTED (R-042).
- Approved game concept exists in `technical_specification/ts_game.txt`:
  **Neon Snake** (`neon_snake`), arcade, six languages, seeded RNG, SDK
  result/leaderboard/storage, mobile support. `games-src/neon_snake` is an
  empty scaffold.
- Real game E2E and first publication are not done.

## 2. Work plan

| ID | Scope | Status |
|---|---|---|
| P4-A1 | R-033 system-wide ZIP quota/reservation/free-space behavior | IMPLEMENTED (`ARCADE-P4-STORAGE-001`) |
| P4-A2 | R-037 retention policy + active/completed/failed/abandoned cleanup, restart/retry tests | IMPLEMENTED (`ARCADE-P4-STORAGE-001`) |
| P4-A3 | R-041 synchronous-wait analysis; async only if justified | DONE: keep sync; `docs/audits/R-041_SYNC_WAIT_ANALYSIS.md` |
| P4-A4 | staging template/instructions/ownership/runtime/backup/ZIP checks; live only when `.env.staging` exists | DONE (prepared): `docs/runbook/staging_verification.md`, `verify_staging_p4.sh`; live **NOT TESTED/BLOCKED** |
| P4-A5 | resilience: concurrent imports, worker/broker failure, redelivery, duplicate, cleanup failure, disk pressure, recovery | IMPLEMENTED: quota/free-space/duplicate/cleanup rerun/broker-failure tests; load/stress not performed |
| P4-A6 | preserve full Pro Review JSON/findings/fixes/confirmation/not-tested | DONE (available evidence): `docs/audits/ZIP_WORKER_REVIEW_EVIDENCE.md`; original P3 reviewer JSON was not persisted |
| P4-B1 | implement Neon Snake as a real game package with full assets/locales/SDK behavior | IMPLEMENTED (`d1ebc41`); independent review **ACCEPT**, major fixed/closed |
| P4-B2 | full E2E: build → validate → worker → CRM → publish → public/iframe → SDK result → leaderboard; update/rollback/mobile/console | DONE live on dev; details in acceptance report |

## 3. Decisions

- **Game concept:** use the approved `neon_snake` concept from
  `technical_specification/ts_game.txt`; do not invent a random new game.
- **No AI HQ changes.**
- **No production deploy, no paid providers, no fabricated staging
  credentials.**
- **P4 completion gate:** quota, retention, resilience evidence, real game
  import/publish/runtime, and honest remaining limitations.

## 4. Journal

- 2026-11-22: baseline audited; P4 plan recorded. No code changes yet.
- 2026-11-22: `ARCADE-P4-STORAGE-001` implemented (Developer
  `deepseek-flash[1m]`): system-wide quota over uploads+artifacts+packages with
  shared `zip_quota` volume/flock reservations and min-free check; stable
  `X_STORAGE_QUOTA`/`X_STORAGE_FREE_SPACE`/`X_STORAGE_QUOTA_STATE` codes;
  active-aware, idempotent retention cleanup; policy
  `docs/runbook/zip_retention.md`; compose/env-template storage configuration.
  Tests cover concurrent reservations, exhaustion, free-space pressure,
  duplicate import, cleanup rerun/restart and preservation of published
  runtimes. Not tested: live staging/.env.staging, hard FS quota, stress/load.
- 2026-11-22: strict quota follow-up `16fb095` (2× archive reservation,
  fail-closed `statvfs`) accepted by Pro reviewer.
- 2026-11-22: `ARCADE-P4-NEON-SNAKE-001` implemented in an isolated
  worktree (Developer `deepseek-flash[1m]`), imported and published through
  the live CRM/worker; game commits `d1ebc41`, catalogue/media fixes
  `5f8bd2b`.
- 2026-11-22 live: CRM upload of `neon_snake-1.0.0.zip` → zip-worker
  `zip.extract`/`zip.complete` (23 files, 131 ms) → card v1.0.0 published;
  public detail/play/iframe loaded; authenticated session result `saved`,
  rank 1, `heuristic_validated`, credited 30 s; leaderboard 200; v1.1.0
  update published; rollback to v1.0.0; bad ZIP rejected with
  `V_MANIFEST_SCHEMA`.
- 2026-11-22 defects found/fixed during live game acceptance: imported media
  was `0640` (nginx 403), catalogue detail did not render cover/screenshots,
  HTMX injected an inline `<style>` blocked by CSP, 360px header overflow.
- 2026-11-22 fresh gate after fixes: **966 passed, 12 skipped**; Browser E2E
  **18 passed**; sandbox game package **13 passed**, import **1 passed**,
  catalog public **11 passed**, pipeline **15 passed**.
