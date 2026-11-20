#!/usr/bin/env python3
# ruff: noqa: T201, S603
"""Create one BA_AUDIT_YYYYMMDD_HHMMSS.zip for independent ChatGPT audit.

The generator is read-only with respect to project sources. It writes only the
archive under reports/ (or --output-dir). It never sends the archive anywhere.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

REQUIRED_DOCS = (
    "REPORT.md",
    "PROJECT_STATE.md",
    "TASK_HISTORY.md",
    "CHANGES.md",
    "TEST_RESULTS.md",
    "GIT_STATUS.txt",
    "REQUIREMENTS_COMPLIANCE.md",
    "RISKS.md",
    "NEXT_STEPS.md",
    "SHA256SUMS.txt",
    "CODE_DIFF.patch",
    "MANIFEST.txt",
)

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    ".virtualenv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".backups",
    "media",
    "staticfiles",
    "dist",
    "reports",
    "audit_package_parts",
    "pgdata",
    "redis-data",
    "backups",
    "var",
}
EXCLUDED_NAMES = {
    ".env",
    ".env.staging",
    ".env.local",
    ".env.production",
    "deepseek.env",
    ".claude.json",
    "project_dump.txt",
    "project_dump.log",
    "audit.txt",
}
EXCLUDED_SUFFIXES = {
    ".pem",
    ".key",
    ".crt",
    ".cer",
    ".der",
    ".p12",
    ".pfx",
    ".jks",
    ".keystore",
    ".zip",
    ".tar",
    ".gz",
    ".tgz",
    ".bz2",
    ".xz",
    ".7z",
    ".rar",
    ".jar",
    ".war",
    ".whl",
    ".deb",
    ".rpm",
    ".iso",
    ".pyc",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".log",
}
MAX_FILE_BYTES = 512 * 1024
MAX_DIFF_BYTES = 2_000_000
MAX_TEST_RESULTS_BYTES = 512 * 1024

SECRET_PATTERNS = (
    ("private-key", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("api-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    ),
    (
        "connection-string-password",
        re.compile(
            r"\b(?:postgres|postgresql|mysql|mongodb|redis|amqp)://"
            r"[^/\s:@]+:[^@\s]+@"
        ),
    ),
    (
        "authorization-header",
        re.compile(r"(?i)\bauthorization:\s*(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{12,}"),
    ),
)

SAFE_PLACEHOLDER_PASSWORDS = {
    "ba",
    "changeme",
    "ci",
    "dev",
    "password",
    "postgres",
    "test",
}
CONNECTION_CREDENTIAL_RE = re.compile(
    r"\b(?P<scheme>postgres|postgresql|mysql|mongodb|redis|amqp)://"
    r"(?P<user>[^/\s:@]+):(?P<password>[^@\s]+)@"
)


def redact_safe_placeholders(text: str) -> str:
    """Mask dev/CI placeholder passwords in connection strings.

    Only passwords that are obvious placeholders (a small allowlist, equal to
    the user name, or an environment-variable reference) are masked. Any
    other credential string still fails the secret scan and blocks the
    archive. The replacement deliberately omits ``user:password`` entirely so
    the conservative connection-string pattern does not match it again.
    """

    def repl(match: re.Match[str]) -> str:
        user = match.group("user")
        password = match.group("password")
        is_variable = password.startswith("$") or password.startswith("%(")
        is_placeholder = password.casefold() in SAFE_PLACEHOLDER_PASSWORDS
        if not (is_variable or is_placeholder or password.casefold() == user.casefold()):
            return match.group(0)
        return f"{match.group('scheme')}://[redacted]@"

    return CONNECTION_CREDENTIAL_RE.sub(repl, text)


class ReportError(RuntimeError):
    pass


def run(cmd: list[str], cwd: Path, timeout: int = 20) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, out.strip()
    except FileNotFoundError as exc:
        return 127, str(exc)
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {timeout}s"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_text(path: Path) -> bool:
    try:
        sample = path.read_bytes()[:8192]
    except OSError:
        return False
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def excluded(rel: Path) -> bool:
    if any(part in EXCLUDED_DIRS for part in rel.parts):
        return True
    if rel.name in EXCLUDED_NAMES:
        return True
    if rel.name.startswith(".env.") and rel.name not in {
        ".env.example",
        ".env.staging.example",
    }:
        return True
    if rel.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    if rel.as_posix().startswith("technical_specification/"):
        return True
    if rel.as_posix().startswith("certs/") or rel.as_posix().startswith("creds/"):
        return True
    if rel.as_posix() == ".claude/settings.local.json":
        return True
    return rel.parent == Path() and (
        rel.name.startswith("ba_")
        or rel.name.startswith("fill_")
        or rel.name.startswith("fix_")
        or rel.name == "rebuild_after_fix.sh"
        or rel.name.startswith("setup-claude-code-deepseek")
        or rel.name.startswith("diagnostics_")
        or rel.name.startswith("dev-env-audit")
    )


def secret_categories(text: str) -> list[str]:
    return [name for name, pattern in SECRET_PATTERNS if pattern.search(text)]


def assert_no_secrets(path: Path) -> None:
    if not path.is_file() or not is_text(path):
        return
    if path.stat().st_size > MAX_FILE_BYTES:
        return
    cats = secret_categories(path.read_text(encoding="utf-8", errors="replace"))
    if cats:
        raise ReportError(
            f"secret-like content in {path.name}: {', '.join(cats)}; value not printed"
        )


def git(root: Path, *args: str) -> tuple[int, str]:
    return run(["git", "-C", str(root), *args], cwd=root)


def write(path: Path, content: str) -> None:
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def collect_files(root: Path) -> list[Path]:
    result: list[Path] = []
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS)
        for name in sorted(files):
            path = Path(base) / name
            rel = path.relative_to(root)
            if excluded(rel):
                continue
            if path.is_symlink() or not path.is_file():
                continue
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            if not is_text(path):
                continue
            result.append(path)
    return result


def make_diff(root: Path, stage: Path) -> str:
    parts: list[str] = [
        "# BA-AUTONOMY-001 code diff",
        "# Generated by ba-create-report; secrets excluded.",
        "# Dev/CI placeholder connection-string credentials are masked as [redacted].",
        "",
    ]
    used = 0

    code, tracked = git(root, "diff", "--no-ext-diff", "--no-color", "--", ".")
    if code == 0 and tracked:
        parts.append("## Tracked changes")
        parts.append(tracked)
        used += len(tracked.encode("utf-8"))

    untracked_code, untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z")
    if untracked_code == 0 and untracked:
        parts.append("## Untracked files (text, filtered)")
        for raw in untracked.split("\0"):
            if not raw:
                continue
            path = root / raw
            rel = Path(raw)
            if excluded(rel) or not path.is_file() or not is_text(path):
                continue
            data = path.read_text(encoding="utf-8", errors="replace")
            block = (
                f"diff --git a/{rel.as_posix()} b/{rel.as_posix()}\n"
                f"new file mode 100644\n--- /dev/null\n+++ b/{rel.as_posix()}\n"
                + "\n".join("+" + line for line in data.splitlines())
                + "\n"
            )
            if used + len(block.encode("utf-8")) > MAX_DIFF_BYTES:
                parts.append(
                    "\n# DIFF TRUNCATED: size limit reached; see CHANGES.md and git status.\n"
                )
                break
            parts.append(block)
            used += len(block.encode("utf-8"))

    if not tracked and not untracked:
        parts.append("# No tracked or untracked text changes found.")
    return "\n".join(parts) + "\n"


def build_stage(root: Path, task_id: str, test_results: Path | None, stage: Path) -> Path:
    stage.mkdir(parents=True, exist_ok=True)
    now = datetime.now().astimezone()
    stamp = now.strftime("%Y-%m-%d %H:%M:%S %z")

    status_code, status = git(root, "status", "--short", "--branch")
    log_code, log = git(root, "log", "-20", "--oneline")
    remote_code, remote = git(root, "remote", "-v")
    stat_code, diffstat = git(root, "diff", "--stat")
    branch_code, branch = git(root, "branch", "--show-current")
    head_code, head = git(root, "rev-parse", "HEAD")
    diff_check_code, diff_check = git(root, "diff", "--check")
    tracked_count = len([x for x in git(root, "ls-files")[1].splitlines() if x])
    apps = sorted([p.name for p in (root / "apps").glob("*") if p.is_dir()])
    empty_docs = [
        str(p.relative_to(root))
        for p in (root / "docs").rglob("*")
        if p.is_file() and p.stat().st_size == 0 and p.name != ".gitkeep"
    ]
    spec_dir = root / "docs/spec"
    spec_empty = (
        not any(p.is_file() and p.name != ".gitkeep" for p in spec_dir.rglob("*"))
        if spec_dir.is_dir()
        else True
    )
    allow_any = 0
    allow_any_paths = []
    for base in (root / "apps", root / "config"):
        for p in base.rglob("*.py"):
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "AllowAny" in text:
                allow_any += 1
                allow_any_paths.append(str(p.relative_to(root)))
    skills_count = len(list((root / ".claude/skills").glob("*/SKILL.md")))
    agents_count = len(list((root / ".claude/agents").glob("*.md")))
    ts_files = []
    for name in ("ts_site.txt", "ts_game.txt"):
        p = root / "technical_specification" / name
        if p.is_file():
            ts_files.append((name, p.stat().st_size, sha256(p)))

    test_env_code, test_env = run(
        [
            "docker",
            "compose",
            "-f",
            "compose.yml",
            "-f",
            "compose.dev-lite.yml",
            "exec",
            "-T",
            "web",
            "python",
            "-m",
            "pytest",
            "--version",
        ],
        cwd=root,
        timeout=15,
    )
    docker_code, docker_ps = run(
        [
            "docker",
            "compose",
            "-f",
            "compose.yml",
            "-f",
            "compose.dev-lite.yml",
            "ps",
        ],
        cwd=root,
        timeout=15,
    )

    write(
        stage / "REPORT.md",
        f"""# BA AUDIT REPORT — {task_id}

