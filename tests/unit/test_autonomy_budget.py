"""Fake-model coverage for hard task, wall-clock, token and cost budgets."""

from __future__ import annotations

import json
from pathlib import Path

import autonomy.runner as runner_module
import pytest
from autonomy.budget import (
    DEFAULT_MAX_COST_USD,
    DEFAULT_MAX_RUN_SECONDS,
    DEFAULT_MAX_TASKS,
    DEFAULT_MAX_TOKENS,
    MAX_TASKS,
    WALL_CLOCK,
    Budget,
    BudgetError,
    BudgetTracker,
    Usage,
)
from autonomy.orchestrator import Orchestrator
from autonomy.runner import RunResult
from autonomy.state import READY, StateStore, Task


def _usage_result(
    role: str,
    model: str,
    *,
    tokens: int = 0,
    cost: float = 0.0,
    result: str = "{}",
) -> RunResult:
    return RunResult(
        role=role,
        model=model,
        agent=role,
        returncode=0,
        session_id=f"session-{role}",
        model_usage={
            model: {
                "inputTokens": tokens,
                "outputTokens": 0,
                "cacheReadInputTokens": 0,
                "cacheCreationInputTokens": 0,
                "costUSD": cost,
            }
        },
        result=result,
        evidence_path=f"/tmp/{role}.json",
        duration_seconds=0.1,
        total_cost_usd=cost,
    )


class BudgetFakeRunner:
    """Model double that reports real-looking ``modelUsage`` for every role."""

    def __init__(self, *, tokens: int = 0, cost: float = 0.0) -> None:
        self.tokens = tokens
        self.cost = cost
        self.calls: list[str] = []

    def architect(self, prompt: str, **_: object) -> RunResult:
        del prompt
        self.calls.append("architect")
        return _usage_result(
            "architect",
            "deepseek-v4-pro",
            tokens=self.tokens,
            cost=self.cost,
            result='{"tasks": []}',
        )

    def developer(self, prompt: str, **_: object) -> RunResult:
        del prompt
        self.calls.append("developer")
        return _usage_result(
            "developer",
            "deepseek-flash[1m]",
            tokens=self.tokens,
            cost=self.cost,
            result=(
                '{"status":"done","files":["tests/unit/test_autonomy_budget.py"],'
                '"self_check":{"spec_reviewed":true,"scope_reviewed":true,'
                '"tests_run":["targeted"],"localization_reviewed":true,'
                '"known_limits":[]}}'
            ),
        )

    def qa(self, prompt: str, **_: object) -> RunResult:
        del prompt
        self.calls.append("qa")
        return _usage_result(
            "qa",
            "deepseek-flash",
            tokens=self.tokens,
            cost=self.cost,
            result='{"status":"pass"}',
        )

    def reviewer(self, prompt: str, **_: object) -> RunResult:
        del prompt
        self.calls.append("reviewer")
        return _usage_result(
            "reviewer",
            "deepseek-v4-pro",
            tokens=self.tokens,
            cost=self.cost,
            result=json.dumps({"verdict": "accept", "findings": []}),
        )


def _orchestrator(
    tmp_path: Path,
    runner: BudgetFakeRunner,
    budget: Budget,
) -> tuple[Orchestrator, StateStore]:
    store = StateStore(tmp_path)
    orchestrator = Orchestrator(
        runner,
        store,
        commit=False,
        worktrees=False,
        budget=budget,
    )
    return orchestrator, store


def _enqueue(store: StateStore, count: int = 1) -> None:
    store.enqueue(
        [
            Task(
                id=f"AUTONOMY-BUDGET-{index}",
                title=f"Budget task {index}",
                priority="Major",
                acceptance=[f"criterion {index}"],
            )
            for index in range(count)
        ]
    )


def test_budget_defaults_and_environment_overrides() -> None:
    defaults = Budget.from_env({})
    assert defaults.max_tasks == DEFAULT_MAX_TASKS
    assert defaults.max_run_seconds == DEFAULT_MAX_RUN_SECONDS
    assert defaults.max_tokens == DEFAULT_MAX_TOKENS
    assert defaults.max_cost_usd == DEFAULT_MAX_COST_USD

    configured = Budget.from_env(
        {
            "BA_MAX_TASKS_PER_RUN": "7",
            "BA_MAX_RUN_SECONDS": "120.5",
            "BA_MAX_TOKENS": "1000",
            "BA_MAX_COST_USD": "2.25",
        }
    )
    assert configured == Budget(
        max_tasks=7,
        max_run_seconds=120.5,
        max_tokens=1000,
        max_cost_usd=2.25,
    )


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("BA_MAX_TASKS_PER_RUN", "many"),
        ("BA_MAX_RUN_SECONDS", "-1"),
        ("BA_MAX_TOKENS", "1.5"),
        ("BA_MAX_COST_USD", "nan"),
    ],
)
def test_invalid_environment_budget_fails_closed(key: str, value: str) -> None:
    with pytest.raises(BudgetError):
        Budget.from_env({key: value})


def test_cli_task_request_is_clamped_to_hard_cap() -> None:
    budget = Budget(max_tasks=2)
    assert budget.task_cap(None) == 2
    assert budget.task_cap(1) == 1
    assert budget.task_cap(100) == 2
    assert budget.task_cap(-5) == 0


