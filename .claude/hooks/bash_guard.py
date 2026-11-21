#!/usr/bin/env python3
# ruff: noqa: T201
"""Narrow PreToolUse Bash guard for the Breaktime Arcade workspaces.

Defense-in-depth only: blocks obvious destructive commands and write-like
commands touching protected paths or the sibling repository. It is not a
sandbox and cannot understand arbitrary shell/Python programs.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

ROOT = Path(
    os.environ.get("CLAUDE_PROJECT_DIR", str(Path(__file__).resolve().parents[2]))
).resolve()
SIBLING = (
    Path("/home/elkinva/projects/ai-dev")
    if ROOT.name == "ba"
    else Path("/home/elkinva/projects/ba")
)

PROTECTED_NAMES = {
    ".env",
    ".env.staging",
    ".env.local",
    ".env.production",
    ".claude.json",
    "settings.local.json",
    "CLAUDE.md",
}
PROTECTED_DIRS = {".git", "certs", "creds", "secrets", "technical_specification"}
PROTECTED_PREFIXES = (".claude/hooks", ".claude/settings.json", ".claude/settings.local.json")
SAFE_ENV_NAMES = {".env.example", ".env.staging.example"}
PROTECTED_LITERALS = (
    "~/.bashrc",
    "$HOME/.bashrc",
    "${HOME}/.bashrc",
    "~/.claude/settings.json",
    "$HOME/.claude/settings.json",
    "~/.claude.json",
    "$HOME/.claude.json",
    "~/.config/ba/deepseek.env",
    "$HOME/.config/ba/deepseek.env",
)
PROTECTED_ABSOLUTE = (
    Path("~/.bashrc").expanduser().resolve(),
    Path("~/.claude/settings.json").expanduser().resolve(),
    Path("~/.claude.json").expanduser().resolve(),
    Path("~/.config/ba/deepseek.env").expanduser().resolve(),
)

WRITE_LIKE = re.compile(
    r"(^|[\s;&|])(?:>|>>|tee\b|sed\s+-i\b|cp\b|mv\b|rm\b|truncate\b|dd\b|install\b|chmod\b|chown\b|patch\b)"
)
SECRET_READ = re.compile(r"\b(?:cat|head|tail|grep|less|more|strings|xxd|base64|od)\b")
GIT_WRITE = re.compile(
    r"\bgit\s+(?:-C\s+\S+\s+)?(?:add|commit|reset|clean|checkout|restore|push|stash|tag|rebase|apply|merge)\b"
)
DESTRUCTIVE = (
    (
        re.compile(r"\bdocker[-\s]compose\b[^\n]*\bdown\b[^\n]*(-v|--volumes)\b"),
        "docker compose down -v",
    ),
    (
        re.compile(r"\bdocker[-\s]compose\b[^\n]*\brm\b[^\n]*(-v|--volumes)\b"),
        "docker compose rm -v",
    ),
    (re.compile(r"\bdocker\s+volume\s+rm\b"), "docker volume rm"),
    (re.compile(r"\bdocker\s+system\s+prune\b"), "docker system prune"),
    (re.compile(r"\bgit\s+reset\b[^\n]*--hard\b"), "git reset --hard"),
    (re.compile(r"\bgit\s+clean\s+-[a-zA-Z]*[fx]"), "git clean -f/-x"),
    (
        re.compile(r"\bgit\s+push\b[^\n]*(--force|--force-with-lease|\+[A-Za-z0-9])"),
        "git push force",
    ),
    (re.compile(r"\bgit\s+commit\b[^\n]*--amend\b"), "git commit --amend"),
    (re.compile(r"\bgit\s+rebase\b"), "git rebase"),
    (re.compile(r"\bgit\s+tag\s+-d\b"), "git tag -d"),
    (re.compile(r"\bgit\s+branch\s+-D\b"), "git branch -D"),
    (re.compile(r"\bgit\s+stash\b"), "git stash"),
    (re.compile(r"\bgit\s+add\s+(?:-A|--all|-f|--force)\b"), "git add -A/-f"),
    (re.compile(r"\bfind\b[^\n]*(?:-delete|-exec\b)"), "find -delete/-exec"),
    (re.compile(r"\bperl\s+-[a-zA-Z]*i"), "perl -i"),
    (re.compile(r"\btar\b[^\n]*\s-C\s+"), "tar -C"),
    (re.compile(r"\bunzip\b[^\n]*\s-o\b"), "unzip -o"),
    (re.compile(r"\bgit\s+apply\b"), "git apply"),
    (re.compile(r"\bpatch\b"), "patch"),
    (re.compile(r"\bunlink\b"), "unlink"),
    (re.compile(r"\b(?:mkfs|shred)\b"), "mkfs/shred"),
    (re.compile(r"\bdd\s+[^\n]*\bof="), "dd of="),
    (re.compile(r"\btruncate\s+-s\s+0\b"), "truncate -s 0"),
    (re.compile(r"\bFLUSHALL\b"), "redis FLUSHALL"),
    (re.compile(r"\bFLUSHDB\b"), "redis FLUSHDB"),
)


def resolved_paths(command: str, cwd: Path) -> list[Path]:
    try:
        tokens = shlex.split(command, comments=False, posix=True)
    except ValueError:
        tokens = command.split()
    paths: list[Path] = []
    for token in tokens:
        stripped = token.strip("'\"")
        if not stripped or stripped.startswith("-"):
            continue
        if "=" in stripped and not stripped.startswith("="):
            name, value = stripped.split("=", 1)
            if name.isidentifier() or name in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"}:
                stripped = value
        expanded = os.path.expandvars(os.path.expanduser(stripped))
        path = Path(expanded)
        if not path.is_absolute():
            path = cwd / path
        paths.append(path.resolve(strict=False))
    return paths


def has_unexpandable_syntax(command: str) -> bool:
    if re.search(r"[$`*?\[\]{}]", command):
        return True
    try:
        shlex.split(command, comments=False, posix=True)
    except ValueError:
        return True
    return False


def path_is_protected(path: Path) -> bool:
    if path in PROTECTED_ABSOLUTE:
        return True
    if path == SIBLING or SIBLING in path.parents:
        return True
    if any(part in PROTECTED_DIRS for part in path.parts):
        return True
    if path.name in PROTECTED_NAMES:
        return True
    rel = str(path)
    return any(prefix in rel for prefix in PROTECTED_PREFIXES)


def protected_path_mentioned(command: str, cwd: Path) -> bool:
    command = _strip_safe_env(command)
    for name in PROTECTED_NAMES:
        if name in command:
            return True
    for part in PROTECTED_DIRS:
        if f"/{part}/" in command or command.strip().endswith(f"/{part}"):
            return True
    for prefix in PROTECTED_PREFIXES:
        if prefix in command:
            return True
    if str(SIBLING) in command:
        return True
    for literal in PROTECTED_LITERALS:
        if literal in command:
            return True
    for path in PROTECTED_ABSOLUTE:
        if str(path) in command:
            return True
    return any(path_is_protected(path) for path in resolved_paths(command, cwd))


def rm_outside_tmp(command: str) -> bool:
    for match in re.finditer(r"\brm\s+-(?=[a-zA-Z]*r)[a-zA-Z]+\s+([^\n;&|]+)", command):
        for token in match.group(1).split():
            cleaned = token.strip("'\"")
            if cleaned.startswith("/tmp/") or cleaned == "/tmp":
                continue
            return True
    return False


def _restore_paths(command: str, cwd: Path) -> list[Path]:
    """Return explicit worktree paths for ``git restore``/``checkout --``."""
    try:
        tokens = shlex.split(command, comments=False, posix=True)
    except ValueError:
        return []
    if "restore" in tokens:
        index = tokens.index("restore")
    elif "checkout" in tokens and "--" in tokens:
        index = tokens.index("checkout")
    else:
        return []
    if "--staged" in tokens[index + 1 :]:
        return []
    paths: list[Path] = []
    for token in tokens[index + 1 :]:
        cleaned = token.strip("'\"")
        if not cleaned or cleaned == "--" or cleaned.startswith("-"):
            continue
        candidate = Path(os.path.expandvars(os.path.expanduser(cleaned)))
        if not candidate.is_absolute():
            candidate = cwd / candidate
        paths.append(candidate.resolve(strict=False))
    return paths


def _restore_allowed(path: Path) -> bool:
    if path == ROOT:
        return False
    try:
        path.relative_to(ROOT)
    except ValueError:
        return False
    return not path_is_protected(path)


def _strip_safe_env(command: str) -> str:
    for name in SAFE_ENV_NAMES:
        command = command.replace(name, "")
    return command


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception as exc:  # noqa: BLE001 - fail closed
        print(f"BA bash guard: cannot parse hook input: {exc}", file=sys.stderr)
        return 2
    if data.get("tool_name") != "Bash":
        return 0
    command = str((data.get("tool_input") or {}).get("command") or "")
    if not command.strip():
        return 0
    cwd = Path(data.get("cwd") or ROOT).resolve()

    if (WRITE_LIKE.search(command) or GIT_WRITE.search(command)) and has_unexpandable_syntax(
        command
    ):
        print(
            "BA bash guard: BLOCKED unexpandable path/glob in a write-like command.",
            file=sys.stderr,
        )
        return 2

    for pattern, label in DESTRUCTIVE:
        if pattern.search(command):
            print(f"BA bash guard: BLOCKED ({label}).", file=sys.stderr)
            return 2

    if rm_outside_tmp(command):
        print("BA bash guard: BLOCKED recursive rm outside /tmp.", file=sys.stderr)
        return 2

    if re.search(r"\bgit\s+(?:restore|checkout\s+--)\b", command):
        paths = _restore_paths(command, cwd)
        if not paths or not all(_restore_allowed(path) for path in paths):
            print(
                "BA bash guard: BLOCKED bare/protected/out-of-project git restore/checkout.",
                file=sys.stderr,
            )
            return 2

    if re.search(r"\bDROP\s+(?:DATABASE|TABLE)\b", command, re.IGNORECASE) and not re.search(
        r"\b(?:ba_schema_check_|test_)", command
    ):
        print(
            "BA bash guard: BLOCKED DROP DATABASE/TABLE outside a test database.", file=sys.stderr
        )
        return 2

    if protected_path_mentioned(command, cwd) and WRITE_LIKE.search(command):
        print(
            "BA bash guard: BLOCKED write-like command touching a protected path "
            "(.env, certs, creds, .git, technical_specification, CLAUDE.md, "
            "user config, hook/settings, or the sibling repository).",
            file=sys.stderr,
        )
        return 2

    secret_command = _strip_safe_env(command)
    if SECRET_READ.search(secret_command) and any(
        token in secret_command for token in (".env", "deepseek.env")
    ):
        print("BA bash guard: BLOCKED reading a secret path via shell.", file=sys.stderr)
        return 2

    if protected_path_mentioned(command, cwd) and GIT_WRITE.search(command):
        print(
            "BA bash guard: BLOCKED git write operation touching a protected path.", file=sys.stderr
        )
        return 2

    if re.search(r"\bgit\s+add\b", command) and protected_path_mentioned(command, cwd):
        print("BA bash guard: BLOCKED git add of a protected path.", file=sys.stderr)
        return 2

    if str(SIBLING) in command and GIT_WRITE.search(command):
        print(
            "BA bash guard: BLOCKED git write operation against the sibling repository.",
            file=sys.stderr,
        )
        return 2

    if re.search(rf'\bcd\s+["\']?{re.escape(str(SIBLING))}(?:["\']|\s|$)', command) and (
        WRITE_LIKE.search(command) or GIT_WRITE.search(command)
    ):
        print(
            "BA bash guard: BLOCKED write-like command after cd into the sibling repository.",
            file=sys.stderr,
        )
        return 2

    if re.search(r'\bcd\s+["\']?(?:\.\./)+ai-dev(?:["\']|/|\s|$)', command) and (
        WRITE_LIKE.search(command) or GIT_WRITE.search(command)
    ):
        print("BA bash guard: BLOCKED write-like command after cd into ai-dev.", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
