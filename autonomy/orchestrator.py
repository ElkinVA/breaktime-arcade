"""Task queue → Pro Architect → Flash Developer → Flash QA → Pro Review."""

# ruff: noqa: T201, S607, S603

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import shlex
import shutil
import subprocess
import sys
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from devcontrol.telegram import sanitize_text

from autonomy.budget import (
    MAX_TASKS,
    Budget,
    BudgetReached,
    BudgetStop,
    BudgetTracker,
)
from autonomy.gate import (
    KIND_MILESTONE,
    OwnerActionRequired,
    clear_gate,
    load_gate,
    mark_notified,
    paused_report,
    set_gate,
)
from autonomy.metrics import compute_metrics
from autonomy.notifier import (
    FATAL_ERROR,
    MILESTONE_COMPLETED,
    OWNER_ACTION_REQUIRED,
    RUN_BUDGET_STOP,
    RUN_STOPPED,
    TASK_BLOCKED,
    TASK_COMPLETED,
    TASK_REJECTED,
    NotificationEvent,
    Notifier,
)
from autonomy.observability import InvocationContext, reconcile_invocations
from autonomy.runner import ClaudeRunner, RunnerError, RunResult
from autonomy.state import (
    BLOCKED,
    COMPLETED,
    QA,
    READY,
    REVIEW,
    StateStore,
    Task,
)
from autonomy.status_report import derive_status, write_last_report
from autonomy.windows_notify import send_toast


def _dump(value: Any) -> str:
    return sanitize_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


ROOT = Path(__file__).resolve().parents[1]
STATE_ROOT = Path(__file__).resolve().parents[1] / ".autonomy"
ChecksRunner = Callable[[Path], tuple[str, list[str]]]
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
    ".claude/agents/",
    ".claude/hooks",
    "docs/spec/",
    "docs/decisions/",
    "reports/",
    "autonomy/",
    "devcontrol/",
    "scripts/",
    ".claude/skills/",
    ".claude/commands/",
    ".mcp.json",
    ".github/",
    "infra/",
    "sdk/",
    "schemas/",
    "pyproject.toml",
    "uv.lock",
    "mypy.ini",
    ".pre-commit-config.yaml",
    ".dockerignore",
    "Dockerfile",
    "Makefile",
    "package.json",
    "package-lock.json",
    "compose.yml",
    "compose.dev-lite.yml",
    "compose.staging.yml",
    "compose.prod.yml",
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


def _create_worktree(task: Task, base: str | None = None) -> tuple[Path, str]:
    _assert_main_clean()
    safe_id = "".join(ch for ch in task.id if ch.isalnum() or ch in "-_")[:80]
    if not safe_id:
        raise RunnerError("task id has no safe worktree prefix")
    base = base or _head()
    path = WORKTREE_ROOT / f"{safe_id}-{uuid.uuid4().hex[:12]}" / "ba"
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


def _discard_worktrees(*paths: Path | None) -> None:
    for path in paths:
        if path is not None:
            _remove_worktree(path)


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


def _strict_json_object(value: str) -> dict[str, Any] | None:
    """Parse one complete JSON object; never repair or guess."""
    text = value.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()
        if text.startswith("json"):
            text = text[4:].lstrip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _qa_passed(qa: RunResult) -> bool:
    parsed = _strict_json_object(qa.result)
    return parsed is not None and parsed.get("status") == "pass"


def _reviewer_verdict(value: str) -> dict[str, Any]:
    """Require a complete reviewer verdict; malformed output is a reject."""
    parsed = _strict_json_object(value)
    if (
        parsed is None
        or parsed.get("verdict") not in {"accept", "reject"}
        or not isinstance(parsed.get("findings"), list)
    ):
        return {
            "verdict": "reject",
            "findings": [
                {
                    "severity": "blocker",
                    "file": "reviewer",
                    "summary": "Malformed or incomplete review JSON",
                    "scenario": "Review must be one valid JSON object with verdict and findings.",
                }
            ],
        }
    return parsed


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


