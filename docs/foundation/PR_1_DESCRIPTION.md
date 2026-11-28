## Scope

Platform Integration Baseline + ChatGPT follow-up. This is a **Draft PR for CI validation and independent review**; do not merge until the owner accepts the block.

- Review branch: `review/platform-integration-baseline-20261128`
- Base: `main` (`b59cc12`)
- Current HEAD: `e7b1b0e19588c54c6e7ab6c2f882a1243b8ce15f`
- Code/test HEAD: `21beb4b`
- PR state: Draft / open / unmerged. Product acceptance is pending.

## Changes in this block

- Heartbeat preflight limits before resolving `GameSession`; preserves 3/min per active session, adds authenticated subject and guest shared-IP preflight, skips session lookup after a preflight denial, and caches guest identity per request.
- Password-reset token creation and invalidation remain under the User row lock; SMTP delivery happens after commit, with neutral failure handling.
- CRM browser E2E uses exact per-run teardown, archives its exact Game row rather than violating the permanent delete trigger, and validates real ZIP contents.
- `make lint` now matches the GitHub CI Ruff scope.
- Existing product work includes account race fixes, catalog/SEO improvements, ratings race coverage and related tests.

## GitHub CI

CI #174: https://github.com/ElkinVA/breaktime-arcade/actions/runs/46126028661

- `quality`: success — Python 1406 passed, 8 skipped, 1 warning; coverage 88.32%.
- `frontend`: success.
- `e2e`: success — Browser E2E 36 passed in 321.37 s.
- `image`: success.
- `django-next`: success (additional; `continue-on-error: true`).

CI #172 and #173 also passed on the preceding documentation and test-only HEADs.

## Local verification

- Full fresh-database local pytest at `636259f`: **1395 passed, 18 skipped, 1 warning; 88.29% coverage; exit 0**.
- The local dev-lite `web` container lacks `git`, causing ten tests (nine autonomy-worktree plus one devcontrol) to skip locally while GitHub runs them. The local run predates test-only `21beb4b`; comparable local is 1396/18 vs CI 1406/8. This is an environment difference, not a failure.
- Ruff: 539 formatted; mypy: 413 source files; Django check/migrations: clean; JS: 47/47.
- Browser E2E was not run locally because the dev-lite web service is unhealthy; GitHub `e2e` passed.
- Targeted heartbeat and password-reset tests passed.

## Outstanding disclosures

- E2E teardown intentionally leaves append-only audit evidence and archives the exact Game row because `catalog_game` has a permanent DELETE trigger. Archived UUID-suffixed rows accumulate.
- Preflight rates (30/min subject, 120/min guest IP) are implementation-defined; the normative per-session heartbeat rate remains 3/min.
- Authenticated users have no aggregate per-IP bound; per-subject 30/min and per-session 3/min still bound each account.
- Expired/foreign invalid-bucket behavior is implicit in the unknown-UUID test.
- `make fmt` remains narrower than `make lint`.
- No product acceptance is claimed.

## Safety

No merge to `main` is requested. Keep this PR in Draft pending independent review and owner acceptance.
