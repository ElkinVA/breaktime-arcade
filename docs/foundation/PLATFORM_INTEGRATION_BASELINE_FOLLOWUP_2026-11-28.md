# Platform Integration Baseline — ChatGPT Follow-up — 2026-11-28

## Scope

Review branch: `review/platform-integration-baseline-20261128`.
Base before follow-up: `99cb379` (nine product commits, formatting commit,
baseline docs). Follow-up commits are additive; no history rewrite.

New commits:

- `fc00333` — heartbeat preflight limits before session lookup.
- `b6cb1d1` — password-reset SMTP delivery after the User lock releases.
- `ba36d8e` — CRM E2E fixture teardown and ZIP content checks.
- `3716d52` — `make lint` scope aligned with GitHub CI.
- `5bc8a81` — shared IP preflight is guest-only; authenticated users keep
  the subject preflight and are not caught by a NAT IP cap.
- `636259f` — CRM teardown no longer attempts the forbidden physical
  `Game` delete; it archives the exact fixture row after clearing the
  version and leaves the append-only audit row intact.

## 1. Heartbeat throttling

`apps/gameplay/api/throttling.py` and `apps/gameplay/api/views.py`:

- Added authenticated-subject preflight (`heartbeat_preflight_subject`,
  30/min) and guest shared-IP preflight (`heartbeat_preflight_ip`, 120/min).
  Authenticated users are exempt from the guest IP cap so an office NAT does
  not degrade legitimate players.
- Preflights never query `GameSession`; guest preflight is IP-only, so an
  arbitrary UUID or guest cookie cannot mint a key per request.
- The existing per-session `heartbeat` limit remains 3/min and is keyed by the
  resolved active session.
- DRF evaluates every throttle before raising. A preflight denial therefore
  records a request flag; `SessionScopedRateThrottle` sees it and returns
  without resolving the UUID or loading a guest identity. The preflight still
  causes the 429.
- Guest identity resolution is cached request-locally and reused by the
  subject key and per-session lookup.
- Existing fail-open behavior for the public heartbeat throttle is preserved.

## 2. Password reset delivery

`apps/accounts/services/email.py` and `apps/accounts/views.py`:

- `prepare_password_reset_email()` invalidates old reset tokens and creates the
  new token while the User row lock is held.
- It returns an immutable `PasswordResetDelivery` snapshot containing the
  recipient address and raw token.
- The view calls `send_password_reset_email()` only after the atomic block has
  exited, so SMTP latency cannot hold the User lock.
- SMTP errors are logged and do not turn the committed request into a 500.
  The user-facing message says the request was accepted; it does not claim
  successful delivery when SMTP failed.
- Existing reset-request/email-change/verify race scenarios remain; the
  reset-request pause now occurs inside token preparation while the lock is
  held.

## 3. CRM E2E cleanup

`tests/e2e/test_crm_e2e.py`:

- The seed now returns exact user IDs, game/version/complaint IDs and
  package/runtime paths for the current run.
- A function-scoped fixture yields the seed and tears down only those exact
  IDs/paths after each scenario.
- Cleanup removes the exact package/runtime files and disposable users first,
  then the complaint and version, clears `current_version`, and archives the
  exact game row. It does **not** call `Game.delete()`: the permanent
  `catalog_game` trigger forbids physical deletion. The archived UUID-suffixed
  row is inert and not reusable for a future run.
- The package is now a valid ZIP; the test opens downloaded package and
  runtime archives with `zipfile` and checks expected members/content.
- `AdminAuditLog` is append-only by model and PostgreSQL trigger; its delete
  is deliberately not attempted. The audit row created by complaint
  resolution remains as the required append-only audit evidence.

## 4. Quality scope

`Makefile` `lint` now runs:

```text
ruff check apps config tests devcontrol autonomy scripts
ruff format --check apps config tests devcontrol autonomy scripts
```

This matches the GitHub CI quality scope; no AI HQ functionality changed.

## Verification

| Check | Result |
|---|---|
| Targeted heartbeat/session tests | all passed on a fresh test DB after the preflight changes |
| Targeted account/reset tests | all passed on a fresh test DB |
| Ruff check/format (CI scope) | all checks passed; 539 files formatted |
| Mypy | Success: no issues found in 413 source files |
| Django check / migrations | System check clean; No changes detected |
| JS check/tests | 47 passed, 0 failed |
| Full fresh-database pytest | **1395 passed, 18 skipped, 1 warning; 88.29% coverage; 800.89 s; exit 0** |
| Browser E2E | NOT RUN locally: dev-lite web is unhealthy (pre-existing permission error) |

Independent QA (read-only, separate from implementer): **PASS** for the six
follow-up commits plus targeted heartbeat/account evidence. QA did not run
the full suite; the fresh-database result above is main-agent evidence, not
an independent QA result. QA verified the delete trigger is enabled and that
the E2E cleanup never attempts `Game.delete()`.

## QA / Review / CI

Independent code review, delta after the first review's blocker:

- **VERDICT: ACCEPT** for the delta (`5bc8a81` + `636259f`).
- The first review's B1 — forbidden physical `catalog_game` delete — is
  resolved by archiving the exact fixture row, not by bypassing the
  PostgreSQL trigger.
- Re-checked: archive updates only `status`; `current_version=None` releases
  the PROTECT reference before version deletion; user deletion is safe with
  SET_NULL/CASCADE relations; files/users are cleaned before game handling.

Independent QA verdict: **PASS** for the code/delta and targeted tests;
browser E2E/live HTTP were not executed. QA disclosed the residuals below.

GitHub CI / Draft PR: **BLOCKED**. The branch is pushed at `636259f`
(`origin/review/platform-integration-baseline-20261128`), but this shell has
no `gh` and no `GITHUB_TOKEN`/`GH_TOKEN`; no Draft PR can be created and no
GitHub CI result is claimed.

Branch compare:
`https://github.com/ElkinVA/breaktime-arcade/compare/main...review/platform-integration-baseline-20261128`

## Residuals / required disclosures

- `AdminAuditLog` rows cannot be deleted without violating append-only
  invariants.
- `catalog_game` rows cannot be physically deleted by a permanent trigger;
  the E2E fixture archives its exact game row instead of bypassing the
  invariant. A fully row-free E2E would require an owner decision on a
  test-only database/cleanup policy. Archived UUID-suffixed rows accumulate.
- Local browser E2E and live HTTP remain unverified until the dev-lite web
  permission problem is fixed or GitHub CI runs the E2E job.
- The preflight rates (`30/min` subject, `120/min` guest IP) are
  implementation-defined; Appendix E specifies only the normative `3/min`
  per-session heartbeat.
- There is no committed test specifically asserting authenticated-user
  exemption from the guest IP preflight; it was checked manually.
- The expired/foreign `invalid` bucket path is covered implicitly by the
  unknown-UUID test, not by a dedicated expired/foreign test.
- `make fmt` remains narrower than `make lint`; only lint was required to
  match CI.
- The dev DB shows `i18n.0014`/`i18n.0015` unapplied; this is pre-existing
  environment drift, not a code failure (fresh test DB passed all migrations).
- No product acceptance is claimed.
