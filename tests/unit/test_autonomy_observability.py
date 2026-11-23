from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

import autonomy.runner as runner_module
import pytest
from autonomy.budget import Budget, BudgetTracker
from autonomy.observability import (
    CLAUDE_CODE,
    FINISHED_EVENT,
    STARTED_EVENT,
    InvocationMetrics,
    InvocationStart,
    from_failure,
    from_outcome,
    from_run_result,
    read_invocations,
    reconcile_invocations,
    record_finished,
    record_invocation,
    record_started,
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


def _success_payload(
    *,
    model: str = "deepseek-flash",
    is_error: bool = False,
    input_tokens: int = 10,
) -> dict[str, object]:
    return {
        "modelUsage": {
            model: {
                "inputTokens": input_tokens,
                "outputTokens": 2,
                "cacheReadInputTokens": 100,
                "cacheCreationInputTokens": 4,
                "costUSD": 0.03,
            }
        },
        "session_id": "session-2",
        "num_turns": 4,
        "result": "{}",
        "is_error": is_error,
    }


class _Completed:
    def __init__(self, payload: dict[str, object] | None = None, *, returncode: int = 0) -> None:
        self.returncode = returncode
        self.stdout = json.dumps(payload) if payload is not None else "not json"
        self.stderr = ""


def _runner(tmp_path: Path) -> runner_module.ClaudeRunner:
    return runner_module.ClaudeRunner(journal_root=tmp_path / "journal")


def _install(monkeypatch: pytest.MonkeyPatch, result: object, tmp_path: Path) -> None:
    monkeypatch.setattr(runner_module, "EVIDENCE_ROOT", tmp_path / "evidence")
    monkeypatch.setattr(runner_module.subprocess, "run", lambda *args, **kwargs: result)


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
    assert metrics.request_count_known is False
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
    assert metrics.event == FINISHED_EVENT
    assert metrics.status == "ok"
    assert metrics.usage_known is True
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
    assert summary["accepted_cost_unknown_usage_invocations"] == 0
    assert summary["by_task"]["ARCADE-1"]["invocations"] == 2
    assert summary["by_role"]["developer"]["invocations"] == 1
    assert summary["by_role"]["reviewer"]["invocations"] == 1
    assert "secret" not in json.dumps(summary)


def test_duplicate_invocation_ids_are_counted_once(tmp_path: Path) -> None:
    record = from_run_result(_result(), task_id="ARCADE-1").as_dict()
    duplicate = dict(record, input_tokens=999)
    path = tmp_path / "invocations.jsonl"
    path.write_text(json.dumps(record) + "\n" + json.dumps(duplicate) + "\n", encoding="utf-8")
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


def test_orchestrator_account_does_not_write_lifecycle_events(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    orchestrator = Orchestrator(object(), store)
    tracker = BudgetTracker(Budget())
    orchestrator._account("ARCADE-1", _result(), tracker)
    assert read_invocations(tmp_path) == []
    assert tracker.usage.total_tokens == 119
    assert store.snapshot()["usage"]["total_tokens"] == 119


def test_runner_writes_started_before_spawn_and_finished_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = tmp_path / "journal"
    observed: list[list[dict[str, object]]] = []

    def fake_run(*args: object, **kwargs: object) -> _Completed:
        observed.append(read_invocations(journal))
        return _Completed(_success_payload())

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)
    monkeypatch.setattr(runner_module, "EVIDENCE_ROOT", tmp_path / "evidence")

    result = _runner(tmp_path).run(
        role="developer",
        model="deepseek-flash",
        agent="test",
        prompt="must not be persisted",
        allowed_tools=[],
        permission_mode="acceptEdits",
    )

    assert observed and observed[0][0]["event"] == STARTED_EVENT
    assert observed[0][0]["invocation_id"] == result.invocation_id
    records = read_invocations(journal)
    assert [item["event"] for item in records] == [STARTED_EVENT, FINISHED_EVENT]
    finished = records[1]
    assert finished["status"] == "ok"
    assert finished["usage_known"] is True
    assert finished["input_tokens"] == 10
    assert finished["cache_hit_tokens"] == 100
    assert finished["exit_code"] == 0
    assert finished["request_count_known"] is False
    assert "must not be persisted" not in json.dumps(records)


def test_runner_api_error_preserves_reported_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _success_payload(is_error=True)
    _install(monkeypatch, _Completed(payload, returncode=1), tmp_path)

    with pytest.raises(runner_module.RunnerError):
        _runner(tmp_path).run(
            role="developer",
            model="deepseek-flash",
            agent="test",
            prompt="hello",
            allowed_tools=[],
            permission_mode="acceptEdits",
        )

    finished = read_invocations(tmp_path / "journal")[1]
    assert finished["status"] == "failed"
    assert finished["error_type"] == "api_error"
    assert finished["usage_known"] is True
    assert finished["input_tokens"] == 10
    assert finished["estimated_cost_usd"] == 0.03
    assert finished["exit_code"] == 1


def test_runner_zeroed_error_usage_is_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {
        "modelUsage": {"deepseek-flash": {"inputTokens": 0, "outputTokens": 0}},
        "is_error": True,
        "result": "",
    }
    _install(monkeypatch, _Completed(payload, returncode=1), tmp_path)

    with pytest.raises(runner_module.RunnerError):
        _runner(tmp_path).run(
            role="developer",
            model="deepseek-flash",
            agent="test",
            prompt="hello",
            allowed_tools=[],
            permission_mode="acceptEdits",
        )

    finished = read_invocations(tmp_path / "journal")[1]
    assert finished["status"] == "failed"
    assert finished["usage_known"] is False
    assert finished["input_tokens"] is None
    assert finished["estimated_cost_usd"] is None


def test_runner_invalid_output_marks_usage_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(monkeypatch, _Completed(returncode=0), tmp_path)

    with pytest.raises(runner_module.RunnerError):
        _runner(tmp_path).run(
            role="developer",
            model="deepseek-flash",
            agent="test",
            prompt="hello",
            allowed_tools=[],
            permission_mode="acceptEdits",
        )

    finished = read_invocations(tmp_path / "journal")[1]
    assert finished["status"] == "failed"
    assert finished["error_type"] == "invalid_output"
    assert finished["usage_known"] is False
    assert finished["output_tokens"] is None


def test_runner_timeout_records_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: object, **kwargs: object) -> _Completed:
        raise subprocess.TimeoutExpired(cmd=["claude"], timeout=1)

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)
    monkeypatch.setattr(runner_module, "EVIDENCE_ROOT", tmp_path / "evidence")

    with pytest.raises(runner_module.RunnerError):
        _runner(tmp_path).run(
            role="developer",
            model="deepseek-flash",
            agent="test",
            prompt="hello",
            allowed_tools=[],
            permission_mode="acceptEdits",
            timeout=1,
        )

    finished = read_invocations(tmp_path / "journal")[1]
    assert finished["status"] == "timeout"
    assert finished["error_type"] == "timeout"
    assert finished["usage_known"] is False
    assert finished["exit_code"] is None
    assert finished["duration_seconds"] >= 0