def _validate_worktree_git(worktree: Path) -> None:
    """Refuse git operations if the worktree's ``.git`` pointer was altered.

    A model can write inside its worktree; without this check a poisoned
    ``.git`` file could redirect ``git add/commit`` to the main checkout.
    """
    if worktree.resolve() == ROOT.resolve():
        return
    git_file = worktree / ".git"
    if git_file.is_symlink() or not git_file.is_file():
        raise RuntimeError("worktree .git metadata is missing or unsafe")
    text = git_file.read_text(encoding="utf-8").strip()
    if not text.startswith("gitdir: "):
        raise RuntimeError("worktree .git metadata has an unexpected format")
    target = Path(text.removeprefix("gitdir: ").strip())
    if not target.is_absolute():
        target = worktree / target
    expected = (ROOT / ".git" / "worktrees").resolve()
    if not target.resolve().is_relative_to(expected):
        raise RuntimeError("worktree .git metadata points outside the project worktrees")


def _changed_files(root: Path) -> list[str]:
    """Derive the changed-file set from Git, not from the developer report."""
    _validate_worktree_git(root)
    tracked = _git(["diff", "--name-only", "-z", "HEAD"], cwd=root)
    untracked = _git(["ls-files", "--others", "--exclude-standard", "-z"], cwd=root)
    names = {name for name in (tracked.stdout + untracked.stdout).split("\0") if name}
    files: list[str] = []
    for name in sorted(names):
        if name.startswith("/") or ".." in name.split("/"):
            raise RuntimeError(f"git reported an unsafe path: {name}")
        _safe_file(name, root)
        files.append(name)
    if not files:
        raise RuntimeError("developer changed no files; refusing an empty change")
    return files


def _developer_files(developer: RunResult, root: Path | None = None) -> list[str]:
    root = root or ROOT
    try:
        parsed = _parse_json(developer.result)
    except (ValueError, json.JSONDecodeError):  # fmt: skip
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
    _validate_worktree_git(worktree)
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
            return result.stdout
        result = _git(["diff", "--", *files], cwd=root, check=False)
        return result.stdout
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


def _sandbox_command() -> str:
    """Trusted main-checkout runner; the worktree is only a copy source."""
    return f"{ROOT / '.venv/bin/python'} {ROOT / 'devcontrol/sandbox/run_tests.py'}"


def _sandbox_commands() -> list[tuple[str, str, str]]:
    """Return ``(label, sandbox command, evidence command)`` checks."""
    command = _sandbox_command()
    return [
        (
            "pytest",
            f"{command} --source-root . --tool pytest --timeout 1800",
            "pytest -q (full suite)",
        ),
        (
            "makemigrations-check",
            f"{command} --source-root . --tool makemigrations-check --timeout 1800",
            "python manage.py makemigrations --check --dry-run",
        ),
        (
            "ruff",
            f"{command} --source-root . --tool ruff --timeout 1800",
            "ruff check apps config tests devcontrol && "
            "ruff format --check apps config tests devcontrol",
        ),
        (
            "mypy",
            f"{command} --source-root . --tool mypy --timeout 1800",
            "mypy",
        ),
        (
            "js",
            f"{command} --source-root . --tool js --timeout 1800",
            "node --test tests/js/*.test.mjs",
        ),
    ]


def _append_event(root: Path, payload: dict[str, Any]) -> None:
    events = Path(root) / "events.jsonl"
    events.parent.mkdir(parents=True, exist_ok=True)
    with events.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _notify_gate_once(
    store: StateStore,
    gate: Any,
    report: dict[str, Any],
    notifier: Notifier,
    windows_notifier: Callable[[str, str], object] | None = None,
) -> None:
    if windows_notifier is None:
        windows_notifier = send_toast
    current = load_gate(store.root)
    if current is None or current.notified_at is not None:
        return
    delivered = False
    kind = MILESTONE_COMPLETED if gate.kind == KIND_MILESTONE else OWNER_ACTION_REQUIRED
    with contextlib.suppress(Exception):
        result = notifier.notify(
            NotificationEvent(
                kind,
                status="paused",
                reason=gate.reason,
                detail=gate.requested_action,
            )
        )
        delivered = getattr(result, "status", None) == "sent"
    title = (
        "Breaktime Arcade: этап завершён"
        if gate.kind == KIND_MILESTONE
        else "Breaktime Arcade: требуется решение"
    )
    message = gate.reason
    if gate.requested_action:
        message = f"{message}\n{gate.requested_action}"
    with contextlib.suppress(Exception):
        toast = windows_notifier(title, message)
        delivered = delivered or getattr(toast, "status", None) == "sent"
    if delivered:
        mark_notified(store.root)


