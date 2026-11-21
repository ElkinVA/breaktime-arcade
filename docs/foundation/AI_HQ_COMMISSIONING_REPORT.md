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

A third real product task, `ARCADE-POPULARITY-001` (`f211161`), was proposed by
the Pro Architect and completed automatically: 30-day popularity indicator,
cached read and `sort=popular`. It passed the cycle, but the independent
reviewer flagged a product-behavior divergence: secondary ordering is
`-published_at/-id`, while §2.8 specifies `WR ↓, id ↑`. That needs a product
decision/follow-up; it was not silently changed.

Final repository gate: **729 passed, 11 skipped**; ruff/format/mypy clean.

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