def test_runner_keyboard_interrupt_records_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(*args: object, **kwargs: object) -> _Completed:
        raise KeyboardInterrupt

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)
    monkeypatch.setattr(runner_module, "EVIDENCE_ROOT", tmp_path / "evidence")

    with pytest.raises(KeyboardInterrupt):
        _runner(tmp_path).run(
            role="developer",
            model="deepseek-flash",
            agent="test",
            prompt="hello",
            allowed_tools=[],
            permission_mode="acceptEdits",
        )

    finished = read_invocations(tmp_path / "journal")[1]
    assert finished["status"] == "cancelled"
    assert finished["error_type"] == "operator_interrupt"
    assert finished["usage_known"] is False


def test_authoritative_finish_wins_over_inferred(tmp_path: Path) -> None:
    start = InvocationStart(
        invocation_id="inv-1",
        agent_id="autonomy-developer",
        role="developer",
        model="deepseek-flash",
        started_at="2026-11-23T09:00:00+00:00",
        task_id="ARCADE-1",
        attempt_id="run-1",
        retry_count=1,
    )
    record_started(tmp_path, start)
    inferred = InvocationMetrics(
        task_id="ARCADE-1",
        attempt_id="run-1",
        agent_id="autonomy-developer",
        role="developer",
        session_id=None,
        invocation_id="inv-1",
        model="deepseek-flash",
        reported_models=(),
        execution_channel="orchestrator",
        request_count=None,
        num_turns=None,
        input_tokens=None,
        cache_hit_tokens=None,
        cache_miss_tokens=None,
        output_tokens=None,
        reasoning_tokens=None,
        estimated_cost_usd=None,
        started_at="2026-11-23T09:00:00+00:00",
        finished_at=None,
        status="interrupted",
        accepted_result=None,
        retry_count=1,
        usage_source=CLAUDE_CODE,
        usage_known=False,
        inferred=True,
        reconciled_at="2026-11-23T10:00:00+00:00",
    )
    authoritative = from_run_result(
        _result(invocation_id="inv-1"), task_id="ARCADE-1", attempt_id="run-1", retry_count=1
    )
    record_finished(tmp_path, inferred)
    record_finished(tmp_path, authoritative)

    summary = summarize(read_invocations(tmp_path), accepted_task_ids={"ARCADE-1"})
    assert summary["totals"]["invocations"] == 1
    assert summary["totals"]["input_tokens"] == 12
    assert summary["by_status"]["ok"]["invocations"] == 1
    assert summary["totals"]["inferred_invocations"] == 0


