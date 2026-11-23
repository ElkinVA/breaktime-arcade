"""Task queue → Pro Architect → Flash Developer → Flash QA → Pro Review."""

# ruff: noqa: T201, S607, S603

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from autonomy.budget import (
    MAX_TASKS,
    Budget,
    BudgetReached,
    BudgetStop,
    BudgetTracker,
)
from autonomy.metrics import compute_metrics
from autonomy.notifier import (
    FATAL_ERROR,
    RUN_BUDGET_STOP,
    RUN_STOPPED,
    TASK_BLOCKED,
    TASK_COMPLETED,
    TASK_REJECTED,
    NotificationEvent,
    Notifier,
)
from autonomy.observability import InvocationContext, reconcile_invocations
from autonomy.runner import ClaudeRunner, RunResult
from autonomy.state import (
    BLOCKED,
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
        # A truncated object can be completed by appending the missing
        # closing brace(es); accept only a complete contract object.
        if value.startswith("{"):
            for suffix in ("}", "}}", "]}", "}]}", "}}]"):
                try:
                    repaired = json.loads(value + suffix)
                except json.JSONDecodeError:
                    continue
                if isinstance(repaired, dict) and any(
                    key in repaired for key in ("verdict", "status", "tasks")
                ):
                    return repaired
        # Agents sometimes prepend prose (and the prose can contain braces,
        # e.g. Django template syntax). Try every `${` start and prefer the
        # outer contract object (verdict/status/tasks), not a nested finding.
        decoder = json.JSONDecoder()
        candidates: list[dict[str, Any]] = []
        for start in [index for index, char in enumerate(value) if char == "{"]:
            try:
                candidate, _end = decoder.raw_decode(value[start:])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                candidates.append(candidate)
        parsed = next(
            (
                candidate
                for candidate in candidates
                if any(key in candidate for key in ("verdict", "status", "tasks"))
            ),
            candidates[-1] if candidates else None,
        )
        if parsed is None:
            raise
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
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args], cwd=cwd or ROOT, text=True, capture_output=True, check=False
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr[-800:]}")
    return result


def _head(cwd: Path | None = None) -> str:
    return _git(["rev-parse", "HEAD"], cwd=cwd).stdout.strip()


class MergeGateError(RuntimeError):
    """A merge precondition is broken; retrying the task cannot fix it."""


def _assert_main_clean() -> None:
    branch = _git(["symbolic-ref", "--short", "HEAD"]).stdout.strip()
    if branch != "main":
        raise MergeGateError(f"orchestrator must run on main, got {branch or 'detached HEAD'}")
    status = _git(["status", "--porcelain", "--untracked-files=no"]).stdout.strip()
    if status:
        raise MergeGateError(f"main worktree is dirty: {status[:800]}")


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
    # Drop the now-empty per-task directory created around the worktree.
    parent = path.parent
    if parent != WORKTREE_ROOT and parent.is_relative_to(WORKTREE_ROOT) and parent.is_dir():
        with contextlib.suppress(OSError):
            parent.rmdir()


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
    _git(["worktree", "prune"], check=False)
    # Remove leftovers that git no longer tracks (e.g. an interrupted
    # `worktree add`, or a directory whose metadata was already pruned).
    if not WORKTREE_ROOT.is_dir():
        return
    for child in WORKTREE_ROOT.iterdir():
        if child.is_symlink():
            child.unlink(missing_ok=True)
        elif child.is_dir():
            shutil.rmtree(child, ignore_errors=True)