def _run_orchestrator_checks(worktree: Path) -> tuple[str, list[str]]:
    """Run the trusted sandbox checks in the parent, outside the model sandbox.

    The model child has no Docker socket or host paths, so it cannot execute
    the test runner itself. The parent runs the same fixed commands against the
    committed candidate; the runner copies the worktree into a capability-
    dropped container, so untrusted code is still not executed on the host.
    Returns the evidence text and the list of failed tools; a non-empty list
    must hard-fail the candidate before QA.
    """
    lines: list[str] = []
    failed: list[str] = []
    for label, command, evidence_command in _sandbox_commands():
        argv = shlex.split(command)
        try:
            completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
                argv,
                cwd=worktree,
                text=True,
                capture_output=True,
                timeout=1900,
                check=False,
            )
            output = (completed.stdout + completed.stderr)[-3000:]
            lines.append(
                f"- {label}: exit={completed.returncode}\n"
                f"command: {evidence_command}\n"
                f"sandbox: {command}\n{output}"
            )
            if completed.returncode != 0:
                failed.append(label)
        except subprocess.TimeoutExpired:
            lines.append(f"- {label}: TIMEOUT\ncommand: {evidence_command}\nsandbox: {command}")
            failed.append(label)
        except Exception as exc:  # noqa: BLE001 - evidence must reach QA
            lines.append(
                f"- {label}: LAUNCH ERROR {type(exc).__name__}: {exc}\n"
                f"command: {evidence_command}\nsandbox: {command}"
            )
            failed.append(label)
    return "\n".join(lines) or "no checks configured", failed


def _developer_prompt(task: Task) -> str:
    return (
        f"Task ID: {task.id}\nTitle: {task.title}\n"
        f"Acceptance criteria:\n- " + "\n- ".join(task.acceptance) + "\n"
        "Implement exactly this task in the isolated worktree. The orchestrator runs "
        "the trusted sandbox test suite on your committed candidate after handoff; "
        "the model sandbox has no Docker socket or host paths, so do not attempt to "
        "run pytest/mypy/ruff/npm or the sandbox runner yourself. In self_check set "
        "tests_run to [] and describe known limits honestly.\n"
        "Do not change game features. Complete the mandatory self-check against the "
        "ТЗ, scope and localization/regressions; include its fields in the JSON. "
        + (f"Previous failure to address:\n{task.last_error[:4000]}\n" if task.last_error else "")
        + "Return the strict JSON report from your instructions."
    )


