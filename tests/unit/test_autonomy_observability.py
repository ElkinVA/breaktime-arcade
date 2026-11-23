from __future__ import annotations

import json
from pathlib import Path

import autonomy.runner as runner_module
import pytest
from autonomy.budget import Budget, BudgetTracker
from autonomy.observability import (
    CLAUDE_CODE,
    InvocationMetrics,
    from_run_result,
    read_invocations,
    record_invocation,
    summarize,
)
from autonomy.orchestrator import Orchestrator
from autonomy.runner import RunResult
from autonomy.state import StateStore


def _result(
    *,
    role: str = "developer",
    model: str = "deepseek-flash[1m]",
    session_id: str = "session-1",
    invocation_id: str = "inv-1",
    request_count: int | None = None,
    num_turns: int | None = 3,
) -> RunResult:
    return RunResult(
        role=role,
        model=model,
        agent=f"autonomy-{role}",
        returncode=0,
        session_id=session_id,
        model_usage={
            model: {
                "inputTokens": 12,
                "outputTokens": 3,
                "cacheReadInputTokens": 100,
                "cacheCreationInputTokens": 4,
                "costUSD": 0.04,
            }
        },
        result='{"secret":"must not be persisted"}',
        evidence_path="/tmp/evidence.json",
        duration_seconds=0.2,
        total_cost_usd=0.04,
        invocation_id=invocation_id,
        started_at="2026-11-23T09:00:00+00:00",
        finished_at="2026-11-23T09:00:01+00:00",
        request_count=request_count,
        num_turns=num_turns,
    )


def test_from_run_result_keeps_metadata_and_excludes_content() -> None:
    metrics = InvocationMetrics.from_run_result(
        _result(),
        task_id="ARCADE-1",
        attempt_id="run-1",
        retry_count=1,
    )
    assert metrics.task_id == "ARCADE-1"
    assert metrics.attempt_id == "run-1"
    assert metrics.role == "developer"
    assert metrics.agent_id == "autonomy-developer"
    assert metrics.session_id == "session-1"
    assert metrics.invocation_id == "inv-1"
    assert metrics.model == "deepseek-flash[1m]"
    assert metrics.reported_models == ("deepseek-flash[1m]",)
    assert metrics.request_count is None
    assert metrics.num_turns == 3
    assert metrics.input_tokens == 12
    assert metrics.cache_hit_tokens == 100
    assert metrics.cache_miss_tokens == 16
    assert metrics.output_tokens == 3
    assert metrics.estimated_cost_usd == 0.04
    assert metrics.usage_source == CLAUDE_CODE
    assert metrics.execution_channel == "orchestrator"
    assert metrics.accepted_result is None
    assert metrics.retry_count == 1
    assert "secret" not in json.dumps(metrics.as_dict())


def test_record_and_read_are_append_only_and_deduplicated(tmp_path: Path) -> None:
    first = from_run_result(_result(invocation_id="inv-1"), task_id="ARCADE-1")
    second = from_run_result(
        _result(invocation_id="inv-2", role="reviewer", model="deepseek-v4-pro"),
        task_id="ARCADE-1",
    )
    record_invocation(tmp_path, first)
    record_invocation(tmp_path, second)
    records = read_invocations(tmp_path)
    assert len(records) == 2

    summary = summarize(records, accepted_task_ids={"ARCADE-1"})
    assert summary["totals"]["invocations"] == 2
    assert summary["totals"]["input_tokens"] == 24
    assert summary["totals"]["cache_hit_tokens"] == 200
    assert summary["totals"]["cache_miss_tokens"] == 32
    assert summary["totals"]["output_tokens"] == 6
    assert summary["accepted_tasks"] == 1
    assert summary["accepted_cost_usd"] == 0.08
    assert summary["by_task"]["ARCADE-1"]["invocations"] == 2
    assert summary["by_role"]["developer"]["invocations"] == 1
    assert summary["by_role"]["reviewer"]["invocations"] == 1
    assert "secret" not in json.dumps(summary)


