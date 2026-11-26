"""Isolated-worktree lifecycle, merge gate and recovery integration tests.

These tests use a real local git repository in ``tmp_path`` and a fake model
runner. They never touch Docker, the network or the project database.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import autonomy.orchestrator as orchestrator
import pytest
from autonomy.orchestrator import Orchestrator
from autonomy.runner import RunResult
from autonomy.state import BLOCKED, COMPLETED, QA, READY, StateStore, Task

# The control plane itself drives git; these tests exercise it with a real
# local repository. Test images that do not ship git (CI app image) skip them
# instead of failing, while hosts running the orchestrator execute them.
pytestmark = pytest.mark.skipif(
    shutil.which("git") is None,
    reason="git is required to exercise isolated worktree lifecycle",
)

TASK_ID = "AUTONOMY-WT-001"
CHANGE = "notes/change.txt"


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(  # noqa: S603 - fixed argv, test-only repository
        ["git", *args],  # noqa: S607 - git is resolved from PATH by the test host
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.fixture
def git_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "symbolic-ref", "HEAD", "refs/heads/main")
    _git(root, "config", "user.name", "Autonomy Test")
    _git(root, "config", "user.email", "autonomy@test.invalid")
    (root / "README.md").write_text("base\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-q", "-m", "base")

    worktrees = tmp_path / "worktrees"
    worktrees.mkdir()
    monkeypatch.setattr(orchestrator, "ROOT", root)
    monkeypatch.setattr(orchestrator, "WORKTREE_ROOT", worktrees)
    return root, worktrees, tmp_path / "state"


def _task() -> Task:
    return Task(
        id=TASK_ID,
        title="Worktree lifecycle",
        priority="Major",
        acceptance=["lifecycle covered"],
    )


def _store(state_dir: Path) -> StateStore:
    store = StateStore(state_dir)
    store.enqueue([_task()])
    return store


def _orchestrator(runner: FakeRunner, store: StateStore) -> Orchestrator:
    """Lifecycle tests use a disposable repo; product checks are covered
    separately by the trusted-check runner and by CI integration."""
    return Orchestrator(
        runner,
        store,
        worktrees=True,
        checks_runner=lambda _: ("lifecycle test checks stubbed", []),
    )


class FakeRunner:
    """Writes a candidate file and lets the test perturb main before review."""

    def __init__(
        self,
        *,
        verdict: str = "accept",
        before_verdict: Callable[[], None] | None = None,
        review_result: str | None = None,
    ) -> None:
        self.verdict = verdict
        self.before_verdict = before_verdict
        self.review_result = review_result
        self.calls: list[str] = []
        self.reviewed_head: str | None = None
        self.developer_cwd: Path | None = None
        self.qa_cwd: Path | None = None
        self.qa_head: str | None = None
        self.qa_status: str | None = None
        self.architect_cwd: Path | None = None

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

    def architect(self, prompt: str, cwd: Path | None = None, **_: object) -> RunResult:
        del prompt
        # Assert the cleanup precondition while the worktree still exists.
        assert cwd is not None
        assert cwd.is_dir()
        assert (cwd / ".git").is_file()
        self.architect_cwd = cwd
        return self._result("architect", '{"tasks": []}', "deepseek-v4-pro")

    def developer(self, prompt: str, cwd: Path | None = None, **_: object) -> RunResult:
        assert cwd is not None
        self.developer_cwd = cwd
        target = cwd / CHANGE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("candidate\n", encoding="utf-8")
        return self._result(
            "developer",
            json.dumps(
                {
                    "status": "done",
                    "files": [CHANGE],
                    "self_check": {
                        "spec_reviewed": True,
                        "scope_reviewed": True,
                        "tests_run": ["targeted"],
                        "localization_reviewed": True,
                        "known_limits": [],
                    },
                }
            ),
            "deepseek-flash[1m]",
        )

    def qa(self, prompt: str, cwd: Path | None = None, **_: object) -> RunResult:
        del prompt
        assert cwd is not None
        self.qa_cwd = cwd
        self.qa_head = _git(cwd, "rev-parse", "HEAD")
        self.qa_status = _git(cwd, "status", "--porcelain")
        return self._result("qa", '{"status":"pass"}', "deepseek-flash")

    def reviewer(self, prompt: str, cwd: Path | None = None, **_: object) -> RunResult:
        del prompt
        assert cwd is not None
        self.reviewed_head = _git(cwd, "rev-parse", "HEAD")
        if self.before_verdict is not None:
            self.before_verdict()
        return self._result(
            "reviewer",
            self.review_result
            if self.review_result is not None
            else json.dumps({"verdict": self.verdict, "findings": []}),
            "deepseek-v4-pro",
        )


def test_failed_trusted_checks_block_before_qa_and_clean_worktrees(
    git_repo: tuple[Path, Path, Path],
) -> None:
    root, worktrees, state_dir = git_repo
    base = _git(root, "rev-parse", "HEAD")
    store = _store(state_dir)
    runner = FakeRunner()

    report = Orchestrator(
        runner,
        store,
        worktrees=True,
        checks_runner=lambda _: ("pytest failed", ["pytest"]),
    ).run_once(propose=False)

    assert report["status"] == "retry", report
    assert report["checks"] == ["pytest"]
    assert runner.calls == ["developer"]
    assert _git(root, "rev-parse", "HEAD") == base
    assert store.get(TASK_ID).status == READY  # type: ignore[union-attr]
    assert store.get(TASK_ID).worktree is None  # type: ignore[union-attr]
    assert not any(worktrees.iterdir())


def test_worktree_accept_commits_candidate_and_fast_forwards(
    git_repo: tuple[Path, Path, Path],
) -> None:
    root, worktrees, state_dir = git_repo
    base = _git(root, "rev-parse", "HEAD")
    store = _store(state_dir)
    runner = FakeRunner()

    report = _orchestrator(runner, store).run_once(propose=False)

    assert report["status"] == "completed", report
    candidate = report["candidate"]
    assert candidate and candidate != base
    assert runner.reviewed_head == candidate
    # QA ran on the exact candidate SHA in a separate clean worktree.
    assert runner.qa_head == candidate
    assert runner.qa_status == ""
    assert runner.qa_cwd is not None and runner.qa_cwd != runner.developer_cwd
    # The candidate was really committed in the isolated worktree and merged
    # into main as a single fast-forward commit.
    assert _git(root, "rev-parse", "HEAD") == candidate
    assert _git(root, "rev-list", "--count", f"{base}..{candidate}") == "1"
    assert _git(root, "show", "--format=", "--name-only", candidate).splitlines() == [CHANGE]
    assert (root / CHANGE).read_text(encoding="utf-8") == "candidate\n"
    assert store.get(TASK_ID).status == COMPLETED  # type: ignore[union-attr]
    assert not any(worktrees.iterdir())


def test_worktree_reject_discards_candidate_and_keeps_main_unchanged(
    git_repo: tuple[Path, Path, Path],
) -> None:
    root, worktrees, state_dir = git_repo
    base = _git(root, "rev-parse", "HEAD")
    store = _store(state_dir)
    runner = FakeRunner(verdict="reject")

    report = _orchestrator(runner, store).run_once(propose=False)

    assert report["status"] == "retry", report
    assert runner.reviewed_head is not None
    assert runner.reviewed_head != base
    # The candidate exists as an object, but main never moved to it.
    assert _git(root, "cat-file", "-t", runner.reviewed_head) == "commit"
    assert _git(root, "rev-parse", "HEAD") == base
    assert _git(root, "status", "--porcelain", "--untracked-files=no") == ""
    assert not (root / CHANGE).exists()
    assert store.get(TASK_ID).status == READY  # type: ignore[union-attr]
    assert store.get(TASK_ID).worktree is None  # type: ignore[union-attr]
    assert not any(worktrees.iterdir())


def test_malformed_reviewer_json_never_merges(
    git_repo: tuple[Path, Path, Path],
) -> None:
    root, worktrees, state_dir = git_repo
    base = _git(root, "rev-parse", "HEAD")
    store = _store(state_dir)
    runner = FakeRunner(review_result='{"verdict":"accept","findings": [')

    report = _orchestrator(runner, store).run_once(propose=False)

    assert report["status"] == "retry", report
    assert report["review"]["verdict"] == "reject"
    assert _git(root, "rev-parse", "HEAD") == base
    assert not (root / CHANGE).exists()
    assert not any(worktrees.iterdir())


def test_merge_base_drift_blocks_with_reason_and_removes_worktree(
    git_repo: tuple[Path, Path, Path],
) -> None:
    root, worktrees, state_dir = git_repo
    store = _store(state_dir)
    observed: dict[str, str] = {}

    def move_main() -> None:
        (root / "drift.txt").write_text("drift\n", encoding="utf-8")
        _git(root, "add", "drift.txt")
        _git(root, "commit", "-q", "-m", "main moved")
        observed["head"] = _git(root, "rev-parse", "HEAD")

    report = _orchestrator(FakeRunner(before_verdict=move_main), store).run_once(propose=False)

    assert report["status"] == "blocked", report
    assert "merge base drift" in report["reason"]
    task = store.get(TASK_ID)
    assert task is not None
    assert task.status == BLOCKED
    assert "merge base drift" in (task.blocked_reason or "")
    assert task.last_error == task.blocked_reason
    assert task.worktree is None
    assert _git(root, "rev-parse", "HEAD") == observed["head"]
    assert not any(worktrees.iterdir())


def test_dirty_main_blocks_with_reason_and_removes_worktree(
    git_repo: tuple[Path, Path, Path],
) -> None:
    root, worktrees, state_dir = git_repo
    store = _store(state_dir)

    def dirty_main() -> None:
        (root / "README.md").write_text("dirty\n", encoding="utf-8")

    report = _orchestrator(FakeRunner(before_verdict=dirty_main), store).run_once(propose=False)

    assert report["status"] == "blocked", report
    assert "dirty" in report["reason"]
    task = store.get(TASK_ID)
    assert task is not None
    assert task.status == BLOCKED
    assert "dirty" in (task.blocked_reason or "")
    assert task.worktree is None
    # The candidate is never merged while main has local modifications.
    assert _git(root, "diff", "--name-only") == "README.md"
    assert not any(worktrees.iterdir())


def test_merge_failure_blocks_with_reason_and_removes_worktree(
    git_repo: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, worktrees, state_dir = git_repo
    base = _git(root, "rev-parse", "HEAD")
    store = _store(state_dir)
    real_git = orchestrator._git

    def failing_git(
        args: list[str], *, cwd: Path | None = None, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["merge", "--ff-only"]:
            return subprocess.CompletedProcess(["git", *args], 1, "", "fatal: cannot fast-forward")
        return real_git(args, cwd=cwd, check=check)

    monkeypatch.setattr(orchestrator, "_git", failing_git)

    report = _orchestrator(FakeRunner(), store).run_once(propose=False)

    assert report["status"] == "blocked", report
    assert "fast-forward merge failed" in report["reason"]
    assert "cannot fast-forward" in report["reason"]
    task = store.get(TASK_ID)
    assert task is not None
    assert task.status == BLOCKED
    assert "fast-forward merge failed" in (task.blocked_reason or "")
    assert task.worktree is None
    assert _git(root, "rev-parse", "HEAD") == base
    assert not any(worktrees.iterdir())


def test_recovery_removes_orphan_worktrees_and_resumes_without_duplicates(
    git_repo: tuple[Path, Path, Path],
) -> None:
    root, worktrees, state_dir = git_repo
    store = _store(state_dir)
    claimed = store.claim_next()
    assert claimed is not None
    interrupted, base = orchestrator._create_worktree(claimed)
    store.set_worktree(TASK_ID, str(interrupted), base)
    store.transition(TASK_ID, QA)

    # An orphan directory that git no longer tracks must also be removed.
    leftover = worktrees / "AUTONOMY-LEFTOVER-deadbeef" / "ba"
    leftover.mkdir(parents=True)
    (leftover / "tmp.txt").write_text("leftover", encoding="utf-8")

    runner = FakeRunner()
    report = _orchestrator(runner, store).run_once(propose=False)

    assert report["status"] == "completed", report
    assert runner.calls == ["developer", "qa", "reviewer"]
    assert not interrupted.exists()
    assert not leftover.parent.exists()
    assert not any(worktrees.iterdir())

    state = store.snapshot()
    assert list(state["tasks"]) == [TASK_ID]
    runs = [run for run in state["runs"] if run["task_id"] == TASK_ID]
    assert sum(1 for run in runs if run["status"] == "completed") == 1

    # A second iteration must be idle: recovery did not leave a duplicate
    # READY/RUNNING copy of the task behind.
    again = _orchestrator(runner, store).run_once(propose=False)
    assert again["status"] == "idle"
    assert runner.calls.count("developer") == 1
    assert store.get(TASK_ID).status == COMPLETED  # type: ignore[union-attr]
    assert _git(root, "rev-parse", "HEAD") == report["commit"]


def test_propose_runs_architect_in_disposable_worktree_and_cleans_up(
    git_repo: tuple[Path, Path, Path],
) -> None:
    root, worktrees, state_dir = git_repo
    store = StateStore(state_dir)
    runner = FakeRunner()

    added = _orchestrator(runner, store).propose()

    assert added == []
    # The Architect callback asserted cwd/.git while the worktree existed.
    assert runner.architect_cwd is not None
    assert not runner.architect_cwd.exists()
    assert not any(worktrees.iterdir())
    assert _git(root, "status", "--porcelain", "--untracked-files=no") == ""