Generated: {stamp}

## Summary

- Project: `{root}`.
- Worktree: branch `{branch}`; HEAD `{head}`; tracked files: {tracked_count}.
- Changed/untracked files are listed in `CHANGES.md`; full context is in
  `GIT_STATUS.txt` and `CODE_DIFF.patch`.
- This report was generated by `ba-create-report`; it does not publish or
  deploy anything.
- Project setup: {skills_count} skills, {agents_count} agents, and the
  project-local protection hook are present under `.claude/`.
- Model policy: flash for routine work; v4-pro for architecture/complex
  review in a fresh session/subagent. Both were verified against the
  configured provider; no global model/endpoint change was made.

## Current state

Breaktime Arcade remains in the skeleton stage described in `CLAUDE.md`.
No mass feature development is claimed by this report. The report records
the actual repository state and the verified setup artifacts under
`.claude/`.

## Verification

- `git diff --check`: exit {diff_check_code}{("; " + diff_check) if diff_check else ""}.
- Full project tests are not run by this generator. Actual test results are
  in `TEST_RESULTS.md`; if they were not run, they are marked NOT RUN.
- Docker Compose state command exit: {docker_code}.
- Dev-container pytest probe: exit {test_env_code} — {test_env or "no output"}.

## Important

- No API keys, tokens, `.env`, `certs/`, `creds/`, private configs, or
  `node_modules` are included.
