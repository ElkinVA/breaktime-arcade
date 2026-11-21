"""Non-blocking efficiency metrics derived from durable task state."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from autonomy.state import COMPLETED, StateStore


def _duration_seconds(start: str | None, end: str | None) -> float:
    if not start or not end:
        return 0.0
    try:
        return max(
            0.0, (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
        )
    except ValueError:
        return 0.0


def compute_metrics(store: StateStore) -> dict[str, Any]:
    state = store.snapshot()
    tasks = list(state["tasks"].values())
    completed = [value for value in tasks if value.get("status") == COMPLETED]
    first_pass = [value for value in completed if int(value.get("attempts", 0)) <= 1]
    corrections = sum(max(0, int(value.get("attempts", 0)) - 1) for value in completed)
    durations = [
        _duration_seconds(value.get("created_at"), value.get("completed_at")) for value in completed
    ]
    tokens = sum(int(value.get("usage", {}).get("total_tokens", 0)) for value in completed)
    cost = sum(float(value.get("usage", {}).get("cost_usd", 0.0)) for value in completed)
    accepted = len(completed)
    duplicates = int(state.get("metrics", {}).get("duplicate_enqueues", 0))
    return {
        "accepted_tasks": accepted,
        "first_pass_accepted": len(first_pass),
        "first_pass_rate": round(len(first_pass) / accepted, 4) if accepted else 0.0,
        "correction_cycles": corrections,
        "review_rejections": sum(int(value.get("review_rejections", 0)) for value in tasks),
        "average_task_seconds": round(sum(durations) / accepted, 3) if accepted else 0.0,
        "tokens_per_accepted_task": round(tokens / accepted, 3) if accepted else 0.0,
        "cost_usd_per_accepted_task": round(cost / accepted, 6) if accepted else 0.0,
        "duplicate_enqueue_skips": duplicates,
        "repeated_file_reads": "not_available_from_cli_json",
    }