def _safe_file(name: str, root: Path | None = None) -> Path:
    root = root or ROOT
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise RuntimeError(f"developer reported an unsafe path: {name}")
    # A missing path is a legitimate deletion reported by the developer; it is
    # still confined to the worktree and protected-path rules below.
    if path.exists() and not path.is_file():
        raise RuntimeError(f"developer reported a non-file path: {name}")
    normalized = path.relative_to(root.resolve()).as_posix()
    # The actual staging config is protected; its non-secret Jinja template is
    # allowed so worker/proxy timeout changes can be reviewed and committed.
    # Example env files contain no secrets and are valid documentation.
    allowed_non_secret = {
        "infra/nginx/staging.conf.j2",
        ".env.example",
        ".env.staging.example",
    }
    protected = normalized.startswith(PROTECTED_PARTS) and normalized not in allowed_non_secret
    if normalized == ".env" or protected:
        raise RuntimeError(f"developer reported a protected path: {name}")
    return path


def _qa_passed(qa: RunResult) -> bool:
    try:
        parsed = _parse_json(qa.result)
    except ValueError, json.JSONDecodeError:
        return False
    return parsed.get("status") == "pass"


def _validate_self_check(developer: RunResult) -> None:
    parsed = _parse_json(developer.result)
    check = parsed.get("self_check")
    if not isinstance(check, dict):
        raise RuntimeError("developer self_check is mandatory before QA")
    required = (
        "spec_reviewed",
        "scope_reviewed",
        "tests_run",
        "localization_reviewed",
        "known_limits",
    )
    missing = [key for key in required if key not in check]
    if missing:
        raise RuntimeError(f"developer self_check missing: {missing}")
    if check["spec_reviewed"] is not True or check["scope_reviewed"] is not True:
        raise RuntimeError("developer self_check must confirm spec and scope review")
    if not isinstance(check["tests_run"], list) or not isinstance(check["known_limits"], list):
        raise RuntimeError("developer self_check tests_run/known_limits must be lists")
    if not isinstance(check["localization_reviewed"], bool):
        raise RuntimeError("developer self_check localization_reviewed must be boolean")


def _developer_files(developer: RunResult, root: Path | None = None) -> list[str]:
    root = root or ROOT
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
    last = None
    for _attempt in range(2):
        commit = _git(["commit", "-m", subject, "-m", body], cwd=root, check=False)
        if commit.returncode == 0:
            return commit.stdout.strip().splitlines()[0] if commit.stdout.strip() else "committed"
        last = commit
        # Pre-commit hooks may auto-fix whitespace/format and leave the hook
        # run non-zero. Restage the task files once, then retry.
        _git(["add", "--", *files], cwd=root, check=False)
    raise RuntimeError(f"git commit failed: {last.stderr[-500:] if last else 'unknown'}")


def _commit_candidate(task: Task, files: list[str], worktree: Path) -> str:
    _stage_task(files, worktree)
    _commit_staged(task, files, worktree)
    return _head(worktree)


def _merge_candidate(candidate: str, base: str) -> str:
    _assert_main_clean()
    current = _head()
    if current != base:
        raise MergeGateError(
            f"merge base drift: main is at {current[:12]}, candidate was based on {base[:12]}"
        )
    result = _git(["merge", "--ff-only", candidate], check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-500:] or "git merge returned non-zero"
        raise MergeGateError(f"fast-forward merge failed: {detail}")
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
        "Inspect the repository and determine the next bounded Browser Arcade "
        "product tasks (site, catalog, accounts, CRM, game-facing features). "
        "AI HQ is frozen; propose control-plane work only for a concrete "
        "operational defect. Do not repeat any item below. Return the strict JSON "
        "schema from your agent instructions. Current queue: "
        + json.dumps(active, ensure_ascii=False)
    )


def _developer_prompt(task: Task) -> str:
    return (
        f"Task ID: {task.id}\nTitle: {task.title}\n"
        f"Acceptance criteria:\n- " + "\n- ".join(task.acceptance) + "\n"
        "Implement exactly this task in the isolated worktree. The worktree has no "
        ".env: do not run make test/check there. Use "
        "`python3 devcontrol/sandbox/run_tests.py ...` for tests and "
        "/home/elkinva/projects/ba/.venv/bin/python -m ruff/mypy for lint. Do not "
        "change game features. Complete the mandatory self-check against the ТЗ, "
        "scope, tests and localization/regressions; include its fields in the JSON. "
        + (f"Previous failure to address:\n{task.last_error[:4000]}\n" if task.last_error else "")
        + "Return the strict JSON report from your instructions."
    )


