"""Agent-contract tests for the autonomy role definitions.

The orchestrator routes each role to a fixed model and parses a role-specific
JSON object from the agent output.  These tests keep the committed agent files
in sync with that policy.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / ".claude" / "agents"

MODEL_POLICY = {
    "autonomy-architect": "deepseek-v4-pro",
    "autonomy-developer": "deepseek-flash",
    "autonomy-qa": "deepseek-flash",
    "autonomy-reviewer": "deepseek-v4-pro",
}

OUTPUT_KEYS = {
    "autonomy-architect": {
        "tasks",
        "id",
        "title",
        "priority",
        "acceptance",
        "dependencies",
    },
    "autonomy-developer": {
        "status",
        "summary",
        "files",
        "commands",
        "cmd",
        "exit",
        "risks",
        "blocked",
        "reason",
    },
    "autonomy-qa": {
        "status",
        "commands",
        "cmd",
        "exit",
        "output",
        "findings",
    },
    "autonomy-reviewer": {
        "verdict",
        "findings",
        "severity",
        "file",
        "summary",
        "scenario",
        "tested",
        "not_tested",
    },
}


def _split_document(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    assert lines and lines[0] == "---", "agent file must start with frontmatter"
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise AssertionError("frontmatter is not terminated") from None

    meta: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        key, separator, value = line.partition(":")
        assert separator, f"frontmatter line is not 'key: value': {line!r}"
        key = key.strip()
        assert key and key not in meta, f"duplicate or empty frontmatter key: {key!r}"
        meta[key] = value.strip()
    return meta, "\n".join(lines[end + 1 :])


def _load_agent(role: str) -> tuple[dict[str, str], str]:
    path = AGENTS / f"{role}.md"
    assert path.is_file(), f"missing agent definition: {path}"
    return _split_document(path.read_text(encoding="utf-8"))


def test_agent_frontmatter_has_required_fields() -> None:
    for role in MODEL_POLICY:
        meta, _body = _load_agent(role)
        assert {"name", "model", "tools"} <= meta.keys()
        assert meta["name"] == role
        tools = meta["tools"].split(",")
        assert tools and all(tool.strip() for tool in tools), (
            f"{role} tools must be a non-empty comma-separated list"
        )


def test_agent_model_routing_matches_policy() -> None:
    routed = {role: _load_agent(role)[0]["model"] for role in MODEL_POLICY}
    assert routed == MODEL_POLICY


def test_agent_body_documents_role_json_output_keys() -> None:
    for role, keys in OUTPUT_KEYS.items():
        _meta, body = _load_agent(role)
        missing = sorted(key for key in keys if f'"{key}"' not in body)
        assert not missing, f"{role} body is missing output keys: {missing}"
