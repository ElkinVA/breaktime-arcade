# AI autonomy — технические доказательства (2026-11-21)

## Model routing (actual, not role names)

Environment: `ANTHROPIC_MODEL=deepseek-flash[1m]`,
`ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-v4-pro`,
`CLAUDE_CODE_SUBAGENT_MODEL=deepseek-flash`; endpoint
`https://api.deepseek.com/anthropic`.

Transcript audit of `/home/elkinva/.claude/projects/-home-elkinva-projects-ba/`:

- main session: 3 931 assistant calls, all `deepseek-flash`;
- 20 Pro subagent transcripts: `message.model=deepseek-v4-pro`, real
  Read/SubagentHandback calls; one Flash built-in `claude-code-guide`;
- CLI Pro probe: 3 turns, 2 files read, `modelUsage.deepseek-v4-pro`
  (input 15 243 / output 2 243), no permission denials.

The control plane checks `modelUsage` on every call; role/model mismatch is
failed closed.

## Real task cycle

Command: `python3 -m autonomy.orchestrator run --max-tasks 2 --no-propose`

Queue source: Pro Architect (`autonomy-architect`,
session `79aef134-e1a8-42a0-9ec9-ac8d292ac2bc`) returned 4 concrete
`AUTONOMY-*` tasks. Its evidence has
`modelUsage.deepseek-v4-pro` input 87 927 / output 16 459.

### Task `AUTONOMY-GUARD-TESTS-001`

- Flash Developer session `d149cd69-...` / `12cb4074-...`:
  `modelUsage.deepseek-flash[1m]`; added `tests/unit/test_hooks_guard.py`.
- Flash QA session `5e34badd-...`: `modelUsage.deepseek-flash`;
  `make test`/`make check` = **657 passed, 4 skipped** at that commit
  (193 guard tests).
- Commit: `24cd6fd autonomy(AUTONOMY-GUARD-TESTS-001): ...`.

### Task `AUTONOMY-CONFIG-CONTRACT-001`

- Developer Flash added the two contract test modules and the devcontrol
  deny/sandbox wiring; QA `make check` = 670 passed, 4 skipped.
- Pro Reviewer `42f4c0f6-...` accepted; commit `c184ffa`.
- Auto-next was already observed after the preceding completed task.
- First Pro Reviewer (`b56e4714-...`) correctly rejected the uncommitted
  deliverable. Second Pro Reviewer (`36f8fac4-...`,
  `modelUsage.deepseek-v4-pro`, output 18 605) reviewed the committed diff
  and accepted with two minor residuals.
- State: `COMPLETED`, attempts 2.

### Automatic next task

After the completed task, the same orchestrator claimed
`AUTONOMY-CONFIG-CONTRACT-001` (status `RUNNING`, attempt 1) without a new
owner command. The protected-hook hardening task is `BLOCKED` with reason
`OWNER_APPROVAL_REQUIRED`.

## Queue/state properties

`autonomy/state.py` + `.autonomy/state.json` (local, ignored):

- frozen status set `READY/RUNNING/QA/REVIEW/COMPLETED/BLOCKED/FAILED`;
- `fcntl` lock, atomic `os.replace`, single `run.lock`;
- attempts (max 2), dependencies, BLOCKED reason;
- completed IDs and title/acceptance fingerprints are never re-enqueued;
- recovery of RUNNING/QA/REVIEW after a killed orchestrator;
- stop file `.autonomy/STOP`.

Unit coverage: `tests/unit/test_autonomy.py` (12 tests) covers dedup,
dependencies, recovery, retry→BLOCKED, COMPLETED non-requeue, architect
filter, JSON parsing/model checks.

## Verification

```text
make check                    -> 670 passed, 4 skipped
tests/unit/test_autonomy.py   -> 12 passed
tests/unit/test_hooks_guard.py-> 193 passed
ruff/format/mypy              -> clean
```

Commits: `24cd6fd` (task output), `32bc351` (control plane), `e190436` (review-gate/state fixes). `main` pushed.
No game/App F feature changes were made in this block.

### Independent control-plane review

- First Pro review (`4f7af416...`) **rejected** the original
  commit-before-review gate and weak model/staging checks.
- Fix `e190436` changed the flow to safe-path staging → Pro review of the
  staged candidate → commit only on accept / unstage on reject; corrupt state
  fail-closed; strict requested-model token check; recovery locked.
- Second Pro review (`172ca08a-e7cb-4a5f-97ea-4582f92ea7eb`,
  `modelUsage.deepseek-v4-pro`, output 33 689) **accepted** with minor
  residuals. Commit-path tests were then added (13 autonomy tests).

## Remaining risks

- Review gate is now: stage only reported safe paths → Pro review → commit
  on accept / unstage on reject. No isolated worktree/branch; a failed
  staging operation leaves worktree changes.
- Pro reviewer does not independently re-run the full suite; QA evidence is
  supplied.
- `AUTONOMY-CONFIG-CONTRACT-001` was interrupted during the control-plane
  review fix and rerun; its final verdict is separate.
- The autonomous developer still has normal user-level process permissions;
  the existing hooks are defense-in-depth, not an OS sandbox.
- `.autonomy` state/evidence are local and not backed up/committed by design.
