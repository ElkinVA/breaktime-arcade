"""Static contract tests for the autonomous control-plane configuration.

These tests only parse committed JSON.  They never start Claude Code, Docker or
the network, so they are safe to run in every environment.
"""

from __future__ import annotations

import fnmatch
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROJECT_SETTINGS = ROOT / ".claude" / "settings.json"
DEVCONTROL_SETTINGS = ROOT / "devcontrol" / "claude-settings.json"

WRITE_MATCHER = "Edit|Write|MultiEdit|NotebookEdit"

# Every listed command bypasses the isolated sandbox that autonomous sessions
# must use for tests; the deny list has to win over any allow rule.
SANDBOX_BYPASS_RULES = {
    "pytest tests/unit": "Bash(pytest*)",
    "make test": "Bash(make test*)",
    "docker compose exec web pytest -q": "Bash(docker compose exec*)",
    'python3 -c "print(1)"': "Bash(python3 -c*)",
}


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{path} must contain a JSON object"
    return data


def _pre_tool_use_entries(settings: dict[str, Any], matcher: str) -> list[dict[str, Any]]:
    entries = settings["hooks"]["PreToolUse"]
    assert isinstance(entries, list)
    matched = [entry for entry in entries if entry.get("matcher") == matcher]
    assert matched, f"no PreToolUse entry for matcher {matcher!r}"
    return matched


def _bash_pattern(rule: str) -> str:
    assert rule.startswith("Bash(") and rule.endswith(")")
    return rule[len("Bash(") : -1]


def test_project_settings_wire_both_pre_tool_use_guards() -> None:
    settings = _load_json(PROJECT_SETTINGS)

    for matcher, script in (
        ("Bash", "bash_guard.py"),
        (WRITE_MATCHER, "guard_protected_paths.py"),
    ):
        entries = _pre_tool_use_entries(settings, matcher)
        commands = [hook.get("command", "") for entry in entries for hook in entry.get("hooks", [])]
        assert any(script in command for command in commands), (
            f"{matcher!r} is not wired to {script}"
        )
        for entry in entries:
            hooks = entry.get("hooks")
            assert isinstance(hooks, list) and hooks, f"{matcher!r} has no hooks"
            for hook in hooks:
                assert hook.get("type") == "command"
                assert hook.get("onFailure") == "block", (
                    f"{script} must fail closed with onFailure=block"
                )


@pytest.mark.parametrize(("command", "expected_rule"), SANDBOX_BYPASS_RULES.items())
def test_autonomous_settings_deny_sandbox_bypass(command: str, expected_rule: str) -> None:
    settings = _load_json(DEVCONTROL_SETTINGS)
    deny = settings["permissions"]["deny"]
    assert isinstance(deny, list)
    assert expected_rule in deny
    assert any(
        rule.startswith("Bash(") and fnmatch.fnmatchcase(command, _bash_pattern(rule))
        for rule in deny
    ), f"{command!r} is not denied by the autonomous settings"
