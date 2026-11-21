"""Task queue → Pro Architect → Flash Developer → Flash QA → Pro Review."""

# ruff: noqa: T201, S607, S603

from __future__ import annotations

import argparse
import fcntl
import json
import subprocess
import sys
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


def _safe_file(name: str) -> Path:
    path = (ROOT / name).resolve()
    if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
        raise RuntimeError(f"developer reported an unsafe or missing path: {name}")
    normalized = path.relative_to(ROOT.resolve()).as_posix()
    if normalized == ".env" or normalized.startswith(PROTECTED_PARTS):
        raise RuntimeError(f"developer reported a protected path: {name}")
    return path


def _git_diff(files: list[str], *, staged: bool) -> str:
    try:
        if staged:
            result = subprocess.run(
                ["git", "diff", "--cached", "--", *files],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            return result.stdout[-40000:]
        result = subprocess.run(
            ["git", "diff", "--", *files],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "--", *files],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return "[git unavailable in this runtime]"
    chunks = [result.stdout]
    for name in untracked.stdout.splitlines():
        if not name.strip():
            continue
        path = ROOT / name
        if path.is_file():
            chunks.append(f"\n--- untracked: {name}\n{path.read_text(errors='replace')[:20000]}")
    return "\n".join(chunks)[-40000:]


def _developer_files(developer: RunResult) -> list[str]:
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
        _safe_file(name)
        files.append(name)
    if not files:
        raise RuntimeError("developer reported no safe files; refusing an empty change")
    return files


def _stage_task(files: list[str]) -> None:
    add = subprocess.run(["git", "add", "--", *files], cwd=ROOT, capture_output=True, text=True)
    if add.returncode != 0:
        raise RuntimeError(f"git add failed: {add.stderr[-500:]}")
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"], cwd=ROOT, capture_output=True, text=True
    )
    if staged.returncode != 0:
        raise RuntimeError(f"git diff --cached failed: {staged.stderr[-500:]}")
    unexpected = set(staged.stdout.splitlines()) - set(files)
    if unexpected:
        raise RuntimeError(f"unexpected staged paths: {sorted(unexpected)}")


def _unstage(files: list[str]) -> None:
    subprocess.run(
        ["git", "restore", "--staged", "--", *files],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def _commit_staged(task: Task, files: list[str]) -> str:
    subject = f"autonomy({task.id}): {task.title}"
    body = "Co-Authored-By: Claude Code <noreply@anthropic.com>"
    commit = subprocess.run(
        ["git", "commit", "--only", "-m", subject, "-m", body, "--", *files],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if commit.returncode != 0:
        raise RuntimeError(f"git commit failed: {commit.stderr[-500:]}")
    return commit.stdout.strip().splitlines()[0] if commit.stdout.strip() else "committed"


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
        "Implement exactly this task in the repository. Do not change game features. "
        "Run relevant checks and return the strict JSON report from your instructions."
    )


def _qa_prompt(task: Task, developer: RunResult) -> str:
    return (
        f"Task ID: {task.id}\nTitle: {task.title}\n"
        f"Acceptance criteria:\n- " + "\n- ".join(task.acceptance) + "\n"
        f"Developer report:\n{developer.result[:8000]}\n"
        "Run the real checks and return the strict JSON QA report."
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
        f"Actual git diff (staged candidate; the orchestrator commits only after "
        f"your accept):\n{diff}\n"
        "Independently review the staged candidate and evidence. Do not reject "
        "solely because the commit is created after your verdict; reject if the "
        "diff is not the reported deliverable or if it is unsafe. Return the strict "
        "JSON verdict from your instructions."
    )


class Orchestrator:
    def __init__(
        self,
        runner: ClaudeRunner,
        store: StateStore | None = None,
        *,
        commit: bool = True,
    ) -> None:
        self.runner = runner
        self.store = store or StateStore(STATE_ROOT)
        self.commit = commit

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
            if self.commit:
                _stage_task(files)
                staged = True
            review = self.runner.reviewer(
                _reviewer_prompt(task, developer, qa, _git_diff(files, staged=staged))
            )
            verdict = _parse_json(review.result)
            if verdict.get("verdict") != "accept":
                if staged:
                    _unstage(files)
                    staged = False
                retried = self.store.retry(task.id, json.dumps(verdict, ensure_ascii=False)[:4000])
                report = {
                    "status": "retry" if retried and retried.status == READY else "blocked",
                    "task": task.id,
                    "review": verdict,
                }
            else:
                commit = _commit_staged(task, files) if self.commit else "not committed (test)"
                staged = False
                completed = self.store.transition(
                    task.id,
                    COMPLETED,
                    session_id=review.session_id,
                    model=review.model,
                    evidence=review.evidence_path,
                )
                report = {
                    "status": "completed",
                    "task": task.id,
                    "commit": commit,
                    "evidence": completed.evidence if completed else [],
                    "review": verdict,
                }
        except Exception as exc:  # noqa: BLE001 - task boundary is fail-closed
            if staged:
                _unstage(files)
            retried = self.store.retry(task.id, f"{type(exc).__name__}: {exc}")
            report = {
                "status": "retry" if retried and retried.status == READY else "blocked",
                "task": task.id,
                "error": f"{type(exc).__name__}: {exc}",
            }
        self._write_event(report)
        return report

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