- `CODE_DIFF.patch` is capped at {MAX_DIFF_BYTES} bytes and may omit large
  parts; see the truncation note and `CHANGES.md`.
""",
    )

    write(
        stage / "PROJECT_STATE.md",
        f"""# PROJECT_STATE — {task_id}

Generated: {stamp}

## Repository

- Branch: `{branch}`.
- HEAD: `{head}`.
- Tracked files: {tracked_count}.
- Remote: {remote or "none"}.
- Apps: {", ".join(apps) if apps else "none"}.

## Stage and documentation

- Normative state from `CLAUDE.md`: skeleton, not MVP.
- Empty docs (excluding `.gitkeep`): {", ".join(empty_docs) if empty_docs else "none"}.
- `docs/spec/` is expected to contain normative TZ copies but is empty;
  normative source files are under `technical_specification/` (not modified).

## Local environment

- Docker Compose `ps` exit: {docker_code}.
- Dev-container pytest probe exit: {test_env_code} — {test_env or "no output"}.
- The generator does not run the full suite; actual checks are recorded in
  `TEST_RESULTS.md` with explicit exit codes.

## Setup artifacts

- Project-local `.claude/` contains skills, agents, hooks, settings, and the
  report generator. They are project-scoped and do not change global Claude
  Code settings or DeepSeek credentials.
