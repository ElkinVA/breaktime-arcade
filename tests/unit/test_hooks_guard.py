"""Regression tests for the BA hooks: ``bash_guard.py`` and ``guard_protected_paths.py``.

The hooks are driven exactly as Claude Code drives them: one JSON object on
stdin, exit code 2 means BLOCK, exit code 0 means ALLOW.  The tests are
hermetic: no network, no Docker, no real destructive command is executed.

Rules documented in ``.claude/README.md`` and
``docs/foundation/BA-AUTONOMY-003_REPORT.md`` are covered, including the
BA-AUTONOMY-003 evasion cases.
"""

from __future__ import annotations

import json
import os
import subprocess  # noqa: S404 - the hooks are external processes by design
import sys
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASH_GUARD = PROJECT_ROOT / ".claude" / "hooks" / "bash_guard.py"
PATH_GUARD = PROJECT_ROOT / ".claude" / "hooks" / "guard_protected_paths.py"

# Mirror bash_guard.py's sibling-repository derivation without importing it.
SIBLING = (
    Path("/home/elkinva/projects/ai-dev")
    if PROJECT_ROOT.name == "ba"
    else Path("/home/elkinva/projects/ba")
)

# Absolute paths protected even outside the project (same expansion as the hooks).
PROTECTED_USER_PATHS = [
    str(Path("~/.bashrc").expanduser().resolve()),
    str(Path("~/.claude/settings.json").expanduser().resolve()),
    str(Path("~/.claude.json").expanduser().resolve()),
    str(Path("~/.config/ba/deepseek.env").expanduser().resolve()),
]


