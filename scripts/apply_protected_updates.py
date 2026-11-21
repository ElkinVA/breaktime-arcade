#!/usr/bin/env python3
# ruff: noqa: T201
"""Apply the protected BA instruction/guard updates.

The project PreToolUse guard intentionally blocks agent edits to CLAUDE.md and
.claude/hooks/. Run this script manually from the repository root after
reviewing the dry-run diff:

    python3 scripts/apply_protected_updates.py --dry-run
    python3 scripts/apply_protected_updates.py --apply

It is idempotent, refuses partial/ambiguous matches, writes atomically, and
keeps a backup under /tmp/ba-protected-backups/<timestamp>/.
"""

from __future__ import annotations

import argparse
import difflib
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAUDE = ROOT / "CLAUDE.md"
GUARD = ROOT / ".claude" / "hooks" / "bash_guard.py"


def _replace(text: str, old: str, new: str, label: str) -> tuple[str, str]:
    if new and new in text:
        return text, f"already applied: {label}"
    if old not in text:
        if not new:
            return text, f"already applied: {label}"
        raise SystemExit(f"ERROR: expected block not found ({label})")
    return text.replace(old, new, 1), f"updated: {label}"


def update_claude(text: str) -> tuple[str, list[str]]:
    notes: list[str] = []

    old = (
        "App F (gameplay, leaderboards, ratings, SDK, player/runtime) **не реализован**;\n"
        "`schemas/*.json` содержат DRAFT App F; `sdk/1.1.0/ba-sdk.js` и `games-src/*` пусты.\n"
    )
    new = (
        "App F server slices — session/result/leaderboard/storage/playtime/ratings/\n"
        "popularity — реализованы и ожидают продуктовой приёмки. App F runtime/SDK/\n"
        "player и `games-src` **не реализованы**; `schemas/*.json` содержат DRAFT\n"
        "App F; `sdk/1.1.0/ba-sdk.js` пуст.\n"
    )
    text, note = _replace(text, old, new, "current state")
    notes.append(note)

    old = "## Команды (все через Makefile, выполняются ВНУТРИ контейнера web)"
    new = "## Команды (через Makefile; quality/DB — в web, инфраструктура — на хосте)"
    text, note = _replace(text, old, new, "commands heading")
    notes.append(note)

    old = "Проверки: ./verify_stack.sh, ./verify_staging_final.sh (read-only)."
    new = (
        "`env/certs/assets/lock/build/up/down/restart/staging-*/verify_*` — на хосте;\n"
        "`test/lint/fmt/types/check/migrate/shell/psql` — в `web`.\n"
        "Проверки: ./verify_stack.sh, ./verify_staging_final.sh (read-only)."
    )
    text, note = _replace(text, old, new, "host/container command split")
    notes.append(note)

    old = "- Никакого self-review; `IMPLEMENTED` ≠ `ACCEPTED`. Приёмка — только владелец."
    new = (
        "- Никакого self-review; `IMPLEMENTED` ≠ `ACCEPTED`. Техническая приёмка\n"
        "  агента — по OD-AUTONOMY-003; продуктовая/юридическая — только владелец."
    )
    text, note = _replace(text, old, new, "acceptance scope")
    notes.append(note)
    return text, notes


def _restore_helper() -> str:
    return '''def _restore_paths(command: str, cwd: Path) -> list[Path]:
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
        cleaned = token.strip("'\\\"")
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


'''