def test_pending_started_is_not_accepted_cost(tmp_path: Path) -> None:
    record_started(
        tmp_path,
        InvocationStart(
            invocation_id="inv-pending",
            agent_id="autonomy-developer",
            role="developer",
            model="deepseek-flash",
            started_at="2026-11-23T09:00:00+00:00",
            task_id="ARCADE-1",
        ),
    )
    summary = summarize(read_invocations(tmp_path), accepted_task_ids={"ARCADE-1"})
    assert summary["totals"]["invocations"] == 1
    assert summary["totals"]["pending_invocations"] == 1
    assert summary["totals"]["usage_unknown_invocations"] == 1
    assert summary["accepted_cost_usd"] == 0.0
    assert summary["by_status"]["pending"]["invocations"] == 1


def test_reconcile_skips_authoritatively_finished_invocation(tmp_path: Path) -> None:
    record_started(
        tmp_path,
        InvocationStart(
            invocation_id="inv-race",
            agent_id="autonomy-developer",
            role="developer",
            model="deepseek-flash",
            started_at="2026-11-23T09:00:00+00:00",
            owner_pid=999999,
            boot_id="boot-1",
        ),
    )
    record_finished(
        tmp_path,
        from_run_result(_result(invocation_id="inv-race"), task_id="ARCADE-1"),
    )
    written = reconcile_invocations(
        tmp_path,
        now="2026-11-23T10:00:00+00:00",
        current_boot_id="boot-1",
        pid_probe=lambda pid, ticks: "dead",
    )
    assert written == []
    summary = summarize(read_invocations(tmp_path))
    assert summary["totals"]["invocations"] == 1
    assert summary["by_status"]["ok"]["invocations"] == 1
    assert summary["totals"]["input_tokens"] == 12


def test_reconcile_dead_owner_is_interrupted_and_idempotent(tmp_path: Path) -> None:
    record_started(
        tmp_path,
        InvocationStart(
            invocation_id="inv-dead",
            agent_id="autonomy-developer",
            role="developer",
            model="deepseek-flash",
            started_at="2026-11-23T09:00:00+00:00",
            task_id="ARCADE-1",
            owner_pid=999999,
            owner_pid_start_ticks=1,
            boot_id="boot-1",
        ),
    )
    written = reconcile_invocations(
        tmp_path,
        now="2026-11-23T10:00:00+00:00",
        current_boot_id="boot-1",
        pid_probe=lambda pid, ticks: "dead",
    )
    assert len(written) == 1
    assert written[0]["status"] == "interrupted"
    assert written[0]["error_type"] == "orchestrator_gone"
    assert written[0]["inferred"] is True
    assert written[0]["usage_known"] is False
    assert written[0]["finished_at"] is None
    assert written[0]["duration_seconds"] is None

    assert (
        reconcile_invocations(
            tmp_path,
            now="2026-11-23T10:05:00+00:00",
            current_boot_id="boot-1",
            pid_probe=lambda pid, ticks: "dead",
        )
        == []
    )


