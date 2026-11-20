#!/usr/bin/env python3
# ruff: noqa: T201
"""PreToolUse guard for Breaktime Arcade.

Blocks Edit/Write/MultiEdit/NotebookEdit on protected project and user paths.
It is intentionally narrow: it does not format, delete, rewrite, publish, or
scan file contents. Other checks live in pre-commit/CI and the report skill.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(
    os.environ.get("CLAUDE_PROJECT_DIR", str(Path(__file__).resolve().parents[2]))
).resolve()

PROTECTED_RELATIVE_PREFIXES = {
    ("CLAUDE.md",),
    ("technical_specification",),
    ("docs", "spec"),
    (".git",),
    ("certs",),
    ("creds",),
    ("reports",),
    ("infra", "nginx", "staging.conf"),
    (".claude", "settings.local.json"),
}

# These are protected even when a tool addresses them outside the project.
PROTECTED_ABSOLUTE = {
    Path("~/.bashrc").expanduser().resolve(),
    Path("~/.claude/settings.json").expanduser().resolve(),
    Path("~/.claude.json").expanduser().resolve(),
    Path("~/.config/ba/deepseek.env").expanduser().resolve(),
}

# Safe secret templates may be edited; real .env files may not.
SAFE_ENV_NAMES = {".env.example", ".env.staging.example"}


def _target_path(data: dict) -> Path | None:
    tool_input = data.get("tool_input") or {}
    raw = tool_input.get("file_path") or tool_input.get("path") or tool_input.get("notebook_path")
    if not isinstance(raw, str) or not raw.strip():
        return None
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        cwd = Path(data.get("cwd") or PROJECT_ROOT)
        candidate = cwd / candidate
    return candidate.resolve(strict=False)


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _is_protected(path: Path) -> str | None:
    if path in PROTECTED_ABSOLUTE:
        return "protected user configuration"
    if not _within(path, PROJECT_ROOT):
        # Allow temporary test artifacts; block other writes outside the project.
        if _within(path, Path("/tmp").resolve()):  # noqa: S108
            return None
        return "path outside the project"

    rel = path.relative_to(PROJECT_ROOT)
    if any(rel.parts[: len(prefix)] == prefix for prefix in PROTECTED_RELATIVE_PREFIXES):
        return "protected project path"
    if rel.name == ".env" or (rel.name.startswith(".env.") and rel.name not in SAFE_ENV_NAMES):
        return "secret environment file"
    return None


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception as exc:  # noqa: BLE001 - hook must fail closed
        print(f"BA guard: cannot parse hook input: {exc}", file=sys.stderr)
        return 2

    tool_name = str(data.get("tool_name", ""))
    if tool_name not in {"Edit", "Write", "MultiEdit", "NotebookEdit"}:
        return 0

    path = _target_path(data)
    if path is None:
        return 0

    reason = _is_protected(path)
    if reason is None:
        return 0

    print(
        f"BA guard: BLOCKED {tool_name} on {path}: {reason}. "
        "This path is protected by BA-AUTONOMY-001; request owner approval.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
