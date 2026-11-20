"""Stop hook: record the clean final assistant message for BA Dev Control."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from devcontrol.config import default_runtime_dir  # noqa: E402
from devcontrol.store import RuntimePaths, StateStore, utc_now  # noqa: E402
from devcontrol.telegram import sanitize_text  # noqa: E402

PATHS = RuntimePaths(default_runtime_dir())


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except OSError, ValueError:
        return 0
    if not isinstance(payload, dict) or payload.get("stop_hook_active"):
        return 0
    message = sanitize_text(str(payload.get("last_assistant_message") or ""))[:2000]
    store = StateStore(PATHS)
    store.append_event(
        "turn_done",
        detail=message,
        session_id=payload.get("session_id"),
        permission_mode=payload.get("permission_mode"),
    )
    store.update_state(last_message=message, last_message_at=utc_now())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
