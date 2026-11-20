# BA Autonomous Development Environment — BA-AUTONOMY-001

This directory contains the project-local Claude Code setup for Breaktime
Arcade. It does not change global Claude Code settings or the DeepSeek
endpoint/tokens.

## Boundaries

- Work only inside `/home/elkinva/projects/ba` unless a task explicitly
  permits another path.
- Never modify `CLAUDE.md`, `technical_specification/**`, `docs/spec/**`,
  `.env*`, `certs/**`, `creds/**`, `.git/**`, or user/global Claude configs.
- Never push, publish, deploy, rotate keys, or change the provider endpoint.
- Main agent coordinates; subagents must not edit the same files
  concurrently and must not make critical architecture decisions.
- If a requirement is ambiguous or a protected file must change, stop and
  ask the owner.

## Verified DeepSeek models

Discovery used the configured provider only; no endpoint, keys, or global
settings were changed. `GET /models` returned two models and the
Anthropic-compatible endpoint accepted both current flash and v4-pro.

| Model ID | Display name | Context | Max output | Input | Anthropic messages notes |
|---|---|---:|---:|---|---|
| `deepseek-flash` | DeepSeek-V4.1-Flash | 1,048,576 | 393,216 | text, image | system prompt update: in-history; tool update: addition-only |
| `deepseek-v4-pro` | DeepSeek-V4-Pro | 1,048,576 | 393,216 | text | system prompt update: leading-only; tool update: leading-only |

Both expose effort levels `low`, `high`, `max`; default `high`.
Current environment uses `deepseek-flash[1m]` as the main model.
`CLAUDE_CODE_SUBAGENT_MODEL=deepseek-flash` is the default for subagents, but
per-agent `model:` frontmatter takes precedence: BA-AUTONOMY-002 verified real
calls on `deepseek-flash` (qa-engineer, developer) and `deepseek-v4-pro`
(architect, code-reviewer, security-auditor). The `[1m]` suffix is a Claude
Code-side alias; `/models` lists the provider ID `deepseek-flash`.

## Model policy

Default to `deepseek-flash[1m]` for:

- file reading, search, inventory and routine inspection;
- simple edits and mechanical refactors;
- docs, tests and routine verification.

Use `deepseek-v4-pro` for:

- architecture and cross-module design analysis;
- difficult debugging and large, risky changes;
- independent code review and security review.

Because v4-pro reports `leading-only` system/tool updates, prefer a **fresh
focused session or subagent** for v4-pro rather than switching mid-session in
a tool-heavy conversation. If v4-pro fails, is unavailable, or rejects a
tool update, fall back to flash and record the fact; do not change global
environment variables or the endpoint.

Manual switching (no global config changes):

```text
/model deepseek-v4-pro
/model deepseek-flash[1m]
```

Subagent frontmatter requests the model per role. If the global
`CLAUDE_CODE_SUBAGENT_MODEL` or a future provider policy overrides it, use a
fresh session with an explicit `/model` and record the actual behavior.

## Skills

- `ba-project-audit` — read-only project/requirements audit.
- `ba-development` — autonomous feature cycle with tests and review.
- `ba-debugging` — reproduce, isolate, fix, regress.
- `ba-testing` — test matrix and truthful result capture.
- `ba-code-review` — independent diff review.
- `ba-release` — readiness checks without push/deploy.
- `ba-create-report` — creates the single `reports/BA_AUDIT_*.zip` on the
  explicit owner command «Создай отчёт».

## Subagents

- `architect` — read-only architecture/requirements analysis; v4-pro.
- `code-reviewer` — read-only independent diff review; v4-pro.
- `qa-engineer` — read-only testing/regression analysis; flash.
- `security-auditor` — read-only security review; v4-pro.
- `developer` — implementation only in assigned files; flash; no
  architecture decisions, no concurrent edits.

## Hooks

One project hook is enabled: a `PreToolUse` guard for `Edit`, `Write`,
`MultiEdit` and `NotebookEdit` that blocks writes to protected project and
user paths. It does not delete, rewrite, publish, or format user data.
It covers file-editing tools, not arbitrary `Bash` commands; the agent must
still obey the boundaries for shell operations. The hook is fail-closed
(`onFailure: block`): if the guard itself breaks, edits remain blocked until
the owner or a shell-level repair fixes it.

Existing project checks cover the rest:

- `.pre-commit-config.yaml`: EOF/trailing whitespace, YAML/JSON, merge
  conflict, large files, private key detection, ruff;
- `.github/workflows/ci.yml`: ruff, mypy, pytest with PostgreSQL/Redis;
- `make test`, `make lint`, `make types`, `./verify_stack.sh`.

No duplicate syntax/lint/test hook was added because it would be slow or
fragile in the current container.

## Test environment

BA-AUTONOMY-002 removed the former QA blocker. The Dockerfile installs the
`dev` dependency group only when `INSTALL_DEV=true`; only
`compose.dev-lite.yml` sets that build arg (web, worker, beat, backup,
restore-check). Staging and production builds keep `--no-dev`.

Verified on 2026-11-18 inside the dev-lite web container:

```text
make test        -> 11 passed
make lint        -> ruff check: All checks passed; format: 302 files formatted
make types       -> Success: no issues found in 297 source files
./verify_stack.sh -> СТЕК ЗДОРОВ
```

The host `.venv` is not used for project QA. The codebase was reformatted
once with the locked ruff 0.17.5 to restore a clean `ruff format --check`
baseline. Custom `CitextField`/`UUID7` typing is declared in
`apps/core/fields.pyi`; runtime code does not depend on django-stubs.

## Report command

Only on explicit owner request:

```bash
cd /home/elkinva/projects/ba
python3 .claude/skills/ba-create-report/create_report.py --task-id BA-AUTONOMY-001
```

The generator creates one archive at
`reports/BA_AUDIT_YYYYMMDD_HHMMSS.zip`, excludes secrets and heavy
artifacts, scans for secrets, verifies the ZIP and MANIFEST, and refuses to
overwrite an existing archive. It does not send the archive anywhere.