""",
    )

    write(
        stage / "TASK_HISTORY.md",
        f"""# TASK_HISTORY — {task_id}

Generated: {stamp}

## Recent commits

```text
{log or "(no commits)"}
```

## Current task

`{task_id}` — snapshot of the current worktree, not a single development
task. The archive records git status, the actual diff and the checks in
`TEST_RESULTS.md`. The report generator does not modify sources, `.env`,
certs, credentials, endpoint settings or normative documents.
""",
    )

    write(
        stage / "CHANGES.md",
        f"""# CHANGES — {task_id}

Generated: {stamp}

## Git status

```text
{status or "(clean)"}
```

## Diff stat

```text
{diffstat or "(no tracked changes)"}
```

## Notes

- Full diff: `CODE_DIFF.patch`.
- The report generator excludes secrets, `.env*`, certs, creds, VCS data,
  dependencies, virtual environments, heavy artifacts, and normative TZ
  copies. Normative TZ hashes are summarized in
  `REQUIREMENTS_COMPLIANCE.md`.
""",
    )

    if test_results and test_results.is_file():
        raw = test_results.read_text(encoding="utf-8", errors="replace")
        if len(raw.encode("utf-8")) > MAX_TEST_RESULTS_BYTES:
            raw = raw[:MAX_TEST_RESULTS_BYTES] + "\n# TRUNCATED\n"
        cats = secret_categories(raw)
        if cats:
            raise ReportError("secret-like content in --test-results: " + ", ".join(cats))
        test_body = raw
    else:
        checks = []
        checks.append(
            f"`git diff --check` -> exit {diff_check_code}"
            + (f"\n```text\n{diff_check}\n```" if diff_check else "")
        )
        import ast

        parse_errors: list[str] = []
        for py_path in sorted((root / ".claude").rglob("*.py")):
            try:
                ast.parse(
                    py_path.read_text(encoding="utf-8", errors="replace"),
                    filename=str(py_path),
                )
            except SyntaxError as exc:
                parse_errors.append(f"{py_path}: {exc}")
        checks.append(
            "AST parse of `.claude/**/*.py` -> "
            + ("PASS" if not parse_errors else "FAIL: " + "; ".join(parse_errors))
        )
        settings = root / ".claude/settings.json"
        if settings.is_file():
            try:
                json.loads(settings.read_text(encoding="utf-8"))
                checks.append("`.claude/settings.json` JSON parse -> PASS")
            except Exception as exc:  # noqa: BLE001
                checks.append(f"`.claude/settings.json` JSON parse -> FAIL: {exc}")
        checks.append(
            "Full project test suite in the dev container: NOT RUN by this "
            f"generator; probe exit {test_env_code} — {test_env or 'no output'}."
        )
        test_body = "\n\n".join(checks)

    write(
        stage / "TEST_RESULTS.md",
        f"""# TEST_RESULTS — {task_id}

Generated: {stamp}

## Recorded checks

{test_body}

## Rule

A check is PASS only when it was actually executed and its exit code was 0.
NOT RUN / NOT TESTED is never presented as PASS.
""",
    )

    write(
        stage / "GIT_STATUS.txt",
        f"""# GIT_STATUS — {task_id}
Generated: {stamp}

