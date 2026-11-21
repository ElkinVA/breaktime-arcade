from __future__ import annotations

from pathlib import Path

from autonomy.metrics import compute_metrics
from autonomy.state import COMPLETED, StateStore, Task


def test_metrics_report_acceptance_and_cost_per_task(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    first = Task(
        id="ARCADE-METRICS-1",
        title="One",
        priority="Major",
        acceptance=["a"],
        attempts=1,
        status=COMPLETED,
        usage={"total_tokens": 100, "cost_usd": 0.5},
    )
    second = Task(
        id="ARCADE-METRICS-2",
        title="Two",
        priority="Major",
        acceptance=["b"],
        attempts=2,
        status=COMPLETED,
        usage={"total_tokens": 300, "cost_usd": 1.5},
        review_rejections=1,
    )
    store.enqueue([first, second])
    store.enqueue([first])

    metrics = compute_metrics(store)

    assert metrics["accepted_tasks"] == 2
    assert metrics["first_pass_accepted"] == 1
    assert metrics["first_pass_rate"] == 0.5
    assert metrics["correction_cycles"] == 1
    assert metrics["tokens_per_accepted_task"] == 200.0
    assert metrics["cost_usd_per_accepted_task"] == 1.0
    assert metrics["duplicate_enqueue_skips"] == 1
    assert metrics["review_rejections"] == 1
    assert metrics["repeated_file_reads"] == "not_available_from_cli_json"