def test_usage_is_summed_from_actual_model_usage() -> None:
    usage = Usage.from_model_usage(
        {
            "deepseek-flash": {
                "inputTokens": 10,
                "outputTokens": 5,
                "cacheReadInputTokens": 100,
                "cacheCreationInputTokens": 20,
                "costUSD": 0.25,
            },
            "deepseek-v4-pro": {
                "inputTokens": 1,
                "outputTokens": 2,
                "costUSD": 0.05,
            },
        }
    )
    assert usage.input_tokens == 11
    assert usage.output_tokens == 7
    assert usage.cache_read_tokens == 100
    assert usage.cache_creation_tokens == 20
    assert usage.total_tokens == 138
    assert usage.cost_usd == pytest.approx(0.30)


def test_cost_falls_back_to_invocation_total_when_model_usage_has_no_cost() -> None:
    usage = Usage.from_model_usage(
        {"deepseek-flash": {"inputTokens": 10, "outputTokens": 5}},
        total_cost_usd=0.42,
    )
    assert usage.total_tokens == 15
    assert usage.cost_usd == pytest.approx(0.42)


def test_runner_captures_usage_in_evidence_and_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {
        "modelUsage": {
            "deepseek-flash": {
                "inputTokens": 12,
                "outputTokens": 3,
                "cacheReadInputTokens": 5,
                "costUSD": 0.04,
            }
        },
        "session_id": "session-1",
        "result": "{}",
    }

    class Completed:
        returncode = 0
        stdout = json.dumps(payload)
        stderr = ""

    monkeypatch.setattr(runner_module, "EVIDENCE_ROOT", tmp_path)
    monkeypatch.setattr(runner_module.subprocess, "run", lambda *args, **kwargs: Completed())

    result = runner_module.ClaudeRunner(journal_root=tmp_path / "journal").run(
        role="developer",
        model="deepseek-flash",
        agent="test",
        prompt="prompt",
        allowed_tools=[],
        permission_mode="acceptEdits",
    )

    assert result.usage.total_tokens == 20
    assert result.usage.cost_usd == pytest.approx(0.04)
    evidence = json.loads(Path(result.evidence_path).read_text(encoding="utf-8"))
    assert evidence["usage"]["total_tokens"] == 20
    assert evidence["usage"]["cost_usd"] == pytest.approx(0.04)
    assert evidence["modelUsage"] == payload["modelUsage"]


def test_run_cannot_exceed_hard_task_cap(tmp_path: Path) -> None:
    budget = Budget(max_tasks=2)
    runner = BudgetFakeRunner()
    orchestrator, store = _orchestrator(tmp_path, runner, budget)
    _enqueue(store, count=5)

    reports = orchestrator.run(max_tasks=100, propose=False)

    assert runner.calls.count("developer") == 2
    completed = [report for report in reports if report.get("status") == "completed"]
    assert len(completed) == 2
    assert reports[-1]["status"] == "stopped"
    assert reports[-1]["budget_reason"] == MAX_TASKS
    assert reports[-1]["requested"] == 100
    assert len(store.list_tasks(READY)) == 3


def test_wall_clock_budget_stops_before_the_next_task(tmp_path: Path) -> None:
    now = [0.0]
    tracker = BudgetTracker(
        Budget(max_tasks=5, max_run_seconds=10.0),
        clock=lambda: now[0],
    )
    runner = BudgetFakeRunner()
    orchestrator, store = _orchestrator(tmp_path, runner, tracker.budget)
    _enqueue(store, count=2)

    now[0] = 10.5
    reports = orchestrator.run(propose=False, tracker=tracker)

    assert runner.calls == []
    assert len(reports) == 1
    assert reports[0]["status"] == "stopped"
    assert reports[0]["reason"] == "BUDGET"
    assert reports[0]["budget_reason"] == WALL_CLOCK
    assert store.list_tasks(READY)[0].attempts == 0


def test_token_and_cost_are_accounted_but_do_not_stop(tmp_path: Path) -> None:
    budget = Budget(max_tokens=100, max_cost_usd=0.5)
    runner = BudgetFakeRunner(tokens=150, cost=1.25)
    orchestrator, store = _orchestrator(tmp_path, runner, budget)
    _enqueue(store)

    reports = orchestrator.run(propose=False)

    assert runner.calls == ["developer", "qa", "reviewer"]
    assert reports[0]["status"] == "completed"
    task = store.get("AUTONOMY-BUDGET-0")
    assert task is not None
    assert task.status == "COMPLETED"
    assert task.usage["total_tokens"] > 100
    assert task.usage["cost_usd"] > 0.5


def test_usage_is_persisted_on_task_and_run_records(tmp_path: Path) -> None:
    budget = Budget(max_tokens=10_000_000, max_cost_usd=100.0)
    runner = BudgetFakeRunner(tokens=10, cost=0.01)
    orchestrator, store = _orchestrator(tmp_path, runner, budget)
    _enqueue(store)

    reports = orchestrator.run(propose=False)

    assert reports[0]["status"] == "completed"
    assert reports[0]["usage"]["total_tokens"] == 30
    task = store.get("AUTONOMY-BUDGET-0")
    assert task is not None
    assert task.usage["total_tokens"] == 30
    assert task.usage["cost_usd"] == pytest.approx(0.03)
    state = store.snapshot()
    assert state["usage"]["total_tokens"] == 30
    runs = state["runs"]
    assert runs[-1]["usage"]["total_tokens"] == 30
    assert runs[-1]["usage"]["cost_usd"] == pytest.approx(0.03)


def test_architect_usage_is_persisted_without_token_stop(tmp_path: Path) -> None:
    budget = Budget(max_tokens=100)
    runner = BudgetFakeRunner(tokens=150)
    orchestrator, store = _orchestrator(tmp_path, runner, budget)

    report = orchestrator.run_once(propose=True)

    assert runner.calls == ["architect"]
    assert report["status"] == "idle"
    assert store.snapshot()["usage"]["total_tokens"] == 150
