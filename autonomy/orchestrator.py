"""Task queue → Pro Architect → Flash Developer → Flash QA → Pro Review."""

# ruff: noqa: T201, S607, S603

from __future__ import annotations

import argparse
import fcntl
import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from autonomy.runner import ClaudeRunner, RunResult
from autonomy.state import (
    COMPLETED,
    QA,
    READY,
    REVIEW,
    StateStore,
    Task,
)

ROOT = Path(__file__).resolve().parents[1]
STATE_ROOT = Path(__file__).resolve().parents[1] / ".autonomy"
STOP_FILE = STATE_ROOT / "STOP"
EVIDENCE_ROOT = STATE_ROOT / "evidence"
RUN_LOCK = STATE_ROOT / "run.lock"
WORKTREE_ROOT = STATE_ROOT / "worktrees"


def _parse_json(value: str) -> dict[str, Any]:
    value = value.strip()
    if value.startswith("```"):
        value = value.strip("`")
        if value.startswith("json"):
            value = value[4:]
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        start = value.find("{")
        end = value.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(value[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("model result is not a JSON object")
    return parsed


PROTECTED_PARTS = (
    ".env",
    "certs/",
    "creds/",
    "technical_specification/",
    "CLAUDE.md",
    ".git/",
    ".claude/settings",
    ".claude/hooks",
    "docs/spec/",
    "reports/",
    "infra/nginx/staging.conf",
)


def _git(
    args: list[str],
    *,
    cwd: Path = ROOT,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=False)
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr[-800:]}")
    return result


def _head(cwd: Path = ROOT) -> str:
    return _git(["rev-parse", "HEAD"], cwd=cwd).stdout.strip()


def _assert_main_clean() -> None:
    branch = _git(["symbolic-ref", "--short", "HEAD"]).stdout.strip()
    if branch != "main":
        raise RuntimeError(f"orchestrator must run on main, got {branch or 'detached HEAD'}")
    status = _git(["status", "--porcelain", "--untracked-files=no"]).stdout.strip()
    if status:
        raise RuntimeError(f"main worktree is dirty: {status[:800]}")


def _create_worktree(task: Task) -> tuple[Path, str]:
    _assert_main_clean()
    base = _head()
    path = WORKTREE_ROOT / f"{task.id}-{uuid.uuid4().hex[:12]}" / "ba"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep basename "ba": project hooks derive the sibling repo from ROOT.name
    # and would otherwise treat the worktree as the sibling repository.
    _git(["worktree", "add", "--detach", str(path), base])
    return path, base


def _remove_worktree(path: Path) -> None:
    if path.exists():
        _git(["worktree", "remove", "--force", str(path)], check=False)
    _git(["worktree", "prune"], check=False)


def _cleanup_worktrees() -> None:
    result = _git(["worktree", "list", "--porcelain"], check=False)
    paths = [
        Path(line.removeprefix("worktree "))
        for line in result.stdout.splitlines()
        if line.startswith("worktree ")
    ]
    for path in paths:
        if path.is_relative_to(WORKTREE_ROOT):
            _remove_worktree(path)


def _safe_file(name: str, root: Path | None = None) -> Path:
    root = root or ROOT
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise RuntimeError(f"developer reported an unsafe or missing path: {name}")
    normalized = path.relative_to(root.resolve()).as_posix()
    if normalized == ".env" or normalized.startswith(PROTECTED_PARTS):
        raise RuntimeError(f"developer reported a protected path: {name}")
    return path


def _developer_files(developer: RunResult, root: Path = ROOT) -> list[str]:
    try:
        parsed = _parse_json(developer.result)
    except ValueError, json.JSONDecodeError:
        return []
    raw = parsed.get("files")
    if not isinstance(raw, list):
        return []
    files: list[str] = []
    for value in raw:
        name = str(value).strip()
        if not name or name.startswith("/") or ".." in name.split("/"):
            continue
        _safe_file(name, root)
        files.append(name)
    if not files:
        raise RuntimeError("developer reported no safe files; refusing an empty change")
    return files


def _stage_task(files: list[str], root: Path = ROOT) -> None:
    add = _git(["add", "--", *files], cwd=root, check=False)
    if add.returncode != 0:
        raise RuntimeError(f"git add failed: {add.stderr[-500:]}")
    staged = _git(["diff", "--cached", "--name-only"], cwd=root)
    unexpected = set(staged.stdout.splitlines()) - set(files)
    if unexpected:
        raise RuntimeError(f"unexpected staged paths: {sorted(unexpected)}")


def _unstage(files: list[str], root: Path = ROOT) -> None:
    _git(["restore", "--staged", "--", *files], cwd=root, check=False)


def _commit_staged(task: Task, files: list[str], root: Path = ROOT) -> str:
    subject = f"autonomy({task.id}): {task.title}"
    body = "Co-Authored-By: Claude Code <noreply@anthropic.com>"
    commit = _git(["commit", "-m", subject, "-m", body], cwd=root, check=False)
    if commit.returncode != 0:
        raise RuntimeError(f"git commit failed: {commit.stderr[-500:]}")
    return commit.stdout.strip().splitlines()[0] if commit.stdout.strip() else "committed"


def _commit_candidate(task: Task, files: list[str], worktree: Path) -> str:
    _stage_task(files, worktree)
    _commit_staged(task, files, worktree)
    return _head(worktree)


def _merge_candidate(candidate: str, base: str) -> str:
    _assert_main_clean()
    if _head() != base:
        raise RuntimeError("main moved while the task was running; refusing to merge")
    _git(["merge", "--ff-only", candidate])
    return _head()


def _git_diff(files: list[str], *, base: str, candidate: str | None, root: Path) -> str:
    try:
        if candidate:
            result = _git(["diff", base, candidate, "--", *files], cwd=root, check=False)
            return result.stdout[-40000:]
        result = _git(["diff", "--", *files], cwd=root, check=False)
        return result.stdout[-40000:]
    except FileNotFoundError:
        return "[git unavailable in this runtime]"


def _architect_prompt(store: StateStore) -> str:
    state = store.snapshot()
    active = [
        {"id": task_id, "status": value["status"], "title": value["title"]}
        for task_id, value in state["tasks"].items()
    ]
    return (
        "Inspect the repository and determine the next bounded tasks for the "
        "autonomy control plane. Do not propose game/App F features; the owner "
        "freeze is active. Do not repeat any item below. Return the strict JSON "
        "schema from your agent instructions. Current queue: "
        + json.dumps(active, ensure_ascii=False)
    )


def _developer_prompt(task: Task) -> str:
    return (
        f"Task ID: {task.id}\nTitle: {task.title}\n"
        f"Acceptance criteria:\n- " + "\n- ".join(task.acceptance) + "\n"
        "Implement exactly this task in the isolated worktree. Do not change game "
        "features. Run relevant checks and return the strict JSON report from your "
        "instructions."
    )


def _qa_prompt(task: Task, developer: RunResult) -> str:
    return (
        f"Task ID: {task.id}\nTitle: {task.title}\n"
        f"Acceptance criteria:\n- " + "\n- ".join(task.acceptance) + "\n"
        f"Developer report:\n{developer.result[:8000]}\n"
        "Run the real checks in this worktree and return the strict JSON QA report."
    )


def _reviewer_prompt(
    task: Task,
    developer: RunResult,
    qa: RunResult,
    diff: str,
) -> str:
    return (
        f"Task ID: {task.id}\nTitle: {task.title}\n"
        f"Acceptance criteria:\n- " + "\n- ".join(task.acceptance) + "\n"
        f"Developer report:\n{developer.result[:8000]}\n"
        f"QA report:\n{qa.result[:8000]}\n"
        f"Candidate diff (isolated worktree; main is unchanged):\n{diff}\n"
        "Independently review the candidate commit and evidence. Main is merged "
        "only if you accept. Reject if the diff is not the reported deliverable "
        "or if it is unsafe. Return the strict JSON verdict from your instructions."
    )


class Orchestrator:
    def __init__(
        self,
        runner: ClaudeRunner,
        store: StateStore | None = None,
        *,
        commit: bool = True,
        worktrees: bool = True,
    ) -> None:
        self.runner = runner
        self.store = store or StateStore(STATE_ROOT)
        self.commit = commit
        self.worktrees = worktrees

    def propose(self) -> list[Task]:
        result = self.runner.architect(_architect_prompt(self.store))
        parsed = _parse_json(result.result)
        raw_tasks = parsed.get("tasks", [])
        if raw_tasks is None:
            raw_tasks = []
        if not isinstance(raw_tasks, list):
            raise ValueError("architect tasks must be a list")
        proposed: list[Task] = []
        for item in raw_tasks:
            if not isinstance(item, dict):
                continue
            task_id = str(item.get("id", "")).strip()
            if not task_id.startswith("AUTONOMY-"):
                continue
            acceptance = [str(value) for value in item.get("acceptance", []) if str(value).strip()]
            if not acceptance:
                continue
            proposed.append(
                Task(
                    id=task_id,
                    title=str(item.get("title") or task_id),
                    priority=str(item.get("priority") or "Minor"),
                    acceptance=acceptance,
                    dependencies=[str(value) for value in item.get("dependencies", [])],
                )
            )
        added = self.store.enqueue(proposed)
        self._write_event(
            {
                "event": "architect",
                "session_id": result.session_id,
                "evidence": result.evidence_path,
                "proposed": [task.id for task in proposed],
                "added": [task.id for task in added],
            }
        )
        return added

    def run_once(self, *, propose: bool = True) -> dict[str, Any]:
        self.store.recover_running()
        self._cleanup_orphan_worktrees()
        task = self.store.claim_next()
        report: dict[str, Any]
        if task is None and propose:
            try:
                self.propose()
            except Exception as exc:  # noqa: BLE001 - architect failure is a run error
                report = {"status": "blocked", "reason": "architect failed", "error": str(exc)}
                self._write_event(report)
                return report
            task = self.store.claim_next()
        if task is None:
            report = {"status": "idle", "reason": "no READY tasks", "completed": []}
            self._write_event(report)
            return report

        report = self._run_isolated(task) if self.worktrees else self._run_inplace(task)
        self._write_event(report)
        return report

    def _cleanup_orphan_worktrees(self) -> None:
        if not self.worktrees:
            return
        _cleanup_worktrees()

    def _run_isolated(self, task: Task) -> dict[str, Any]:
        worktree: Path | None = None
        base: str | None = None
        try:
            worktree, base = _create_worktree(task)
            self.store.set_worktree(task.id, str(worktree), base)
            developer = self.runner.developer(_developer_prompt(task), cwd=worktree)
            self.store.transition(
                task.id,
                QA,
                session_id=developer.session_id,
                model=developer.model,
                evidence=developer.evidence_path,
            )
            qa = self.runner.qa(_qa_prompt(task, developer), cwd=worktree)
            self.store.transition(
                task.id, REVIEW, session_id=qa.session_id, model=qa.model, evidence=qa.evidence_path
            )
            files = _developer_files(developer, worktree)
            candidate = _commit_candidate(task, files, worktree)
            self.store.set_candidate(task.id, candidate)
            review = self.runner.reviewer(
                _reviewer_prompt(
                    task,
                    developer,
                    qa,
                    _git_diff(files, base=base, candidate=candidate, root=worktree),
                ),
                cwd=worktree,
            )
            verdict = _parse_json(review.result)
            if verdict.get("verdict") != "accept":
                _remove_worktree(worktree)
                worktree = None
                retried = self.store.retry(task.id, json.dumps(verdict, ensure_ascii=False)[:4000])
                return {
                    "status": "retry" if retried and retried.status == READY else "blocked",
                    "task": task.id,
                    "review": verdict,
                }
            merged = _merge_candidate(candidate, base)
            completed = self.store.transition(
                task.id,
                COMPLETED,
                session_id=review.session_id,
                model=review.model,
                evidence=review.evidence_path,
            )
            _remove_worktree(worktree)
            worktree = None
            return {
                "status": "completed",
                "task": task.id,
                "commit": merged,
                "candidate": candidate,
                "evidence": completed.evidence if completed else [],
                "review": verdict,
            }
        except Exception as exc:  # noqa: BLE001 - task boundary is fail-closed
            if worktree is not None:
                _remove_worktree(worktree)
            retried = self.store.retry(task.id, f"{type(exc).__name__}: {exc}")
            return {
                "status": "retry" if retried and retried.status == READY else "blocked",
                "task": task.id,
                "error": f"{type(exc).__name__}: {exc}",
            }

    def _run_inplace(self, task: Task) -> dict[str, Any]:
        files: list[str] = []
        staged = False
        try:
            developer = self.runner.developer(_developer_prompt(task))
            self.store.transition(
                task.id,
                QA,
                session_id=developer.session_id,
                model=developer.model,
                evidence=developer.evidence_path,
            )
            qa = self.runner.qa(_qa_prompt(task, developer))
            self.store.transition(
                task.id, REVIEW, session_id=qa.session_id, model=qa.model, evidence=qa.evidence_path
            )
            files = _developer_files(developer)
            base = _head() if self.commit else "no-git-test"
            candidate: str | None = None
            if self.commit:
                try:
                    _stage_task(files)
                except Exception:
                    _unstage(files)
                    raise
                staged = True
                _commit_staged(task, files)
                candidate = _head()
            review = self.runner.reviewer(
                _reviewer_prompt(
                    task, developer, qa, _git_diff(files, base=base, candidate=candidate, root=ROOT)
                )
            )
            verdict = _parse_json(review.result)
            if verdict.get("verdict") != "accept":
                if staged:
                    _unstage(files)
                retried = self.store.retry(task.id, json.dumps(verdict, ensure_ascii=False)[:4000])
                return {
                    "status": "retry" if retried and retried.status == READY else "blocked",
                    "task": task.id,
                    "review": verdict,
                }
            if staged:
                staged = False
            completed = self.store.transition(
                task.id,
                COMPLETED,
                session_id=review.session_id,
                model=review.model,
                evidence=review.evidence_path,
            )
            return {
                "status": "completed",
                "task": task.id,
                "commit": candidate or "not committed (test)",
                "evidence": completed.evidence if completed else [],
                "review": verdict,
            }
        except Exception as exc:  # noqa: BLE001 - task boundary is fail-closed
            if staged:
                _unstage(files)
            retried = self.store.retry(task.id, f"{type(exc).__name__}: {exc}")
            return {
                "status": "retry" if retried and retried.status == READY else "blocked",
                "task": task.id,
                "error": f"{type(exc).__name__}: {exc}",
            }

    def run(self, max_tasks: int, *, propose: bool = True) -> list[dict[str, Any]]:
        reports: list[dict[str, Any]] = []
        for _ in range(max_tasks):
            if STOP_FILE.exists():
                reports.append({"status": "stopped", "reason": "STOP file"})
                break
            report = self.run_once(propose=propose)
            reports.append(report)
            if report["status"] in {"idle", "stopped"}:
                break
        return reports

    def _write_event(self, value: dict[str, Any]) -> None:
        events = self.store.root / "events.jsonl"
        events.parent.mkdir(parents=True, exist_ok=True)
        with events.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--max-tasks", type=int, default=1)
    run.add_argument("--no-propose", action="store_true")
    sub.add_parser("status")
    sub.add_parser("propose")
    enqueue = sub.add_parser("enqueue")
    enqueue.add_argument("--id", required=True)
    enqueue.add_argument("--title", required=True)
    enqueue.add_argument("--priority", default="Minor")
    enqueue.add_argument("--acceptance", action="append", default=[])
    enqueue.add_argument("--dependency", action="append", default=[])
    recover = sub.add_parser("recover")
    recover.add_argument("--task-id")
    args = parser.parse_args(argv)

    store = StateStore(STATE_ROOT)
    if args.command == "status":
        print(json.dumps(store.snapshot(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "recover":
        with RUN_LOCK.open("a+") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print(json.dumps({"status": "locked", "reason": "a run is active"}))
                return 3
            recovered = store.recover_running()
            _cleanup_worktrees()
        print(json.dumps([task.to_dict() for task in recovered], ensure_ascii=False, indent=2))
        return 0
    orchestrator = Orchestrator(ClaudeRunner(), store)
    if args.command == "enqueue":
        if not args.acceptance:
            parser.error("--acceptance is required")
        task = Task(
            id=args.id,
            title=args.title,
            priority=args.priority,
            acceptance=args.acceptance,
            dependencies=args.dependency,
        )
        added = store.enqueue([task])
        print(json.dumps([item.to_dict() for item in added], ensure_ascii=False, indent=2))
        return 0
    if args.command == "propose":
        proposed = orchestrator.propose()
        print(json.dumps([task.to_dict() for task in proposed], ensure_ascii=False, indent=2))
        return 0
    with RUN_LOCK.open("a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({"status": "locked", "reason": "another orchestrator is running"}))
            return 3
        reports = orchestrator.run(args.max_tasks, propose=not args.no_propose)
    print(json.dumps(reports, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if all(item["status"] != "blocked" for item in reports) else 2


if __name__ == "__main__":
    sys.exit(main())
