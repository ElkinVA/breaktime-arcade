# BA Autonomous Development Environment — BA-AUTONOMY-003

This directory contains the project-local Claude Code setup for Breaktime
Arcade. It does not change production, the DeepSeek endpoint, or secrets.

## Boundaries

- Work only inside `/home/elkinva/projects/ba` unless a task explicitly
  permits another path. `ai-dev` is a read-only sibling from here.
- Never modify `CLAUDE.md`, `technical_specification/**`, `.env*`, `certs/**`,
  `creds/**`, or user/global Claude configs without explicit approval.
- Never push, publish, deploy, rotate keys, or change the provider endpoint.
- Main agent coordinates; subagents must not edit the same files concurrently.
- If a requirement is ambiguous or a protected file must change, stop and ask.

## Verified DeepSeek models and actual routing

Discovery used the configured provider only; no endpoint or keys were changed.
`GET /models` returned two models and the Anthropic-compatible endpoint
accepted both current flash and v4-pro.

| Model ID | Display name | Context | Max output | Notes |
|---|---|---:|---:|---|
| `deepseek-flash` | DeepSeek-V4.1-Flash | 1,048,576 | 393,216 | tools work |
| `deepseek-v4-pro` | DeepSeek-V4-Pro | 1,048,576 | 393,216 | tool updates are `leading-only`; use text-only |

Current environment (verified in `~/.bashrc`, 2026-11-20):

```text
ANTHROPIC_MODEL=deepseek-flash[1m]
ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-v4-pro
ANTHROPIC_DEFAULT_SONNET_MODEL=deepseek-flash[1m]
ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-flash
CLAUDE_CODE_SUBAGENT_MODEL=deepseek-flash
```

- Main session remains Flash by default.
- `/model opus` selects `deepseek-v4-pro`; `/model sonnet`/`haiku` remain Flash.
- Per-agent frontmatter: `architect`, `code-reviewer`, `security-auditor` —
  v4-pro; `developer`, `qa-engineer` — Flash.

### Pro text-only protocol (mandatory)

Real calls show `message.model=deepseek-v4-pro` in subagent logs, but Pro
tool use is unreliable (`leading-only`): a real architect emitted 11
assistant messages with 0 tool calls and 0 text. Therefore:

1. Flash gathers facts, diff, test results and excerpts.
2. Flash invokes the Pro agent with a compact brief and **"do not use tools;
   answer text-only"**.
3. Pro returns a plan or `VERDICT: accept|reject|incomplete` with findings.
4. Flash implements/fixes and records the actual model used.

Do not hand a Pro agent a tool-heavy task and expect it to read files. Do not
present a Flash plan or self-review as a Pro plan/review.

## Model policy

Use Flash for file reading/search/inventory, routine edits, tests, docs,
reports and verification. Use Pro (text-only) for architecture, cross-module
design, risky changes, independent code review, security review and task
decomposition. Do not use Pro for routine operations. Do not change the
global endpoint, token or model configuration without owner approval.

## Skills

- `ba-plan` — Pro-led written plan before implementation.
- `ba-development` — Pro plan → Flash implementation → Pro review → tests →
  registers update.
- `ba-debugging` — reproduce, isolate, fix, regress; max 2 fix iterations.
- `ba-testing` — test matrix and truthful result capture.
- `ba-code-review` — Flash prepares evidence; Pro `code-reviewer` verdict.
- `ba-project-audit` — read-only project/requirements audit.
- `ba-release` — readiness checks without push/deploy.
- `ba-create-report` — creates one `reports/BA_AUDIT_*.zip` on explicit
  owner command «Создай отчёт».

## Subagents

- `architect` — read-only, v4-pro, text-only plan/architecture.
- `code-reviewer` — v4-pro, text-only independent diff review.
- `security-auditor` — v4-pro, text-only security review.
- `qa-engineer` — Flash, read-only tests/regression.
- `developer` — Flash, implementation only in assigned files.

## Hooks and permissions

- `guard_protected_paths.py` — PreToolUse for Edit/Write/MultiEdit/
  NotebookEdit; blocks protected project/user paths and writes outside the
  project (except `/tmp`); fail-closed.
- `bash_guard.py` — PreToolUse for Bash; blocks `docker compose down -v`,
  volume removal, `git reset --hard`, `git clean`, history rewrite,
  `push --force`, `rm -rf` outside `/tmp`, `DROP DATABASE/TABLE` outside a
  test DB, and write-like commands touching `.env`, `certs`, `creds`, `.git`,
  `technical_specification`, `CLAUDE.md`, user config, or the sibling
  repository. It is defense-in-depth, not a sandbox.
- No duplicate syntax/lint/test hook; pre-commit and CI cover those.
- `ai-dev` has its own `.claude` guard; it blocks writes to `ba`, secrets and
  user config, and allows output only under `~/ai-handoff` and `/tmp`.

## Context recovery

- First read `docs/handoff/NOW.md`, then `PROJECT_STATUS.md` and
  `BACKLOG.md`; full registers only when needed.
- After each package update NOW, six registers and `PROJECT_STATUS.md`;
  record which model planned, implemented and reviewed.
- `CLAUDE.md` is auto-loaded; keep its factual state and pointers current.

## Test environment

Verified 2026-11-20 inside the dev-lite web container:

```text
make test        -> 185 passed, 2 skipped
make lint        -> ruff check passed; 333 files formatted
make types       -> Success: no issues found in 316 source files
./verify_stack.sh -> СТЕК ЗДОРОВ
```

E2E is run from the host `.venv` because the dev container lacks
`libatomic.so.1`; host E2E: 13 passed. The host `.venv` is not the primary
project QA environment; the dev container is.

## Report command

Only on explicit owner request:

```bash
cd /home/elkinva/projects/ba
python3 .claude/skills/ba-create-report/create_report.py --task-id CURRENT
```

The generator creates one archive at `reports/BA_AUDIT_YYYYMMDD_HHMMSS.zip`,
excludes secrets and heavy artifacts, scans for secrets, verifies the ZIP and
MANIFEST, and refuses to overwrite. It does not send the archive anywhere.
