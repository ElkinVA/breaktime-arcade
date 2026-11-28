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

## Independent review / QA

- Independent reviewer: **ACCEPT**; no blockers.
- Independent QA: **PASS** for targeted/static evidence. QA independently ran
  the three audit tests on a fresh DB, the existing CRM game-card regression
  tests, Ruff, mypy, `manage.py check` and `makemigrations --check`; all
  passed. QA did not claim live browser/HTTP.

- Reviewer minor findings:
  - Paging the audit section and the records section does not preserve the
    other section's page parameter (UX-only).
  - The new test's role-guard check covers anonymous redirect; the endpoint's
    broader role matrix remains covered by the existing records-tab test.
  - Tests construct audit rows directly; the real publish/rollback writers
    were statically verified to emit the same `object_type`/`object_id`
    shape.
- QA residual:
  - No single end-to-end test from real `publish_version`/`rollback_version`
    through the rendered section; writer contract is covered by existing
    tests.
  - The new module's targeted coverage is 78%: deleted-actor, malformed-page
    and unknown-action branches are not directly covered.
  - `crm-audit-*` test IDs are distinct from `crm-record-*`; the global
    journal page uses its own `crm-audit-*` IDs on a different page.
  - Timestamps render in UTC per project settings.

## Residuals

- No product acceptance; this is a technical implementation.
- Branch `feature/ARCADE-CRM-GAME-AUDIT-TAB-001` is pushed through
  `418026a`. A separate PR is not created from this shell because no
  GitHub API credentials are available; use the GitHub PR link after review.
- No remote CI is claimed for this feature branch.
- The task is marked COMPLETED technically in `.autonomy/state.json` with
  candidate `9557520`; timer remains STOPPED and no product acceptance is
  implied.
- Full fresh-DB local run was at `9557520`; the later `418026a` commit is
  docs-only.
