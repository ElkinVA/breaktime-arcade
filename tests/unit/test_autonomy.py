from __future__ import annotations

import json
from pathlib import Path

import pytest
from autonomy.orchestrator import Orchestrator, _developer_files, _safe_file, _stage_task
from autonomy.runner import ClaudeRunner, RunResult
from autonomy.state import (
    BLOCKED,
    COMPLETED,
    QA,
    READY,
    RUNNING,
    StateError,
    StateStore,
    Task,
)


def test_queue_dedup_completed_and_recovery(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    task = Task(
        id="AUTONOMY-001",
        title="Add queue test",
        priority="Major",
        acceptance=["test exists"],
    )
    assert [item.id for item in store.enqueue([task])] == ["AUTONOMY-001"]
    assert store.enqueue([task]) == []

    claimed = store.claim_next()
    assert claimed is not None
    assert claimed.status == RUNNING
    assert claimed.attempts == 1

    store.transition(task.id, COMPLETED)
    assert (
        store.enqueue(
            [
                Task(
                    id="AUTONOMY-002",
                    title="Add queue test",
                    priority="Major",
                    acceptance=["test exists"],
                )
            ]
        )
        == []
    )
    assert store.recover_running() == []
    assert store.get(task.id).status == COMPLETED


def test_corrupt_state_fails_closed(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.path.write_text("{not json")
    with pytest.raises(StateError):
        store.snapshot()
    assert store.path.read_text() == "{not json"


def test_dependency_blocks_claim_until_completed(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.enqueue(
        [
            Task(
                id="AUTONOMY-BASE",
                title="Base",
                priority="Critical",
                acceptance=["base"],
            ),
            Task(
                id="AUTONOMY-DEP",
                title="Dependent",
                priority="Blocker",
                acceptance=["dependent"],
                dependencies=["AUTONOMY-BASE"],
            ),
        ]
    )
    assert store.claim_next().id == "AUTONOMY-BASE"
    store.transition("AUTONOMY-BASE", COMPLETED)
    assert store.claim_next().id == "AUTONOMY-DEP"


def test_recovery_retries_or_blocks_interrupted_task(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.enqueue([Task(id="AUTONOMY-R", title="Interrupted", priority="Minor", acceptance=["x"])])
    store.claim_next()
    recovered = store.recover_running()
    assert recovered[0].status == READY

    claimed = store.claim_next()
    assert claimed is not None
    recovered = store.recover_running()
    assert recovered[0].status == BLOCKED
    assert recovered[0].blocked_reason == "RECOVERED_AFTER_STOP"


def test_recovery_covers_qa_and_review_phases(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.enqueue([Task(id="AUTONOMY-QA", title="QA phase", priority="Minor", acceptance=["x"])])
    store.claim_next()
    store.transition("AUTONOMY-QA", QA)
    recovered = store.recover_running()
    assert recovered[0].status == READY


class FakeRunner:
    def __init__(self, architect_result: str = '{"tasks": []}', verdict: str = "accept") -> None:
        self.architect_result = architect_result
        self.verdict = verdict
        self.calls: list[str] = []

    def _result(self, role: str, result: str, model: str) -> RunResult:
        self.calls.append(role)
        return RunResult(
            role=role,
            model=model,
            agent=role,
            returncode=0,
            session_id=f"session-{role}",
            model_usage={model: {}},
            result=result,
            evidence_path=f"/tmp/{role}.json",
            duration_seconds=0.1,
        )

    def architect(self, prompt: str) -> RunResult:
        return self._result("architect", self.architect_result, "deepseek-v4-pro")

    def developer(self, prompt: str) -> RunResult:
        return self._result(
            "developer",
            '{"status":"done","files":["tests/unit/test_autonomy.py"]}',
            "deepseek-flash[1m]",
        )

    def qa(self, prompt: str) -> RunResult:
        return self._result("qa", '{"status":"pass"}', "deepseek-flash")

    def reviewer(self, prompt: str) -> RunResult:
        return self._result(
            "reviewer",
            json.dumps({"verdict": self.verdict, "findings": []}),
            "deepseek-v4-pro",
        )


def test_orchestrator_completes_and_does_not_requeue(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.enqueue([Task(id="AUTONOMY-OK", title="OK", priority="Major", acceptance=["a"])])
    runner = FakeRunner()
    orchestrator = Orchestrator(runner, store, commit=False)
    report = orchestrator.run_once(propose=False)

    assert report["status"] == "completed", report
    assert store.get("AUTONOMY-OK").status == COMPLETED
    assert runner.calls == ["developer", "qa", "reviewer"]
    assert (
        store.enqueue([Task(id="AUTONOMY-OK", title="OK", priority="Major", acceptance=["a"])])
        == []
    )


def test_orchestrator_retries_then_blocks_after_review_reject(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.enqueue([Task(id="AUTONOMY-BAD", title="Bad", priority="Major", acceptance=["a"])])
    runner = FakeRunner(verdict="reject")
    orchestrator = Orchestrator(runner, store, commit=False)

    first = orchestrator.run_once(propose=False)
    assert first["status"] == "retry"
    second = orchestrator.run_once(propose=False)
    assert second["status"] == "blocked"
    assert store.get("AUTONOMY-BAD").status == BLOCKED


def test_architect_only_enqueues_autonomy_tasks(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    runner = FakeRunner(
        architect_result=json.dumps(
            {
                "tasks": [
                    {
                        "id": "AUTONOMY-X",
                        "title": "Queue task",
                        "priority": "Major",
                        "acceptance": ["criterion"],
                    },
                    {
                        "id": "BA-GAME-FEATURE",
                        "title": "Forbidden game feature",
                        "priority": "Blocker",
                        "acceptance": ["forbidden"],
                    },
                ]
            }
        )
    )
    orchestrator = Orchestrator(runner, store, commit=False)
    added = orchestrator.propose()

    assert [task.id for task in added] == ["AUTONOMY-X"]
    assert store.get("BA-GAME-FEATURE") is None


def test_runner_parses_json_and_role_model() -> None:
    payload = {
        "modelUsage": {
            "deepseek-v4-pro": {"inputTokens": 1, "outputTokens": 1},
            "deepseek-flash": {"inputTokens": 1, "outputTokens": 1},
        },
        "session_id": "s",
        "result": "{}",
    }
    assert ClaudeRunner._parse_stdout("warning\n" + json.dumps(payload)) == payload
    assert ClaudeRunner._actual_model_matches("architect", payload["modelUsage"]) is True
    assert ClaudeRunner._actual_model_matches("developer", payload["modelUsage"]) is True
    assert ClaudeRunner._actual_model_matches("developer", {"deepseek-v4-pro": {}}) is False
    assert ClaudeRunner._actual_model_matches("architect", {"deepseek-v4-pro": {}}) is False
    assert (
        ClaudeRunner._actual_model_matches(
            "architect", {"deepseek-flash": {"inputTokens": 10, "outputTokens": 10}}
        )
        is False
    )


def test_safe_file_rejects_protected_and_escaping_paths(tmp_path: Path, monkeypatch) -> None:
    import autonomy.orchestrator as orchestrator

    monkeypatch.setattr(orchestrator, "ROOT", tmp_path)
    safe = tmp_path / "tests" / "unit" / "test_x.py"
    safe.parent.mkdir(parents=True)
    safe.write_text("x")
    assert _safe_file("tests/unit/test_x.py") == safe
    for name in (".env", ".claude/settings.json", "../outside.py", "/etc/hosts"):
        with pytest.raises(RuntimeError):
            _safe_file(name)


def test_stage_task_rejects_pre_staged_unrelated_changes(monkeypatch) -> None:
    import autonomy.orchestrator as orchestrator

    calls: list[list[str]] = []

    class Completed:
        returncode = 0
        stderr = ""
        stdout = "tests/unit/other.py\n"

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return Completed()

    monkeypatch.setattr(orchestrator.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="unexpected staged"):
        _stage_task(["tests/unit/test_autonomy.py"])
    assert calls[0][:3] == ["git", "add", "--"]


def test_developer_files_rejects_unsafe_or_empty_reports() -> None:
    empty = RunResult(
        role="developer",
        model="deepseek-flash",
        agent="autonomy-developer",
        returncode=0,
        session_id="s",
        model_usage={},
        result='{"status":"done","files":[]}',
        evidence_path="",
        duration_seconds=0,
    )
    try:
        _developer_files(empty)
    except RuntimeError:
        pass
    else:
        raise AssertionError("empty file list must be rejected")