def test_duplicate_invocation_ids_are_counted_once(tmp_path: Path) -> None:
    record = from_run_result(_result(), task_id="ARCADE-1").as_dict()
    duplicate = dict(record, input_tokens=999)
    path = tmp_path / "invocations.jsonl"
    path.write_text(
        json.dumps(record) + "\n" + json.dumps(duplicate) + "\n", encoding="utf-8"
    )
    summary = summarize(read_invocations(tmp_path))
    assert summary["totals"]["invocations"] == 1
    assert summary["totals"]["input_tokens"] == 12


def test_corrupt_marker_is_not_an_invocation(tmp_path: Path) -> None:
    path = tmp_path / "invocations.jsonl"
    path.write_text(
        json.dumps({"corrupt_lines": 3}) + "\n" + json.dumps({"invocation_id": "x"}) + "\n",
        encoding="utf-8",
    )
    records = read_invocations(tmp_path, include_corrupt=True)
    summary = summarize(records)
    assert summary["totals"]["invocations"] == 1


def test_zero_cost_is_recorded_as_zero(tmp_path: Path) -> None:
    result = _result()
    result = type(result)(
        **{
            **result.__dict__,
            "model_usage": {"deepseek-flash[1m]": {"inputTokens": 1, "outputTokens": 0}},
            "total_cost_usd": 0.0,
        }
    )
    metrics = from_run_result(result)
    assert metrics.estimated_cost_usd == 0.0
    record_invocation(tmp_path, metrics)
    assert summarize(read_invocations(tmp_path))["totals"]["estimated_cost_usd"] == 0.0


def test_missing_optional_usage_is_not_fabricated(tmp_path: Path) -> None:
    result = _result(request_count=None, num_turns=None)
    metrics = from_run_result(result)
    assert metrics.request_count is None
    assert metrics.num_turns is None
    record_invocation(tmp_path, metrics)
    summary = summarize(read_invocations(tmp_path))
    assert summary["totals"]["request_count_known"] == 0
    assert summary["by_task"]["(unassigned)"]["request_count"] == 0


def test_orchestrator_account_records_task_and_attempt(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    orchestrator = Orchestrator(object(), store)
    orchestrator._account(
        "ARCADE-1",
        _result(),
        BudgetTracker(Budget()),
        attempt_id="run-1",
        retry_count=1,
    )
    records = read_invocations(tmp_path)
    assert len(records) == 1
    assert records[0]["task_id"] == "ARCADE-1"
    assert records[0]["attempt_id"] == "run-1"
    assert records[0]["retry_count"] == 1
    assert records[0]["role"] == "developer"
    assert "secret" not in json.dumps(records[0])


def test_runner_captures_invocation_metadata_and_optional_counters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {
        "modelUsage": {"deepseek-flash": {"inputTokens": 10, "outputTokens": 2}},
        "session_id": "session-2",
        "request_count": 9,
        "num_turns": 4,
        "result": "{}",
    }

    class Completed:
        returncode = 0
        stdout = json.dumps(payload)
        stderr = ""

    monkeypatch.setattr(runner_module, "EVIDENCE_ROOT", tmp_path)
    monkeypatch.setattr(runner_module.subprocess, "run", lambda *args, **kwargs: Completed())

    result = runner_module.ClaudeRunner().run(
        role="developer",
        model="deepseek-flash",
        agent="test",
        prompt="must not be persisted",
        allowed_tools=[],
        permission_mode="acceptEdits",
    )

    assert result.invocation_id
    assert result.started_at
    assert result.finished_at
    assert result.request_count == 9
    assert result.num_turns == 4
    evidence = json.loads(Path(result.evidence_path).read_text(encoding="utf-8"))
    assert evidence["invocation_id"] == result.invocation_id
    assert evidence["request_count"] == 9
    assert evidence["num_turns"] == 4
    assert "must not be persisted" not in json.dumps(evidence)