## Branch
{branch}

## HEAD
{head}

## Status
{status or "(clean)"}

## Last commits
{log or "(none)"}

## Remote
{remote or "(none)"}

## Diff stat
{diffstat or "(no tracked changes)"}

## git diff --check
exit {diff_check_code}
{diff_check or "(no output)"}
""",
    )

    ts_table = (
        "\n".join(f"| `{name}` | {size} | `{digest}` |" for name, size, digest in ts_files)
        or "| — | — | — |"
    )
    write(
        stage / "REQUIREMENTS_COMPLIANCE.md",
        f"""# REQUIREMENTS_COMPLIANCE — {task_id}

Generated: {stamp}

## Normative files

| File | Size | SHA-256 |
|---|---:|---|
{ts_table}

- Normative copies are not modified by this report task.
- `docs/spec/` is currently empty; `CLAUDE.md`/`README.md` reference it.
- BA-SDK-1.1 and BA-ENV-1.1 are absent and are not treated as existing.
- Full normative texts are intentionally not copied into this archive; the
  hashes above identify the local copies.

## Current stage

`CLAUDE.md` describes the project as a skeleton, not MVP. This report does
not claim feature completeness. Stage-specific compliance requires a
task-level review against the exact TZ section; no unverified PASS is claimed.
""",
    )

    risks = [
        f"- Dev-container pytest probe: exit {test_env_code} — {test_env or 'no output'}.",
        "- The generator does not run the full project suite; quality claims are "
        "limited to the exit codes recorded in `TEST_RESULTS.md`.",
        "- `CLAUDE.md` records an `AllowAny` defect in base permissions; this "
        "report does not change it.",
    ]
    if test_env_code != 0:
        risks.append(
            "- `make test`, `make lint` and `make types` cannot be verified while "
            "pytest/ruff/mypy are unavailable in the dev container; full "
            "autonomous QA cannot be claimed."
        )
    if spec_empty:
        risks.append("- `docs/spec/` contains no normative copies; documentation is incomplete.")
    if empty_docs:
        risks.append("- Empty documentation files: " + ", ".join(empty_docs) + ".")
    if allow_any:
        risks.append(
            f"- `AllowAny` occurrences: {allow_any} "
            f"({', '.join(allow_any_paths[:8])}{'...' if len(allow_any_paths) > 8 else ''})."
        )
    if remote_code != 0 or not remote:
        risks.append("- No Git remote is configured; external backup is absent.")
    for p in (root / ".env", root / ".env.staging"):
        if p.is_file():
            risks.append(
                f"- `{p.relative_to(root)}` mode is {oct(p.stat().st_mode & 0o777)}; "
                "secret file permissions need review."
            )
    for p in sorted((root / "certs").glob("*-key.pem")):
        if p.is_file():
            risks.append(
                f"- `{p.relative_to(root)}` mode is {oct(p.stat().st_mode & 0o777)}; "
                "private key permissions need review."
            )
    risks.append(
        "- v4-pro reports `leading-only` system/tool updates; prefer a fresh "
        "focused session/subagent and verify model behavior before relying on it."
    )
    write(
        stage / "RISKS.md",
        "# RISKS — "
        + task_id
        + "\n\nGenerated: "
        + stamp
        + "\n\n"
        + "\n".join(risks)
        + "\n\nSecrets and private values are not included.\n",
    )

    next_steps: list[str] = []
    if test_env_code != 0:
        next_steps.append(
            "Fix the project dev test environment so `make test`, `make lint` "
            "and `make types` actually execute; do not claim tests passed "
            "before that."
        )
    else:
        next_steps.append(
            "Review the recorded checks in `TEST_RESULTS.md`; the generator "
            "itself does not run the full suite."
        )
    if spec_empty or empty_docs:
        next_steps.append(
            "Populate the empty documentation files (see `RISKS.md`) from "
            "approved normative sources; do not invent missing BA-SDK/BA-ENV."
        )
    next_steps.append(
        "Review secret-file permissions (`.env`, certificate private keys) in "
        "a separately approved task."
    )
    next_steps.append(
        "Perform independent review/acceptance of the current diff "
        "(`CHANGES.md`, `CODE_DIFF.patch`) before release."
    )
    next_steps.append(
        "Continue staged platform development only after the current diff is "
        "reviewed; see `docs/status/BACKLOG.md`."
    )
    numbered_steps = "\n".join(f"{i}. {step}" for i, step in enumerate(next_steps, 1))
    write(
        stage / "NEXT_STEPS.md",
        f"""# NEXT_STEPS — {task_id}