def test_reconcile_live_owner_is_not_closed(tmp_path: Path) -> None:
    record_started(
        tmp_path,
        InvocationStart(
            invocation_id="inv-live",
            agent_id="autonomy-developer",
            role="developer",
            model="deepseek-flash",
            started_at="2026-11-23T09:00:00+00:00",
            owner_pid=1234,
            owner_pid_start_ticks=10,
            boot_id="boot-1",
        ),
    )
    written = reconcile_invocations(
        tmp_path,
        now="2026-11-23T10:00:00+00:00",
        current_boot_id="boot-1",
        pid_probe=lambda pid, ticks: "alive",
    )
    assert written == []
    assert summarize(read_invocations(tmp_path))["totals"]["pending_invocations"] == 1


def test_reconcile_boot_change_is_host_reboot(tmp_path: Path) -> None:
    record_started(
        tmp_path,
        InvocationStart(
            invocation_id="inv-reboot",
            agent_id="autonomy-developer",
            role="developer",
            model="deepseek-flash",
            started_at="2026-11-23T09:00:00+00:00",
            owner_pid=1234,
            boot_id="boot-1",
        ),
    )
    written = reconcile_invocations(
        tmp_path,
        now="2026-11-23T10:00:00+00:00",
        current_boot_id="boot-2",
        pid_probe=lambda pid, ticks: "alive",
    )
    assert written[0]["status"] == "interrupted"
    assert written[0]["error_type"] == "host_reboot"


def test_partial_tail_is_ignored(tmp_path: Path) -> None:
    start = InvocationStart(
        invocation_id="inv-partial",
        agent_id="autonomy-developer",
        role="developer",
        model="deepseek-flash",
        started_at="2026-11-23T09:00:00+00:00",
    )
    path = tmp_path / "invocations.jsonl"
    path.write_text(
        json.dumps(start.as_dict()) + "\n" + '{"event": "invocation_finished"',
        encoding="utf-8",
    )
    records = read_invocations(tmp_path)
    assert len(records) == 1
    assert summarize(records)["totals"]["pending_invocations"] == 1


def test_concurrent_appends_remain_whole_lines(tmp_path: Path) -> None:
    def writer(index: int) -> None:
        record_finished(
            tmp_path,
            from_run_result(_result(invocation_id=f"inv-{index}"), task_id="ARCADE-1"),
        )

    threads = [threading.Thread(target=writer, args=(index,)) for index in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    records = read_invocations(tmp_path)
    assert len(records) == 20
    assert {item["invocation_id"] for item in records} == {f"inv-{index}" for index in range(20)}
    assert summarize(records)["totals"]["input_tokens"] == 240
    summary = summarize(records)
    assert summary["by_status"]["ok"]["input_tokens"] == 240
    assert summary["by_status"]["ok"]["estimated_cost_usd"] == pytest.approx(0.8)


def test_runner_launch_error_records_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(*args: object, **kwargs: object) -> _Completed:
        raise OSError("claude not found")

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)
    monkeypatch.setattr(runner_module, "EVIDENCE_ROOT", tmp_path / "evidence")

    with pytest.raises(OSError):
        _runner(tmp_path).run(
            role="developer",
            model="deepseek-flash",
            agent="test",
            prompt="hello",
            allowed_tools=[],
            permission_mode="acceptEdits",
        )

    finished = read_invocations(tmp_path / "journal")[1]
    assert finished["status"] == "failed"
    assert finished["error_type"] == "launch_error"
    assert finished["usage_known"] is False


def test_runner_model_mismatch_preserves_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _success_payload(model="other-model")
    _install(monkeypatch, _Completed(payload, returncode=0), tmp_path)

    with pytest.raises(runner_module.RunnerError):
        _runner(tmp_path).run(
            role="developer",
            model="deepseek-flash",
            agent="test",
            prompt="hello",
            allowed_tools=[],
            permission_mode="acceptEdits",
        )

    finished = read_invocations(tmp_path / "journal")[1]
    assert finished["status"] == "failed"
    assert finished["error_type"] == "model_mismatch"
    assert finished["usage_known"] is True
    assert finished["input_tokens"] == 10


