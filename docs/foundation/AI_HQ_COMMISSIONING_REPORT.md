# AI HQ — commissioning and Browser Arcade handoff

Date: 2026-11-21
Status: **PARTIAL COMMISSIONING** — product cycle verified; VPS/Telegram live
activation blocked by missing access/network, not by code.

## 1. VPS package

- `autonomy/vps/` contains a systemd user unit, non-secret environment
  template, backup/restore instructions and a VPS runbook.
- `systemd-analyze verify autonomy/vps/ba-autonomy-orchestrator.service`
  exits 0.
- **Not installed on Beget.** This environment has no VPS host entry,
  `~/.ssh/config`, server credentials or owner authorization to copy the
  package. No installation was simulated.

Owner action required: provide SSH host/user/key (or deploy access), clone
`~/ba`, place `~/.config/ba/deepseek.env` (0600), then follow
`autonomy/vps/README.md`. Docker is optional; without it QA uses targeted
checks.

## 2. Model routing

The control plane checks `modelUsage`, not role names. Latest real product
cycle evidence:

| Role | Requested model | Actual `modelUsage` | Session |
|---|---|---|---|
| Developer | `deepseek-flash[1m]` | `deepseek-flash[1m]` | `b4c1d5a9-...` |
| QA | `deepseek-flash` | `deepseek-flash` | `85f8a4e5-...` |
| Reviewer | `deepseek-v4-pro` | `deepseek-v4-pro` | `81f6307d-...` |
| Architect | `deepseek-v4-pro` | `deepseek-v4-pro` | previous task cycle, `79aef134-...` |

No fake/substituted Pro calls were accepted: role/model mismatch fails the
runner closed.

## 3. Telegram

`creds/telegram.env` exists with mode 0600 and `Notifier.from_env()` reports
`enabled=True`. A real `notify()` call returned:

```text
status=skipped attempts=2 reason="network error: [Errno 101] Network is unreachable"
```

A direct `https://api.telegram.org/` request timed out. **Delivery is not
confirmed.** Owner action: provide a network path/VPN or HTTP(S) proxy for
WSL2, or run the notifier on the VPS; then re-test once.

## 4. Browser Arcade product cycle

Two bounded real product tasks completed and merged automatically:

- `ARCADE-RATING-DETAIL-001` — public game detail rating summary; `63b6137`.
- `ARCADE-RATING-LIST-001` — compact catalog-card rating summary with a
  single aggregate query; `3c58dcb`.

Full cycle for each: Flash Developer → Flash QA → Pro Reviewer → commit →
merge. The first became `COMPLETED`; the second was claimed and completed
automatically without an owner command.

A third product task, `ARCADE-POPULARITY-001` (`f211161`), added the
30-day popularity indicator/cache and `sort=popular`. Its reviewer flagged the
secondary order; follow-up `ARCADE-POPULARITY-ORDER-001` (`670923f`) then
aligned it exactly to §2.8 (`WR ↓, id ↑`) and passed the full cycle.

`ARCADE-CATALOG-SORTS-001` (`3f5b16a`) added Bayesian WR scoring and
`sort=rating`/`votes`. Its reviewer accepted with minor edge-case debt
(no-aggregate zero-vote ordering, `RATING_WR_M=0`, search+sort test gap).

### Budget policy change (2026-11-21, owner decision)

Token and API-cost limits are **no longer stop conditions**. `BA_MAX_TOKENS`
and `BA_MAX_COST_USD` remain accounting labels only; a task is not returned to
READY because of them. `BA_MAX_TASKS_PER_RUN` and `BA_MAX_RUN_SECONDS` remain
hard execution guards, as do retry limits, fingerprints, run lock and worktree
merge gates. Actual usage is retained in task/run/state records and reported by
`python3 -m autonomy.orchestrator metrics`.

The historical i18n attempt is retained in the audit trail as a budget stop;
the task is resumed under the new policy.

Product queue continued after the policy change: `ARCADE-I18N-UI-001`
(`0c56116`), `ARCADE-HOME-BLOCKS-001` (`f7634b7`), `ARCADE-PROFILE-RECORDS-001`
(`d330ee0`) and `ARCADE-LOCALE-BADGE-001` (`d3aa9f9`) are completed through
Developer self-check → QA → Pro Reviewer → commit/merge. Localization coverage
badge and account profile records are now part of the running product.

The product queue then self-selected and completed `ARCADE-SEO-SITEMAP-001`
(`64f1fd9`): per-language sitemap index and robots.txt for the public portal,
with Pro Reviewer accept.

`ARCADE-CATALOG-PAGINATION-001` (`824eb28`) followed: 24-card pagination with
filter/sort preservation, canonical, noindex beyond page 5, HTMX fragment
navigation and constant query count; Pro Reviewer accept.

The Architect also queued CRM dashboard, leaderboard attempts, SEO meta and
empty-search tasks.

Final repository gate: **776 passed, 11 skipped**; ruff/format/mypy clean.

Current efficiency snapshot: 16 accepted tasks, 12 first-pass (75%), 4
correction cycles, 1 QA failure, 1 review rejection, ~3.79 USD and ~3.78M
tokens per accepted task. These are analytics only; token/cost no longer stop
work.

## 5. AI HQ state

- Architecture is frozen; no new infrastructure tasks are created.
- Architect prompt now prioritizes site, catalog, accounts, CRM and
  game-facing product work; AI HQ changes require a concrete operational
  defect.
- Queue state is durable in `.autonomy/state.json`; completed tasks are not
  re-enqueued; limits are five tasks/run, 3600 seconds, 5M tokens, 5 USD.

## 6. Residual limitations

- R-040: application-level isolation, not an OS sandbox.
- Live Telegram delivery and VPS systemd start were not exercised.
- Worktree QA uses sandbox/targeted checks because `.env` is intentionally
  absent; final repository gate is run on `main`.
- `AUTONOMY-DOCS-SYNC-001` and `AUTONOMY-GUARD-HARDEN-001` remain blocked.

Next: continue product development from the Browser Arcade queue; no
infrastructure work unless a concrete operational defect appears.