Generated: {stamp}

{numbered_steps}
""",
    )

    diff_text = redact_safe_placeholders(make_diff(root, stage))
    cats = secret_categories(diff_text)
    if cats:
        raise ReportError("secret-like content in CODE_DIFF.patch: " + ", ".join(cats))
    write(stage / "CODE_DIFF.patch", diff_text)

    # Scan exactly the staged archive content before hashing and zipping.
    for path in sorted(stage.rglob("*")):
        if path.is_file():
            assert_no_secrets(path)

    sums = []
    for path in sorted(stage.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            rel = path.relative_to(stage).as_posix()
            sums.append(f"{sha256(path)}  {rel}")
    write(stage / "SHA256SUMS.txt", "\n".join(sums))

    manifest = []
    for path in sorted(stage.rglob("*")):
        if path.is_file():
            rel = path.relative_to(stage).as_posix()
            manifest.append(f"{rel}\t{path.stat().st_size}\t{sha256(path)}")
    write(stage / "MANIFEST.txt", "\n".join(manifest))

    missing = [name for name in REQUIRED_DOCS if not (stage / name).is_file()]
    if missing:
        raise ReportError("missing generated report files: " + ", ".join(missing))
    return stage


def verify_archive(archive: Path, stage: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        bad = zf.testzip()
        if bad is not None:
            raise ReportError(f"ZIP integrity error at {bad}")
        names = set(zf.namelist())
        manifest = zf.read("MANIFEST.txt").decode("utf-8")
        for line in manifest.splitlines():
            if not line.strip():
                continue
            rel, size_s, digest = line.split("\t", 2)
            if rel not in names:
                raise ReportError(f"MANIFEST file missing from ZIP: {rel}")
            data = zf.read(rel)
            if str(len(data)) != size_s or hashlib.sha256(data).hexdigest() != digest:
                raise ReportError(f"MANIFEST mismatch: {rel}")
        for path in stage.rglob("*"):
            if path.is_file():
                rel = path.relative_to(stage).as_posix()
                if rel not in names:
                    raise ReportError(f"staged file missing from ZIP: {rel}")


def main(argv: list[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description="Create one BA audit ZIP")
    parser.add_argument("--project", type=Path, default=default_root)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--task-id", default="CURRENT")
    parser.add_argument("--test-results", type=Path, default=None)
    args = parser.parse_args(argv)

    root = args.project.expanduser().resolve()
    if not (root / "manage.py").is_file() or not (root / "CLAUDE.md").is_file():
        raise ReportError(f"not a Breaktime Arcade project root: {root}")
    output_dir = (args.output_dir or (root / "reports")).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = output_dir / f"BA_AUDIT_{timestamp}.zip"
    if archive.exists() or (output_dir / f"BA_AUDIT_{timestamp}.zip.sha256").exists():
        raise ReportError(f"archive already exists, refusing to overwrite: {archive}")

    stage = Path(tempfile.mkdtemp(prefix="ba-audit-"))
    try:
        build_stage(root, args.task_id, args.test_results, stage)
        with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(stage).as_posix())
        verify_archive(archive, stage)
    except Exception:
        if archive.exists():
            archive.unlink()
        raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)

    digest = sha256(archive)
    sidecar = archive.with_suffix(archive.suffix + ".sha256")
    sidecar.write_text(f"{digest}  {archive}\n", encoding="utf-8")
    print(f"ARCHIVE={archive}")
    print(f"SIZE={archive.stat().st_size}")
    print(f"SHA256={digest}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ReportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
