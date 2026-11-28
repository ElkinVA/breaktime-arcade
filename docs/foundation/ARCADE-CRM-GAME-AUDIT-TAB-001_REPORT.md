# ARCADE-CRM-GAME-AUDIT-TAB-001 — report

## Task

Add a read-only per-game change-history section to the CRM game card.

- Task status before implementation: READY in `.autonomy/state.json`.
- Selection rationale: staff/owner release-readiness visibility; acceptance
  criteria fully specified; no schema, writes, protected paths or owner gate;
  testable without the unhealthy dev-lite web UI.
- Branch: `feature/ARCADE-CRM-GAME-AUDIT-TAB-001`, based on local `main`
  `b035720`.
- Implementation commit: `9557520`.

## Implementation

- `apps/crm/services/game_audit.py` — bounded `AdminAuditLog` projection:
  `object_type="game"`, `object_id=game.id`, newest first
  (`-created_at`, `-id`), 25 rows/page, `select_related("actor")`.
- `apps/crm/views.py` — game detail loads `audit_page` separately from the
  records `page` parameter; role guard remains `@role_required(GAMES_VIEW)`.
- `apps/crm/templates/crm/games/detail.html` — new read-only section.
- `apps/crm/templates/crm/games/audit.html` — rendered action, actor and
  date; explicit empty state; pagination with `audit_page`.
- `tests/integration/test_crm_game_audit.py` — filtering, other-game
  exclusion, newest-first order, rendered date, empty state, role gate and
  pagination.

No schema change, no migration, no new write path, no public-page change.

## Verification

| Check | Result |
|---|---|
| Targeted CRM game card tests | 18 passed |
| Full fresh-DB pytest | **1390 passed, 18 skipped, 1 warning; 88.25% coverage; 823.41 s; exit 0** |
| Ruff | pass, 523 files formatted |
| Mypy | pass, 414 source files |
| makemigrations check | no changes detected |
| JS | not affected |
| Live browser | not run locally; dev-lite web unhealthy |

## Independent review / QA / CI

- **ChatGPT independent code review: ACCEPT** directly through GitHub at
  feature HEAD `d02a040`; no blocking defects. ChatGPT verified the
  `AdminAuditLog` filters, `select_related("actor")`, append-only invariant
  and the real publish/rollback audit shapes.
- **Independent QA: PASS** for targeted/static evidence; QA independently
  ran the audit tests on a fresh DB, the existing CRM regression tests,
  Ruff, mypy, `manage.py check` and `makemigrations --check`.
- **Local full fresh-DB gate: PASS** on `9557520`: **1390 passed, 18
  skipped, 1 warning; 88.25% coverage; exit 0**.
- **GitHub CI: PENDING**. No feature PR exists yet (no GitHub API
  credentials in this shell); no CI result is claimed.
- **Product acceptance: PENDING**.
- ChatGPT non-blocking notes: cross-pagination position is not preserved
  between records/audit; no single end-to-end publish/rollback render test;
  deleted-actor, malformed-page and unknown-action branches are not directly
  covered.

## Git base warning and safe PR scenario

The feature branch is based on local `main` `b035720`, while the baseline
review branch contains 15 additional commits. A normal PR directly into
`main` today would show 12 commits / 34 files, including unrelated unmerged
baseline and product work. **Do not create that mixed PR.**

Safe path after the owner integrates PR #1:

1. Update local `main` from `origin` after the owner-authorized integration.
2. Create a **new** branch from the updated `main`.
3. Cherry-pick the three task commits in order:
   `9557520`, `418026a`, `d02a040`.
4. Verify `git diff --name-only updated-main...new-branch` contains only the
   CRM audit task files.
5. Push the new branch and create a separate PR; wait for all GitHub CI jobs.
6. Do not rebase or force-push the existing feature branch.

If immediate review is explicitly needed, a stacked Draft PR with base
`review/platform-integration-baseline-20261128` is allowed; it must be
labelled as dependent on PR #1 and must not be merged.

## Residuals

- No product acceptance; this is a technical implementation.
- Branch `feature/ARCADE-CRM-GAME-AUDIT-TAB-001` is pushed through
  `d02a040`. A separate PR is not created from this shell because no
  GitHub API credentials are available; use the GitHub PR link after review.
- No remote CI is claimed for this feature branch.
- The task is marked COMPLETED technically in `.autonomy/state.json` with
  candidate `9557520`; timer remains STOPPED and no product acceptance is
  implied.
- Full fresh-DB local run was at `9557520`; later `418026a` and `d02a040`
  commits are documentation-only.
- No rebase, force-push, reset, clean, merge or protected-path bypass was
  performed.