def test_runner_evidence_failure_keeps_terminal_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        runner_module.subprocess, "run", lambda *a, **k: _Completed(_success_payload())
    )

    def fail_write(evidence: dict[str, object]) -> str:
        raise OSError("disk full")

    monkeypatch.setattr(runner_module.ClaudeRunner, "_write_evidence", staticmethod(fail_write))

    with pytest.raises(OSError):
        _runner(tmp_path).run(
            role="developer",
            model="deepseek-flash",
            agent="test",
            prompt="hello",
            allowed_tools=[],
            permission_mode="acceptEdits",
        )

    finished = read_invocations(tmp_path / "journal")[1]
    assert finished["status"] == "ok"
    assert finished["usage_known"] is True


def test_reconcile_pid_reused_is_interrupted(tmp_path: Path) -> None:
    record_started(
        tmp_path,
        InvocationStart(
            invocation_id="inv-reused",
            agent_id="autonomy-developer",
            role="developer",
            model="deepseek-flash",
            started_at="2026-11-23T09:00:00+00:00",
            owner_pid=1234,
            owner_pid_start_ticks=10,
            boot_id="boot-1",
        ),
    )
    written = reconcile_invocations(
        tmp_path,
        now="2026-11-23T10:00:00+00:00",
        current_boot_id="boot-1",
        pid_probe=lambda pid, ticks: "reused",
    )
    assert written[0]["status"] == "interrupted"
    assert written[0]["error_type"] == "pid_reused"


def test_reconcile_unverifiable_start_is_abandoned(tmp_path: Path) -> None:
    record_started(
        tmp_path,
        InvocationStart(
            invocation_id="inv-abandoned",
            agent_id="autonomy-developer",
            role="developer",
            model="deepseek-flash",
            started_at="2026-11-23T09:00:00+00:00",
            owner_pid=None,
            boot_id=None,
        ),
    )
    written = reconcile_invocations(
        tmp_path,
        now="2026-11-23T10:00:00+00:00",
        current_boot_id="boot-1",
        pid_probe=lambda pid, ticks: "unknown",
        stale_after_seconds=60,
    )
    assert written[0]["status"] == "unknown"
    assert written[0]["error_type"] == "abandoned_unknown"


def test_reconcile_missing_started_at_is_abandoned(tmp_path: Path) -> None:
    record_started(
        tmp_path,
        InvocationStart(
            invocation_id="inv-no-time",
            agent_id="autonomy-developer",
            role="developer",
            model="deepseek-flash",
            started_at=None,
            owner_pid=None,
            boot_id=None,
        ),
    )
    written = reconcile_invocations(
        tmp_path,
        now="2026-11-23T10:00:00+00:00",
        current_boot_id="boot-1",
        pid_probe=lambda pid, ticks: "unknown",
    )
    assert written[0]["status"] == "unknown"
    assert written[0]["error_type"] == "abandoned_unknown"


def test_error_type_is_a_closed_enum() -> None:
    with pytest.raises(ValueError):
        from_failure(
            invocation_id="inv-bad",
            agent="autonomy-developer",
            role="developer",
            model="deepseek-flash",
            status="failed",
            error_type="not_a_real_error",
        )


def test_reasoning_only_usage_is_known() -> None:
    metrics = from_outcome(
        invocation_id="inv-reasoning",
        agent="autonomy-developer",
        role="developer",
        model="deepseek-flash",
        status="ok",
        model_usage={"deepseek-flash": {"reasoningTokens": 7}},
    )
    assert metrics.usage_known is True
    assert metrics.reasoning_tokens == 7


def test_manual_reconcile_cli_closes_orphan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from autonomy.observability import main

    record_started(
        tmp_path,
        InvocationStart(
            invocation_id="inv-cli",
            agent_id="autonomy-developer",
            role="developer",
            model="deepseek-flash",
            started_at="2026-11-23T09:00:00+00:00",
            owner_pid=2**31 - 1,
            boot_id=None,
        ),
    )
    assert main(["reconcile", "--root", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "inv-cli" in output
    finished = read_invocations(tmp_path)[-1]
    assert finished["status"] == "interrupted"
    assert finished["error_type"] == "orchestrator_gone"