def update_guard(text: str) -> tuple[str, list[str]]:
    notes: list[str] = []

    # 1) Allow reading .env.example / .env.staging.example.
    old = (
        "def protected_path_mentioned(command: str, cwd: Path) -> bool:\n"
        "    for name in PROTECTED_NAMES:\n"
    )
    new = (
        "def protected_path_mentioned(command: str, cwd: Path) -> bool:\n"
        "    command = _strip_safe_env(command)\n"
        "    for name in PROTECTED_NAMES:\n"
    )
    text, note = _replace(text, old, new, "safe env examples in protected-path check")
    notes.append(note)

    old = (
        "    if SECRET_READ.search(command) and any(token in command "
        'for token in (".env", "deepseek.env")):\n'
    )
    new = (
        "    secret_command = _strip_safe_env(command)\n"
        "    if SECRET_READ.search(secret_command) and any(\n"
        '        token in secret_command for token in (".env", "deepseek.env")\n'
        "    ):\n"
    )
    text, note = _replace(text, old, new, "safe env examples in secret-read check")
    notes.append(note)

    # 2) Remove unconditional restore/checkout blockers.
    old = (
        '    (re.compile(r"\\bgit\\s+checkout\\s+--\\b"), "git checkout --"),\n'
        '    (re.compile(r"\\bgit\\s+restore\\b"), "git restore"),\n'
    )
    text, note = _replace(text, old, "", "unconditional git restore/checkout block")
    notes.append(note)

    # 3) Add scoped restore/checkout validation before the protected-path checks.
    old = (
        "    if rm_outside_tmp(command):\n"
        '        print("BA bash guard: BLOCKED recursive rm outside /tmp.", file=sys.stderr)\n'
        "        return 2\n"
    )
    new = old + (
        "\n"
        '    if re.search(r"\\bgit\\s+(?:restore|checkout\\s+--)\\b", command):\n'
        "        paths = _restore_paths(command, cwd)\n"
        "        if not paths or not all(_restore_allowed(path) for path in paths):\n"
        "            print(\n"
        '                "BA bash guard: BLOCKED bare/protected/out-of-project "\n'
        '                "git restore/checkout.",\n'
        "                file=sys.stderr,\n"
        "            )\n"
        "            return 2\n"
    )
    text, note = _replace(text, old, new, "scoped git restore/checkout validation")
    notes.append(note)

    # 4) Insert helpers after rm_outside_tmp.
    old = (
        "def rm_outside_tmp(command: str) -> bool:\n"
        '    for match in re.finditer(r"\\brm\\s+-(?=[a-zA-Z]*r)[a-zA-Z]+'
        '\\s+([^\\n;&|]+)", command):\n'
        "        for token in match.group(1).split():\n"
        '            cleaned = token.strip("\'\\"")\n'
        '            if cleaned.startswith("/tmp/") or cleaned == "/tmp":\n'
        "                continue\n"
        "            return True\n"
        "    return False\n"
    )
    helper = _restore_helper().rstrip() + "\n"
    if helper.strip() not in text:
        text, note = _replace(text, old, old + "\n" + helper, "restore helpers")
        notes.append(note)
    return text, notes


def _diff(path: Path, old: str, new: str) -> str:
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{path.relative_to(ROOT)}",
            tofile=f"b/{path.relative_to(ROOT)}",
        )
    )


def _apply(path: Path, new: str, backup_dir: Path) -> None:
    backup = backup_dir / path.relative_to(ROOT)
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup)
    mode = path.stat().st_mode
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        handle.write(new)
        temporary = Path(handle.name)
    try:
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes")
    parser.add_argument("--dry-run", action="store_true", help="show diff (default)")
    args = parser.parse_args()
    if args.apply and args.dry_run:
        parser.error("choose either --apply or --dry-run")
    apply = args.apply

    targets: list[tuple[Path, str, list[str]]] = []
    for path, updater in ((CLAUDE, update_claude), (GUARD, update_guard)):
        old = path.read_text(encoding="utf-8")
        new, notes = updater(old)
        targets.append((path, new, notes))
        print(f"{path.relative_to(ROOT)}:")
        for note in notes:
            print(f"  - {note}")
        if new != old:
            print(_diff(path, old, new))
        else:
            print("  - no changes")

    if not apply:
        print("\nDry run only. Re-run with --apply to write.")
        return 0

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = Path("/tmp/ba-protected-backups") / stamp  # noqa: S108
    for path, new, _notes in targets:
        if new != path.read_text(encoding="utf-8"):
            _apply(path, new, backup_dir)
            print(f"updated {path.relative_to(ROOT)}")
    print(f"backups: {backup_dir}")
    print("Next: review git diff, run make check, commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
