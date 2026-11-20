# ruff: noqa: T201
"""PermissionRequest hook: log the request and deny anything not pre-allowed.

The session's allow/deny rules still take precedence; this hook is the
unattended fallback for a request that would otherwise wait for a human.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from devcontrol.config import default_runtime_dir  # noqa: E402
from devcontrol.store import RuntimePaths, StateStore  # noqa: E402
from devcontrol.telegram import sanitize_text  # noqa: E402

PATHS = RuntimePaths(default_runtime_dir())


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except OSError, ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    tool = str(payload.get("tool_name") or "unknown")
    tool_input = payload.get("tool_input")
    detail = sanitize_text(json.dumps(tool_input, ensure_ascii=False))[:1000] if tool_input else ""
    store = StateStore(PATHS)
    store.append_event(
        "permission_request",
        task=None,
        title=tool,
        detail=detail,
        session_id=payload.get("session_id"),
    )
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PermissionRequest",
                    "decision": {
                        "behavior": "deny",
                        "message": "BA Dev Control: owner approval required",
                    },
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