def _run_hook(hook: Path, payload: dict[str, Any] | str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(PROJECT_ROOT)
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(  # noqa: S603 - fixed interpreter + repo-local script
        [sys.executable, str(hook)],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        env=env,
        timeout=30,
        check=False,
    )


def _bash(
    command: str,
    *,
    tool_name: str = "Bash",
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return _run_hook(
        BASH_GUARD,
        {
            "tool_name": tool_name,
            "tool_input": {"command": command},
            "cwd": str(cwd or PROJECT_ROOT),
        },
    )


def _write_tool(
    tool_name: str,
    path: str,
    *,
    key: str = "file_path",
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return _run_hook(
        PATH_GUARD,
        {
            "tool_name": tool_name,
            "tool_input": {key: path},
            "cwd": str(cwd or PROJECT_ROOT),
        },
    )


def _assert_blocked(result: subprocess.CompletedProcess[str], fragment: str) -> None:
    assert result.returncode == 2, (result.returncode, result.stderr)
    assert fragment in result.stderr, result.stderr


def _assert_allowed(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, (result.returncode, result.stderr)


def _outside_project_path() -> str:
    """An existing-unrelated absolute path outside the project and outside /tmp."""
    for base in (Path("/var/tmp"), Path("/opt")):
        candidate = base / "ba-guard-outside" / "file.txt"
        if not candidate.is_relative_to(PROJECT_ROOT):
            return str(candidate)
    raise AssertionError("cannot build a path outside the project")


# ---------------------------------------------------------------------------
# bash_guard.py — BLOCK rules
# ---------------------------------------------------------------------------

BASH_BLOCK_RULES = [
    # docker compose / volumes / prune
    ("docker compose down -v", "docker compose down -v"),
    ("docker-compose down -v", "docker compose down -v"),
    ("docker compose down --volumes", "docker compose down -v"),
    ("docker compose rm -v web", "docker compose rm -v"),
    ("docker volume rm ba_pgdata", "docker volume rm"),
    ("docker system prune -af", "docker system prune"),
    # git destructive / history rewrite
    ("git reset --hard HEAD~1", "git reset --hard"),
    ("git reset HEAD --hard", "git reset --hard"),
    ("git clean -fdx", "git clean -f/-x"),
    ("git clean -x", "git clean -f/-x"),
    ("git push --force origin main", "git push force"),
    ("git push --force-with-lease origin main", "git push force"),
    ("git push origin +main", "git push force"),
    ("git commit --amend --no-edit", "git commit --amend"),
    ("git rebase -i main", "git rebase"),
    ("git tag -d v1.0.0", "git tag -d"),
    ("git branch -D feature", "git branch -D"),
    ("git stash push", "git stash"),
    ("git add -A", "git add -A/-f"),
    ("git add --all", "git add -A/-f"),
    ("git add -f apps/core/views.py", "git add -A/-f"),
    # file-mutating evasions
    ("find . -name '*.pyc' -delete", "find -delete/-exec"),
    ("find . -name '*.tmp' -exec echo {} ;", "find -delete/-exec"),
    ("perl -i -pe 's/a/b/g' file.txt", "perl -i"),
    ("tar -C /tmp -xf archive.tar", "tar -C"),
    ("unzip -o game.zip", "unzip -o"),
    ("git apply fix.patch", "git apply"),
    ("patch -p1 < fix.diff", "patch"),
    ("unlink .env", "unlink"),
    ("mkfs.ext4 /dev/sdz", "mkfs/shred"),
    ("shred -u secret.txt", "mkfs/shred"),
    ("dd if=/dev/zero of=/tmp/zero", "dd of="),
    ("truncate -s 0 apps/core/views.py", "truncate -s 0"),
    ("redis-cli FLUSHALL", "redis FLUSHALL"),
    ("redis-cli -n 1 FLUSHDB", "redis FLUSHDB"),
    # recursive rm outside /tmp
    ("rm -rf build", "recursive rm outside /tmp"),
    ("rm -r /var/data", "recursive rm outside /tmp"),
    # git restore / checkout
    ("git restore .", "git restore/checkout"),
    ("git restore --staged .", "git restore/checkout"),
    (f"git restore {SIBLING}/file.txt", "git restore/checkout"),
    # DROP outside a test database
    ("psql -c 'DROP DATABASE ba'", "DROP DATABASE/TABLE outside a test database"),
    ("psql -c 'DROP TABLE apps_game'", "DROP DATABASE/TABLE outside a test database"),
    ("drop database ba;", "DROP DATABASE/TABLE outside a test database"),
    # write-like commands touching protected paths
    ("cp /tmp/x .env", "write-like command touching a protected path"),
    ("mv /tmp/x .env", "write-like command touching a protected path"),
    ("echo x > CLAUDE.md", "write-like command touching a protected path"),
    ("cp /tmp/x creds/credentials.json", "write-like command touching a protected path"),
    ("cp /tmp/x certs/server.key", "write-like command touching a protected path"),
    ("echo x > .git/config", "write-like command touching a protected path"),
    (
        "cp /tmp/x .claude/settings.local.json",
        "write-like command touching a protected path",
    ),
    (
        "cp /tmp/x technical_specification/BA-PLAT-4.2.md",
        "write-like command touching a protected path",
    ),
    (
        "sed -i 's/a/b/' .claude/hooks/bash_guard.py",
        "write-like command touching a protected path",
    ),
    (
        "cp /tmp/x .claude/settings.json",
        "write-like command touching a protected path",
    ),
    ("sed -i 's/a/b/' ~/.bashrc", "write-like command touching a protected path"),
    (
        "echo x > ~/.claude/settings.json",
        "write-like command touching a protected path",
    ),
    ("echo x > ~/.claude.json", "write-like command touching a protected path"),
    (
        "echo x > ~/.config/ba/deepseek.env",
        "write-like command touching a protected path",
    ),
    ("chmod 600 .env", "write-like command touching a protected path"),
    (f"cp {SIBLING}/file.txt /tmp/copy", "write-like command touching a protected path"),
    # reading secrets via shell
    ("cat .env", "reading a secret path"),
    ("head .env.staging", "reading a secret path"),
    ("grep SECRET_KEY .env", "reading a secret path"),
    # git writes touching protected paths / sibling repository
    ("git add .env", "git write operation touching a protected path"),
    ("git add CLAUDE.md", "git write operation touching a protected path"),
    ("git commit -m update .env", "git write operation touching a protected path"),
    (f"git -C {SIBLING} add file.txt", "git write operation touching a protected path"),
    (f"cd {SIBLING} && git add file.txt", "git write operation touching a protected path"),
]

BASH_EVASION_CASES = [
    # BA-AUTONOMY-003 evasion set (all must BLOCK)
    "git add .env",
    "git add -A",
    "git add -f",
    "git reset --hard",
    "git push --force",
    "docker compose down -v",
    "find . -delete",
    "find . -exec rm {} ;",
    "perl -i -pe 's/a/b/' file",
    "tar -C /tmp -xf archive.tar",
    "unzip -o bundle.zip",
    "patch -p1 < change.diff",
    "git apply change.patch",
    "cd ../ai-dev && git add file.txt",
    "mv /tmp/x .env",
]


@pytest.mark.parametrize(("command", "fragment"), BASH_BLOCK_RULES)
def test_bash_guard_blocks_documented_rules(command: str, fragment: str) -> None:
    _assert_blocked(_bash(command), fragment)


@pytest.mark.parametrize("command", BASH_EVASION_CASES)
def test_bash_guard_blocks_autonomy_003_evasions(command: str) -> None:
    result = _bash(command)
    assert result.returncode == 2, (command, result.returncode, result.stderr)


def test_bash_guard_blocks_unexpandable_write_like_command() -> None:
    _assert_blocked(_bash("rm -rf $HOME/data"), "unexpandable path/glob")
    _assert_blocked(_bash("cp * .env"), "unexpandable path/glob")


def test_bash_guard_blocks_write_after_cd_into_ai_dev() -> None:
    # On a checkout named "ba" an earlier protected-path rule may match first;
    # on any other checkout the dedicated cd-into-ai-dev rule must fire.
    result = _bash("cd ../ai-dev && git add file.txt")
    assert result.returncode == 2, (result.returncode, result.stderr)


# ---------------------------------------------------------------------------
# bash_guard.py — ALLOW cases
# ---------------------------------------------------------------------------

BASH_ALLOW_CASES = [
    "cat .env.example",
    "cat .env.staging.example",
    "echo x > .env.example",
    "cp .env.example /tmp/env.example",
    "rm -rf /tmp/ba-guard-build",
    "rm -r /tmp",
    "git restore apps/core/views.py",
    "psql -c 'DROP DATABASE test_ba'",
    "psql -c 'DROP TABLE ba_schema_check_public.games'",
    "git add apps/core/views.py",
    "git commit -m 'normal commit'",
    "git push origin main",
    "git status --short",
    "find apps -name '*.py'",
    "make test",
    "ls -la",
    "docker compose ps",
]


@pytest.mark.parametrize("command", BASH_ALLOW_CASES)
def test_bash_guard_allows_documented_safe_commands(command: str) -> None:
    _assert_allowed(_bash(command))


@pytest.mark.parametrize("command", ["", "   "])
def test_bash_guard_allows_empty_command(command: str) -> None:
    _assert_allowed(_bash(command))


def test_bash_guard_ignores_non_bash_tools() -> None:
    _assert_allowed(_bash("docker compose down -v", tool_name="Read"))


def test_bash_guard_fails_closed_on_invalid_json() -> None:
    result = _run_hook(BASH_GUARD, "{not json")
    _assert_blocked(result, "cannot parse hook input")


# ---------------------------------------------------------------------------
# guard_protected_paths.py — BLOCK rules
# ---------------------------------------------------------------------------

PROTECTED_PROJECT_PATHS = [
    "CLAUDE.md",
    "technical_specification/BA-PLAT-4.2.md",
    "docs/spec/feature.md",
    ".git/config",
    "certs/server.pem",
    "creds/credentials.json",
    "reports/audit.md",
    "infra/nginx/staging.conf",
    ".claude/settings.json",
    ".claude/settings.local.json",
    ".claude/hooks/bash_guard.py",
    ".env",
    ".env.staging",
    ".env.local",
    ".env.production",
    ".env.prod",  # unknown .env.* is treated as secret
]

WRITE_TOOLS = ["Edit", "Write", "MultiEdit", "NotebookEdit"]


@pytest.mark.parametrize("tool_name", WRITE_TOOLS)
@pytest.mark.parametrize("path", PROTECTED_PROJECT_PATHS)
def test_path_guard_blocks_protected_project_paths(tool_name: str, path: str) -> None:
    key = "notebook_path" if tool_name == "NotebookEdit" else "file_path"
    result = _write_tool(tool_name, path, key=key)
    _assert_blocked(result, "BLOCKED")


@pytest.mark.parametrize("path", PROTECTED_USER_PATHS)
def test_path_guard_blocks_protected_user_config(path: str) -> None:
    _assert_blocked(_write_tool("Edit", path), "protected user configuration")


def test_path_guard_blocks_writes_outside_project() -> None:
    _assert_blocked(
        _write_tool("Write", _outside_project_path()),
        "path outside the project",
    )


def test_path_guard_blocks_relative_path_escaping_project() -> None:
    _assert_blocked(_write_tool("Edit", "../outside.txt"), "path outside the project")


def test_path_guard_blocks_absolute_protected_project_path() -> None:
    _assert_blocked(
        _write_tool("Write", str(PROJECT_ROOT / ".env")),
        "secret environment file",
    )


def test_path_guard_fails_closed_on_invalid_json() -> None:
    result = _run_hook(PATH_GUARD, "[not json")
    _assert_blocked(result, "cannot parse hook input")


# ---------------------------------------------------------------------------
# guard_protected_paths.py — ALLOW cases
# ---------------------------------------------------------------------------

PATH_ALLOW_CASES = [
    ".env.example",
    ".env.staging.example",
    "apps/core/views.py",
    "templates/base.html",
    "tests/unit/test_hooks_guard.py",
    "/tmp/ba-guard-allowed.txt",
    "node_modules/example/index.js",
]


@pytest.mark.parametrize("path", PATH_ALLOW_CASES)
def test_path_guard_allows_safe_paths(path: str) -> None:
    _assert_allowed(_write_tool("Write", path))


def test_path_guard_allows_absolute_project_path() -> None:
    _assert_allowed(_write_tool("Edit", str(PROJECT_ROOT / "apps" / "core" / "views.py")))


@pytest.mark.parametrize("tool_name", ["Bash", "Read", "Grep", "Glob", ""])
def test_path_guard_ignores_non_write_tools(tool_name: str) -> None:
    _assert_allowed(_write_tool(tool_name, ".env"))


@pytest.mark.parametrize("tool_input", [{}, {"file_path": ""}, {"path": "   "}])
def test_path_guard_ignores_missing_path(tool_input: dict[str, str]) -> None:
    result = _run_hook(PATH_GUARD, {"tool_name": "Edit", "tool_input": tool_input})
    _assert_allowed(result)
