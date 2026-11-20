"""SessionEnd hook: record why the autonomous session ended."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from devcontrol.config import default_runtime_dir  # noqa: E402
from devcontrol.store import RuntimePaths, StateStore  # noqa: E402

PATHS = RuntimePaths(default_runtime_dir())


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except OSError, ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    store = StateStore(PATHS)
    store.append_event(
        "session_end",
        detail=str(payload.get("reason") or "")[:500],
        session_id=payload.get("session_id"),
    )
    store.update_state(status="IDLE", session_active=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