def _qa_prompt(task: Task, developer: RunResult, checks: str = "") -> str:
    return (
        f"Task ID: {task.id}\nTitle: {task.title}\n"
        f"Acceptance criteria:\n- " + "\n- ".join(task.acceptance) + "\n"
        f"Developer report:\n{developer.result[:8000]}\n"
        "The orchestrator ran the trusted sandbox checks on the committed candidate. "
        "Review the code and this evidence; do not run host commands (the QA sandbox "
        f"has no Docker socket):\n{checks or 'checks were not executed'}\n"
        "Return the strict JSON QA report."
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
        "or if it is unsafe. Output ONLY one syntactically valid JSON object: "
        "the first character must be '{', the last must be '}', with no prose, "
        "headings, bullet lists, or markdown fences. Close every array and "
        "object before finishing."
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
        checks_runner: ChecksRunner | None = None,
        windows_notifier: Callable[[str, str], object] | None = None,
    ) -> None:
        self.runner = runner
        self.store = store or StateStore(STATE_ROOT)
        self.commit = commit
        self.worktrees = worktrees
        self.budget = budget or Budget.from_env()
        # The trusted product-check runner is injectable so lifecycle tests can
        # use a disposable git repository without weakening production checks.
        self.checks_runner = checks_runner or _run_orchestrator_checks
        # Explicit injection keeps tests and library callers send-free; the
        # CLI enables the owner-configured notifier via ``Notifier.from_env``.
        self.notifier = notifier if notifier is not None else Notifier.disabled()
        self.windows_notifier = windows_notifier or send_toast
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

    def _paused_if_gated(self) -> dict[str, Any] | None:
        gate = load_gate(self.store.root)
        if gate is None:
            return None
        report = paused_report(gate)
        self._write_event(report)
        self._notify_gate(gate, report)
        with contextlib.suppress(Exception):
            write_last_report(self.store, report)
        return report

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
        gate = load_gate(self.store.root)
        if gate is not None:
            raise OwnerActionRequired(paused_report(gate))
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
                gate = load_gate(self.store.root)
                if gate is not None:
                    raise OwnerActionRequired(paused_report(gate))
                result = self.runner.architect(prompt, cwd=worktree, context=InvocationContext())
            else:
                # Test/legacy mode keeps the original prompt-only signature.
                gate = load_gate(self.store.root)
                if gate is not None:
                    raise OwnerActionRequired(paused_report(gate))
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
        if status == "paused":
            gate = report.get("gate")
            gate = gate if isinstance(gate, dict) else {}
            kind = (
                MILESTONE_COMPLETED if gate.get("kind") == KIND_MILESTONE else OWNER_ACTION_REQUIRED
            )
            return NotificationEvent(
                kind,
                status="paused",
                reason=self._text(gate.get("reason")) or "OWNER_ACTION_REQUIRED",
                detail=self._text(gate.get("requested_action")),
            )
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

    def _notify_gate(self, gate: Any, report: dict[str, Any]) -> None:
        """Notify once per gate; repeated timer firings stay silent."""
        with contextlib.suppress(Exception):
            _notify_gate_once(self.store, gate, report, self.notifier, self.windows_notifier)

    def notify_report(self, report: dict[str, Any]) -> None:
        """Emit a notification for a report; never affects the run outcome."""
        with contextlib.suppress(Exception):
            write_last_report(self.store, report)
            event = self._event_for_report(report)
            if event is not None and report.get("status") != "paused":
                self.notifier.notify(event)

    def notify_fatal(self, error: BaseException) -> None:
        """Emit at most one fatal-error notification for the same exception."""
        if self._fatal_notified is error:
            return
        self._fatal_notified = error
        with contextlib.suppress(Exception):
            self._write_event(
                {
                    "event": "fatal_error",
                    "at": datetime.now(UTC).isoformat(),
                    "reason": type(error).__name__,
                }
            )
            write_last_report(
                self.store,
                {
                    "status": "fatal_error",
                    "reason": type(error).__name__,
                    "detail": str(error),
                },
            )
            self.notifier.notify(
                NotificationEvent(
                    FATAL_ERROR,
                    status="error",
                    reason=type(error).__name__,
                    detail=str(error),
                )
            )
            self.windows_notifier(
                "Breaktime Arcade: критическая ошибка",
                type(error).__name__,
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
        if (self.store.root / "STOP").exists():
            report = {"status": "stopped", "reason": "STOP file"}
            self._write_event(report)
            return report
        paused = self._paused_if_gated()
        if paused is not None:
            return paused
        self._write_event(
            {
                "event": "run_started",
                "pid": os.getpid(),
                "at": datetime.now(UTC).isoformat(),
            }
        )
        self.store.recover_running()
        self._reconcile()
        self._cleanup_orphan_worktrees()
        paused = self._paused_if_gated()
        if paused is not None:
            return paused
        task = self.store.claim_next()
        if task is None and propose:
            try:
                self.propose(tracker=tracker)
            except OwnerActionRequired as exc:
                report = exc.report
                self._write_event(report)
                current_gate = load_gate(self.store.root)
                if current_gate is not None:
                    self._notify_gate(current_gate, report)
                with contextlib.suppress(Exception):
                    write_last_report(self.store, report)
                return report
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

        paused = self._paused_if_gated()
        if paused is not None:
            self.store.release(task.id, "OWNER_ACTION_REQUIRED")
            return paused
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
        qa_worktree: Path | None = None
        base: str | None = None
        try:
            worktree, base = _create_worktree(task)
            self.store.set_worktree(task.id, str(worktree), base)
            paused = self._paused_if_gated()
            if paused is not None:
                _discard_worktrees(worktree)
                self.store.set_worktree(task.id, None, None)
                self.store.release(task.id, "OWNER_ACTION_REQUIRED")
                return paused
            developer = self.runner.developer(
                _developer_prompt(task), cwd=worktree, context=self._context(task)
            )
            _validate_self_check(developer)
            files = _changed_files(worktree)
            self._account(task.id, developer, tracker)
            self._guard(tracker)
            # Commit the candidate before QA; QA runs in a clean worktree at
            # exactly this SHA and cannot modify the code under test.
            candidate = _commit_candidate(task, files, worktree)
            self.store.set_candidate(task.id, candidate)
            qa_worktree, _ = _create_worktree(task, base=candidate)
            paused = self._paused_if_gated()
            if paused is not None:
                _discard_worktrees(worktree, qa_worktree)
                self.store.set_worktree(task.id, None, None)
                self.store.release(task.id, "OWNER_ACTION_REQUIRED")
                return paused
            checks, failed_checks = self.checks_runner(qa_worktree)
            if failed_checks:
                paused = self._paused_if_gated()
                if paused is not None:
                    _discard_worktrees(worktree, qa_worktree)
                    self.store.set_worktree(task.id, None, None)
                    self.store.release(task.id, "OWNER_ACTION_REQUIRED")
                    return paused
                _discard_worktrees(worktree, qa_worktree)
                self.store.set_worktree(task.id, None, None)
                worktree = None
                qa_worktree = None
                retried = self.store.retry(
                    task.id,
                    f"orchestrator checks failed: {', '.join(failed_checks)}",
                )
                return {
                    "status": "retry" if retried and retried.status == READY else "blocked",
                    "task": task.id,
                    "checks": failed_checks,
                }
            paused = self._paused_if_gated()
            if paused is not None:
                _discard_worktrees(worktree, qa_worktree)
                self.store.set_worktree(task.id, None, None)
                self.store.release(task.id, "OWNER_ACTION_REQUIRED")
                return paused
            self.store.transition(
                task.id,
                QA,
                session_id=developer.session_id,
                model=developer.model,
                evidence=developer.evidence_path,
            )
            qa = self.runner.qa(
                _qa_prompt(task, developer, checks),
                cwd=qa_worktree,
                context=self._context(task),
            )
            self._account(task.id, qa, tracker)
            self._guard(tracker)
            if not _qa_passed(qa):
                paused = self._paused_if_gated()
                if paused is not None:
                    _discard_worktrees(worktree, qa_worktree)
                    self.store.set_worktree(task.id, None, None)
                    self.store.release(task.id, "OWNER_ACTION_REQUIRED")
                    return paused
                self.store.record_qa_failure(task.id)
                _discard_worktrees(worktree, qa_worktree)
                self.store.set_worktree(task.id, None, None)
                worktree = None
                qa_worktree = None
                retried = self.store.retry(task.id, f"QA: {qa.result[:4000]}")
                return {
                    "status": "retry" if retried and retried.status == READY else "blocked",
                    "task": task.id,
                    "qa": "fail",
                }
            paused = self._paused_if_gated()
            if paused is not None:
                _discard_worktrees(worktree, qa_worktree)
                self.store.set_worktree(task.id, None, None)
                self.store.release(task.id, "OWNER_ACTION_REQUIRED")
                return paused
            self.store.transition(
                task.id, REVIEW, session_id=qa.session_id, model=qa.model, evidence=qa.evidence_path
            )
            review = self.runner.reviewer(
                _reviewer_prompt(
                    task,
                    developer,
                    qa,
                    _git_diff(files, base=base, candidate=candidate, root=worktree),
                ),
                cwd=qa_worktree,
                context=self._context(task),
            )
            self._account(task.id, review, tracker)
            verdict = _reviewer_verdict(review.result)
            if verdict.get("verdict") != "accept":
                paused = self._paused_if_gated()
                if paused is not None:
                    _discard_worktrees(worktree, qa_worktree)
                    self.store.set_worktree(task.id, None, None)
                    self.store.release(task.id, "OWNER_ACTION_REQUIRED")
                    return paused
                _discard_worktrees(worktree, qa_worktree)
                self.store.set_worktree(task.id, None, None)
                worktree = None
                qa_worktree = None
                self.store.record_review_rejection(task.id)
                retried = self.store.retry(task.id, json.dumps(verdict, ensure_ascii=False)[:4000])
                return {
                    "status": "retry" if retried and retried.status == READY else "blocked",
                    "task": task.id,
                    "review": verdict,
                }
            paused = self._paused_if_gated()
            if paused is not None:
                _discard_worktrees(worktree, qa_worktree)
                self.store.set_worktree(task.id, None, None)
                self.store.release(task.id, "OWNER_ACTION_REQUIRED")
                return paused
            merged = _merge_candidate(candidate, base)
            completed = self.store.transition(
                task.id,
                COMPLETED,
                session_id=review.session_id,
                model=review.model,
                evidence=review.evidence_path,
            )
            _discard_worktrees(worktree, qa_worktree)
            worktree = None
            qa_worktree = None
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
            _discard_worktrees(worktree, qa_worktree)
            self.store.release(task.id, f"BUDGET:{exc.stop.reason}")
            return exc.stop.to_report(task=task.id)
        except MergeGateError as exc:
            # Dirty main, moved base or a failed fast-forward cannot be fixed
            # by rerunning the task: discard the candidate and block with the
            # concrete git reason instead of burning the retry budget.
            _discard_worktrees(worktree, qa_worktree)
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
            _discard_worktrees(worktree, qa_worktree)
            self.store.set_worktree(task.id, None, None)
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
            paused = self._paused_if_gated()
            if paused is not None:
                self.store.release(task.id, "OWNER_ACTION_REQUIRED")
                return paused
            developer = self.runner.developer(_developer_prompt(task), context=self._context(task))
            _validate_self_check(developer)
            files = _changed_files(ROOT) if self.commit else _developer_files(developer)
            self._account(task.id, developer, tracker)
            self._guard(tracker)
            self.store.transition(
                task.id,
                QA,
                session_id=developer.session_id,
                model=developer.model,
                evidence=developer.evidence_path,
            )
            paused = self._paused_if_gated()
            if paused is not None:
                self.store.release(task.id, "OWNER_ACTION_REQUIRED")
                return paused
            qa = self.runner.qa(_qa_prompt(task, developer), context=self._context(task))
            self._account(task.id, qa, tracker)
            self._guard(tracker)
            if not _qa_passed(qa):
                paused = self._paused_if_gated()
                if paused is not None:
                    self.store.release(task.id, "OWNER_ACTION_REQUIRED")
                    return paused
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
            paused = self._paused_if_gated()
            if paused is not None:
                if staged:
                    _unstage(files)
                self.store.release(task.id, "OWNER_ACTION_REQUIRED")
                return paused
            base = _head() if self.commit else "no-git-test"
            candidate: str | None = None
            if self.commit:
                paused = self._paused_if_gated()
                if paused is not None:
                    self.store.release(task.id, "OWNER_ACTION_REQUIRED")
                    return paused
                try:
                    _stage_task(files)
                except Exception:
                    _unstage(files)
                    raise
                staged = True
                _commit_staged(task, files)
                candidate = _head()
            paused = self._paused_if_gated()
            if paused is not None:
                if staged:
                    _unstage(files)
                self.store.release(task.id, "OWNER_ACTION_REQUIRED")
                return paused
            review = self.runner.reviewer(
                _reviewer_prompt(
                    task, developer, qa, _git_diff(files, base=base, candidate=candidate, root=ROOT)
                ),
                context=self._context(task),
            )
            self._account(task.id, review, tracker)
            verdict = _reviewer_verdict(review.result)
            if verdict.get("verdict") != "accept":
                if staged:
                    _unstage(files)
                paused = self._paused_if_gated()
                if paused is not None:
                    self.store.release(task.id, "OWNER_ACTION_REQUIRED")
                    return paused
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
            if report["status"] in {"idle", "stopped", "paused"}:
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
    pause = sub.add_parser("pause")
    pause.add_argument("--reason", required=True)
    pause.add_argument("--action", default=None)
    pause.add_argument("--recommendation", default=None)
    checkpoint = sub.add_parser("checkpoint")
    checkpoint.add_argument("--milestone", required=True)
    checkpoint.add_argument("--reason", default="milestone completed")
    checkpoint.add_argument("--action", default=None)
    checkpoint.add_argument("--recommendation", default=None)
    sub.add_parser("resume")
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
        try:
            report = derive_status(store)
        except Exception as exc:  # noqa: BLE001 - status must fail closed
            print(_dump({"status": "STOPPED_ERROR", "reason": type(exc).__name__}))
            return 2
        print(_dump(report))
        return 0
    if args.command in {"pause", "checkpoint"}:
        if args.command == "checkpoint":
            gate = set_gate(
                store.root,
                reason=args.reason,
                kind=KIND_MILESTONE,
                milestone=args.milestone,
                requested_action=args.action,
                recommendation=args.recommendation,
            )
        else:
            gate = set_gate(
                store.root,
                reason=args.reason,
                requested_action=args.action,
                recommendation=args.recommendation,
            )
        report = paused_report(gate)
        _append_event(
            store.root,
            {
                "event": "checkpoint" if args.command == "checkpoint" else "owner_action_required",
                **report,
            },
        )
        _notify_gate_once(store, gate, report, Notifier.from_env())
        with contextlib.suppress(Exception):
            write_last_report(store, report)
        print(_dump(derive_status(store)))
        return 0
    if args.command == "resume":
        cleared = clear_gate(store.root)
        _append_event(store.root, {"event": "owner_action_cleared", "cleared": cleared})
        print(_dump(derive_status(store)))
        return 0
    if args.command == "metrics":
        print(json.dumps(compute_metrics(store), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "recover":
        with RUN_LOCK.open("a+") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print(_dump({"status": "locked", "reason": "a run is active"}))
                return 3
            lock.seek(0)
            lock.truncate()
            lock.write(str(os.getpid()))
            lock.flush()
            recovered = store.recover_running()
            with contextlib.suppress(Exception):
                reconcile_invocations(store.root)
            _cleanup_worktrees()
        print(_dump([task.to_dict() for task in recovered]))
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
        print(_dump([item.to_dict() for item in added]))
        return 0
    if args.command == "propose":
        try:
            proposed = orchestrator.propose()
        except OwnerActionRequired as exc:
            print(_dump(exc.report))
            return 0
        except BudgetReached as exc:
            report = exc.stop.to_report(phase="architect")
            orchestrator.notify_report(report)
            print(_dump(report))
            return 2
        except Exception as exc:
            orchestrator.notify_fatal(exc)
            raise
        print(_dump([task.to_dict() for task in proposed]))
        return 0
    with RUN_LOCK.open("a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(_dump({"status": "locked", "reason": "another orchestrator is running"}))
            return 3
        lock.seek(0)
        lock.truncate()
        lock.write(str(os.getpid()))
        lock.flush()
        try:
            reports = orchestrator.run(args.max_tasks, propose=not args.no_propose)
        except Exception as exc:
            orchestrator.notify_fatal(exc)
            raise
    print(_dump(reports))
    return 0 if all(item["status"] != "blocked" for item in reports) else 2


if __name__ == "__main__":
    sys.exit(main())