def _qa_prompt(task: Task, developer: RunResult) -> str:
    return (
        f"Task ID: {task.id}\nTitle: {task.title}\n"
        f"Acceptance criteria:\n- " + "\n- ".join(task.acceptance) + "\n"
        f"Developer report:\n{developer.result[:8000]}\n"
        "The worktree has no .env: do not run make test/check there. Run tests via "
        "`python3 devcontrol/sandbox/run_tests.py ...`; run targeted pytest with "
        "/home/elkinva/projects/ba/.venv/bin/python when the sandbox would skip "
        "git-dependent tests. Return the strict JSON QA report."
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
        budget: Budget | None = None,
        notifier: Notifier | None = None,
    ) -> None:
        self.runner = runner
        self.store = store or StateStore(STATE_ROOT)
        self.commit = commit
        self.worktrees = worktrees
        self.budget = budget or Budget.from_env()
        # Explicit injection keeps tests and library callers send-free; the
        # CLI enables the owner-configured notifier via ``Notifier.from_env``.
        self.notifier = notifier if notifier is not None else Notifier.disabled()
        self._fatal_notified: BaseException | None = None

    def _account(
        self,
        task_id: str | None,
        result: RunResult,
        tracker: BudgetTracker,
    ) -> None:
        """Persist actual model usage and add it to the run budget.

        Lifecycle events are written by the runner; this method keeps the
        existing success-only state/budget accounting unchanged.
        """
        usage = result.usage
        self.store.record_usage(task_id, usage.to_dict())
        tracker.add(usage)

    @staticmethod
    def _context(task: Task) -> InvocationContext:
        return InvocationContext(
            task_id=task.id,
            attempt_id=task.run_id,
            retry_count=max(0, task.attempts - 1),
        )

    def _reconcile(self) -> None:
        journal_root = getattr(self.runner, "journal_root", self.store.root)
        with contextlib.suppress(Exception):
            reconcile_invocations(journal_root)

    @staticmethod
    def _guard(tracker: BudgetTracker) -> None:
        """Stop at this safe boundary if a hard limit has been reached."""
        stop = tracker.stop()
        if stop is not None:
            raise BudgetReached(stop)

    def propose(self, tracker: BudgetTracker | None = None) -> list[Task]:
        tracker = tracker or BudgetTracker(self.budget)
        prompt = _architect_prompt(self.store)
        worktree: Path | None = None
        try:
            if self.worktrees:
                # The read-only Architect runs from a clean, disposable
                # worktree too: no model process executes in the main checkout.
                worktree, _base = _create_worktree(
                    Task(
                        id="AUTONOMY-ARCHITECT",
                        title="Read-only architecture planning",
                        priority="Minor",
                        acceptance=["planning runs in a disposable worktree"],
                    )
                )
                result = self.runner.architect(prompt, cwd=worktree, context=InvocationContext())
            else:
                # Test/legacy mode keeps the original prompt-only signature.
                result = self.runner.architect(prompt, context=InvocationContext())
        finally:
            if worktree is not None:
                _remove_worktree(worktree)
        self._account(None, result, tracker)
        self._guard(tracker)
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
            if not task_id.startswith(("AUTONOMY-", "ARCADE-")):
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

    def run_once(
        self, *, propose: bool = True, tracker: BudgetTracker | None = None
    ) -> dict[str, Any]:
        """Run one task boundary and emit a best-effort owner notification."""
        try:
            report = self._run_once(propose=propose, tracker=tracker)
        except Exception as exc:
            self.notify_fatal(exc)
            raise
        self.notify_report(report)
        return report

    @staticmethod
    def _text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def _review_reason(cls, review: Any) -> str | None:
        if not isinstance(review, dict):
            return None
        findings = review.get("findings")
        if isinstance(findings, list) and findings:
            return "; ".join(str(item) for item in findings[:5])
        verdict = cls._text(review.get("verdict"))
        return f"verdict: {verdict}" if verdict else None

    def _event_for_report(self, report: dict[str, Any]) -> NotificationEvent | None:
        """Map an orchestrator report to one owner-facing event."""
        status = self._text(report.get("status")) or ""
        task = self._text(report.get("task"))
        title = self._text(report.get("title"))
        raw_usage = report.get("usage")
        usage = raw_usage if isinstance(raw_usage, dict) else None
        review_reason = self._review_reason(report.get("review"))
        if status == "completed":
            return NotificationEvent(
                TASK_COMPLETED,
                task=task,
                title=title,
                status=status,
                detail=self._text(report.get("commit")),
                usage=usage,
            )
        if status == "retry":
            return NotificationEvent(
                TASK_REJECTED,
                task=task,
                title=title,
                status=status,
                reason=review_reason or self._text(report.get("error")),
                detail=self._text(report.get("error")),
                usage=usage,
            )
        if status == "blocked":
            reason = (
                self._text(report.get("reason")) or self._text(report.get("error")) or review_reason
            )
            error = self._text(report.get("error"))
            return NotificationEvent(
                TASK_BLOCKED,
                task=task,
                title=title,
                status=status,
                reason=reason,
                detail=error if error != reason else None,
                usage=usage,
            )
        if status == "stopped":
            is_budget = report.get("reason") == "BUDGET"
            reason = (
                self._text(report.get("budget_reason"))
                if is_budget
                else self._text(report.get("reason"))
            )
            detail = None
            if is_budget and report.get("limit") is not None:
                detail = f"limit={report.get('limit')} used={report.get('used')}"
            return NotificationEvent(
                RUN_BUDGET_STOP if is_budget else RUN_STOPPED,
                task=task,
                title=title,
                status=status,
                reason=reason,
                detail=detail,
                usage=usage,
            )
        return None

    def notify_report(self, report: dict[str, Any]) -> None:
        """Emit a notification for a report; never affects the run outcome."""
        with contextlib.suppress(Exception):
            event = self._event_for_report(report)
            if event is not None:
                self.notifier.notify(event)

    def notify_fatal(self, error: BaseException) -> None:
        """Emit at most one fatal-error notification for the same exception."""
        if self._fatal_notified is error:
            return
        self._fatal_notified = error
        with contextlib.suppress(Exception):
            self.notifier.notify(
                NotificationEvent(
                    FATAL_ERROR,
                    status="error",
                    reason=type(error).__name__,
                    detail=str(error),
                )
            )

    def _run_once(
        self, *, propose: bool = True, tracker: BudgetTracker | None = None
    ) -> dict[str, Any]:
        tracker = tracker or BudgetTracker(self.budget)
        stop = tracker.stop()
        if stop is not None:
            report = stop.to_report()
            self._write_event(report)
            return report
        self.store.recover_running()
        self._reconcile()
        self._cleanup_orphan_worktrees()
        task = self.store.claim_next()
        if task is None and propose:
            try:
                self.propose(tracker=tracker)
            except BudgetReached as exc:
                report = exc.stop.to_report(phase="architect")
                self._write_event(report)
                return report
            except Exception as exc:  # noqa: BLE001 - architect failure is a run error
                report = {"status": "blocked", "reason": "architect failed", "error": str(exc)}
                self._write_event(report)
                return report
            task = self.store.claim_next()
        if task is None:
            report = {"status": "idle", "reason": "no READY tasks", "completed": []}
            self._write_event(report)
            return report

        report = (
            self._run_isolated(task, tracker)
            if self.worktrees
            else self._run_inplace(task, tracker)
        )
        self._write_event(report)
        metrics = compute_metrics(self.store)
        self._write_event({"event": "metrics", **metrics})
        return report

    def metrics(self) -> dict[str, Any]:
        return compute_metrics(self.store)

    def _cleanup_orphan_worktrees(self) -> None:
        if not self.worktrees:
            return
        _cleanup_worktrees()

    def _run_isolated(self, task: Task, tracker: BudgetTracker | None = None) -> dict[str, Any]:
        tracker = tracker or BudgetTracker(self.budget)
        worktree: Path | None = None
        base: str | None = None
        try:
            worktree, base = _create_worktree(task)
            self.store.set_worktree(task.id, str(worktree), base)
            developer = self.runner.developer(
                _developer_prompt(task), cwd=worktree, context=self._context(task)
            )
            _validate_self_check(developer)
            self._account(task.id, developer, tracker)
            self._guard(tracker)
            self.store.transition(
                task.id,
                QA,
                session_id=developer.session_id,
                model=developer.model,
                evidence=developer.evidence_path,
            )
            qa = self.runner.qa(
                _qa_prompt(task, developer), cwd=worktree, context=self._context(task)
            )
            self._account(task.id, qa, tracker)
            self._guard(tracker)
            if not _qa_passed(qa):
                self.store.record_qa_failure(task.id)
                _remove_worktree(worktree)
                self.store.set_worktree(task.id, None, None)
                worktree = None
                retried = self.store.retry(task.id, f"QA: {qa.result[:4000]}")
                return {
                    "status": "retry" if retried and retried.status == READY else "blocked",
                    "task": task.id,
                    "qa": "fail",
                }
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
                context=self._context(task),
            )
            self._account(task.id, review, tracker)
            verdict = _parse_json(review.result)
            if verdict.get("verdict") != "accept":
                _remove_worktree(worktree)
                self.store.set_worktree(task.id, None, None)
                worktree = None
                self.store.record_review_rejection(task.id)
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
                "usage": tracker.usage.to_dict(),
                "review": verdict,
            }
        except BudgetReached as exc:
            # A budget stop is a safe boundary between model calls: discard
            # the candidate, release the task and let the next run retry it.
            if worktree is not None:
                _remove_worktree(worktree)
            self.store.release(task.id, f"BUDGET:{exc.stop.reason}")
            return exc.stop.to_report(task=task.id)
        except MergeGateError as exc:
            # Dirty main, moved base or a failed fast-forward cannot be fixed
            # by rerunning the task: discard the candidate and block with the
            # concrete git reason instead of burning the retry budget.
            if worktree is not None:
                _remove_worktree(worktree)
            self.store.set_worktree(task.id, None, None)
            reason = f"MERGE_GATE: {exc}"
            self.store.transition(task.id, BLOCKED, blocked_reason=reason, error=reason)
            return {
                "status": "blocked",
                "task": task.id,
                "reason": reason,
                "error": f"{type(exc).__name__}: {exc}",
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

    def _run_inplace(self, task: Task, tracker: BudgetTracker | None = None) -> dict[str, Any]:
        tracker = tracker or BudgetTracker(self.budget)
        files: list[str] = []
        staged = False
        try:
            developer = self.runner.developer(_developer_prompt(task), context=self._context(task))
            _validate_self_check(developer)
            self._account(task.id, developer, tracker)
            self._guard(tracker)
            self.store.transition(
                task.id,
                QA,
                session_id=developer.session_id,
                model=developer.model,
                evidence=developer.evidence_path,
            )
            qa = self.runner.qa(_qa_prompt(task, developer), context=self._context(task))
            self._account(task.id, qa, tracker)
            self._guard(tracker)
            if not _qa_passed(qa):
                self.store.record_qa_failure(task.id)
                retried = self.store.retry(task.id, f"QA: {qa.result[:4000]}")
                return {
                    "status": "retry" if retried and retried.status == READY else "blocked",
                    "task": task.id,
                    "qa": "fail",
                }
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
                ),
                context=self._context(task),
            )
            self._account(task.id, review, tracker)
            verdict = _parse_json(review.result)
            if verdict.get("verdict") != "accept":
                if staged:
                    _unstage(files)
                self.store.record_review_rejection(task.id)
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
                "usage": tracker.usage.to_dict(),
                "review": verdict,
            }
        except BudgetReached as exc:
            if staged:
                _unstage(files)
            self.store.release(task.id, f"BUDGET:{exc.stop.reason}")
            return exc.stop.to_report(task=task.id)
        except Exception as exc:  # noqa: BLE001 - task boundary is fail-closed
            if staged:
                _unstage(files)
            retried = self.store.retry(task.id, f"{type(exc).__name__}: {exc}")
            return {
                "status": "retry" if retried and retried.status == READY else "blocked",
                "task": task.id,
                "error": f"{type(exc).__name__}: {exc}",
            }

    def run(
        self,
        max_tasks: int | None = None,
        *,
        propose: bool = True,
        tracker: BudgetTracker | None = None,
    ) -> list[dict[str, Any]]:
        tracker = tracker or BudgetTracker(self.budget)
        requested = self.budget.max_tasks if max_tasks is None else max_tasks
        cap = self.budget.task_cap(requested)
        reports: list[dict[str, Any]] = []
        budget_stopped = False
        for _ in range(cap):
            stop = tracker.stop()
            if stop is not None:
                report = stop.to_report()
                reports.append(report)
                self.notify_report(report)
                budget_stopped = True
                break
            if (self.store.root / "STOP").exists():
                report = {"status": "stopped", "reason": "STOP file"}
                reports.append(report)
                self.notify_report(report)
                break
            report = self.run_once(propose=propose, tracker=tracker)
            reports.append(report)
            if report["status"] in {"idle", "stopped"}:
                budget_stopped = budget_stopped or report.get("reason") == "BUDGET"
                break
        attempted = [report for report in reports if report.get("task")]
        if requested > cap and not budget_stopped and len(attempted) >= cap:
            # The CLI asked for more tasks than the hard cap. Surface the
            # truncation as a normal budget stop instead of silently running
            # fewer tasks.
            report = BudgetStop(
                MAX_TASKS,
                float(cap),
                float(cap),
                tracker.usage,
            ).to_report(requested=requested)
            reports.append(report)
            self.notify_report(report)
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
    run.add_argument(
        "--max-tasks",
        type=int,
        default=None,
        help="task count; clamped to BA_MAX_TASKS_PER_RUN",
    )
    run.add_argument("--no-propose", action="store_true")
    sub.add_parser("status")
    sub.add_parser("metrics")
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
    if args.command == "metrics":
        print(json.dumps(compute_metrics(store), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "recover":
        with RUN_LOCK.open("a+") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print(json.dumps({"status": "locked", "reason": "a run is active"}))
                return 3
            recovered = store.recover_running()
            with contextlib.suppress(Exception):
                reconcile_invocations(store.root)
            _cleanup_worktrees()
        print(json.dumps([task.to_dict() for task in recovered], ensure_ascii=False, indent=2))
        return 0
    orchestrator = Orchestrator(
        ClaudeRunner(journal_root=store.root),
        store,
        notifier=Notifier.from_env(),
    )
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
        try:
            proposed = orchestrator.propose()
        except BudgetReached as exc:
            report = exc.stop.to_report(phase="architect")
            orchestrator.notify_report(report)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 2
        except Exception as exc:
            orchestrator.notify_fatal(exc)
            raise
        print(json.dumps([task.to_dict() for task in proposed], ensure_ascii=False, indent=2))
        return 0
    with RUN_LOCK.open("a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({"status": "locked", "reason": "another orchestrator is running"}))
            return 3
        try:
            reports = orchestrator.run(args.max_tasks, propose=not args.no_propose)
        except Exception as exc:
            orchestrator.notify_fatal(exc)
            raise
    print(json.dumps(reports, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if all(item["status"] != "blocked" for item in reports) else 2


if __name__ == "__main__":
    sys.exit(main())
