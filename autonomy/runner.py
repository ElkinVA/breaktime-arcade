"""Real Claude Code model invocations and evidence capture."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import socket
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autonomy.budget import Usage
from autonomy.landlock import abi_version, sandbox_preexec
from autonomy.observability import (
    InvocationContext,
    InvocationStart,
    boot_id,
    from_failure,
    from_outcome,
    pid_start_ticks,
    record_finished,
    record_started,
)
from autonomy.sandbox import (
    SandboxError,
    build_child_env,
    validate_worktree_cwd,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = ROOT / ".autonomy" / "evidence"
ARCHITECT_MODEL = os.environ.get("BA_ARCHITECT_MODEL", "deepseek-v4-pro")
DEVELOPER_MODEL = os.environ.get("BA_DEVELOPER_MODEL", "deepseek-flash[1m]")
QA_MODEL = os.environ.get("BA_QA_MODEL", "deepseek-flash")
REVIEWER_MODEL = os.environ.get("BA_REVIEWER_MODEL", "deepseek-v4-pro")
DEFAULT_TIMEOUT = int(os.environ.get("BA_MODEL_TIMEOUT", "900"))


class RunnerError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunResult:
    role: str
    model: str
    agent: str
    returncode: int
    session_id: str | None
    model_usage: dict[str, Any]
    result: str
    evidence_path: str
    duration_seconds: float
    total_cost_usd: float | None = None
    invocation_id: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    request_count: int | None = None
    num_turns: int | None = None

    @property
    def usage(self) -> Usage:
        """Actual token and cost usage reported by the model invocation."""
        return Usage.from_model_usage(self.model_usage, total_cost_usd=self.total_cost_usd)


class ClaudeRunner:
    def __init__(
        self,
        root: Path = ROOT,
        timeout: int = DEFAULT_TIMEOUT,
        *,
        worktree_root: Path | None = None,
        journal_root: Path | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.timeout = timeout
        self.worktree_root = (
            Path(worktree_root).resolve()
            if worktree_root is not None
            else self.root / ".autonomy" / "worktrees"
        )
        self.journal_root = (
            Path(journal_root).resolve() if journal_root is not None else self.root / ".autonomy"
        )
        EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)

    def _worktree_cwd(self, role: str, cwd: Path | None) -> Path:
        """Require a validated isolated worktree for a model role."""
        if cwd is None:
            raise RunnerError(f"{role} must run inside an isolated task worktree")
        try:
            return validate_worktree_cwd(
                cwd,
                project_root=self.root,
                worktree_root=self.worktree_root,
            )
        except SandboxError as exc:
            raise RunnerError(f"{role} rejected unsafe cwd: {exc}") from None

    def run(
        self,
        *,
        role: str,
        model: str,
        agent: str,
        prompt: str,
        allowed_tools: list[str],
        permission_mode: str,
        timeout: int | None = None,
        cwd: Path | None = None,
        context: InvocationContext | None = None,
    ) -> RunResult:
        context = context or InvocationContext()
        command = [
            "claude",
            "-p",
            "--model",
            model,
            "--agent",
            agent,
            "--permission-mode",
            permission_mode,
            "--allowedTools",
            ",".join(allowed_tools),
            "--output-format",
            "json",
            prompt,
        ]
        if cwd is None:
            raise RunnerError(f"{role} must run inside an isolated task worktree")
        # Callers may invoke run() directly, so validate here as well: the
        # Landlock ruleset grants write access to this directory.
        worktree = self._worktree_cwd(role, cwd)
        if abi_version() < 1 and not os.environ.get("PYTEST_CURRENT_TEST"):
            # Tests replace subprocess.run with a recorder; real model runs
            # must never proceed without the kernel boundary.
            raise RunnerError(
                "OS sandbox (Landlock) is unavailable; refusing to run a model unsandboxed"
            )
        started = time.monotonic()
        started_at = datetime.now(UTC).isoformat()
        invocation_id = str(uuid.uuid4())
        child_env = build_child_env()
        sandbox_root = self.journal_root / "agent-sandbox" / invocation_id
        home = sandbox_root / "home"
        temp = sandbox_root / "tmp"
        home.mkdir(parents=True, exist_ok=True)
        temp.mkdir(parents=True, exist_ok=True)
        # The child keeps its config/cache in a private HOME; the host HOME is
        # not readable under the Landlock ruleset.
        child_env["HOME"] = str(home)
        child_env["TMPDIR"] = str(temp)
        child_env["XDG_CONFIG_HOME"] = str(home / ".config")
        child_env["XDG_CACHE_HOME"] = str(home / ".cache")
        child_env["XDG_DATA_HOME"] = str(home / ".local/share")
        child_env["XDG_STATE_HOME"] = str(home / ".local/state")
        # Bind the sandbox runner to this task's worktree; an agent cannot
        # point --source-root at another task or the main checkout.
        child_env["BA_TASK_WORKTREE"] = str(worktree)
        owner_pid = os.getpid()
        finished = False

        def write_finish(metrics: Any) -> None:
            nonlocal finished
            if finished:
                return
            finished = True
            with contextlib.suppress(Exception):
                record_finished(self.journal_root, metrics)

        def failure_metrics(
            *,
            status: str,
            error_type: str,
            finished_at: str,
            duration_seconds: float,
            exit_code: int | None = None,
            session_id: str | None = None,
            model_usage: dict[str, Any] | None = None,
            total_cost: float | None = None,
            request_count: int | None = None,
            num_turns: int | None = None,
            is_error: bool | None = None,
        ) -> Any:
            return from_failure(
                invocation_id=invocation_id,
                agent=agent,
                role=role,
                model=model,
                status=status,
                error_type=error_type,
                task_id=context.task_id,
                attempt_id=context.attempt_id,
                retry_count=context.retry_count,
                session_id=session_id,
                model_usage=model_usage,
                total_cost_usd=total_cost,
                request_count=request_count,
                num_turns=num_turns,
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=duration_seconds,
                exit_code=exit_code,
                is_error=is_error,
            )

        try:
            with contextlib.suppress(Exception):
                record_started(
                    self.journal_root,
                    InvocationStart(
                        invocation_id=invocation_id,
                        agent_id=agent,
                        role=role,
                        model=model,
                        started_at=started_at,
                        task_id=context.task_id,
                        attempt_id=context.attempt_id,
                        retry_count=context.retry_count,
                        owner_pid=owner_pid,
                        owner_pid_start_ticks=pid_start_ticks(owner_pid),
                        boot_id=boot_id(),
                        host=socket.gethostname(),
                    ),
                )
            completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
                command,
                cwd=cwd or self.root,
                text=True,
                capture_output=True,
                timeout=timeout or self.timeout,
                check=False,
                env=child_env,
                preexec_fn=sandbox_preexec(
                    worktree,
                    home,
                    temp,
                    claude_path=shutil.which("claude", path=child_env.get("PATH")),
                ),
            )
        except subprocess.TimeoutExpired as exc:
            duration = time.monotonic() - started
            write_finish(
                failure_metrics(
                    status="timeout",
                    error_type="timeout",
                    finished_at=datetime.now(UTC).isoformat(),
                    duration_seconds=duration,
                )
            )
            raise RunnerError(f"{role} timed out after {timeout or self.timeout}s") from exc
        except KeyboardInterrupt:
            duration = time.monotonic() - started
            write_finish(
                failure_metrics(
                    status="cancelled",
                    error_type="operator_interrupt",
                    finished_at=datetime.now(UTC).isoformat(),
                    duration_seconds=duration,
                )
            )
            raise
        except Exception:
            duration = time.monotonic() - started
            write_finish(
                failure_metrics(
                    status="failed",
                    error_type="launch_error",
                    finished_at=datetime.now(UTC).isoformat(),
                    duration_seconds=duration,
                )
            )
            raise
        duration = time.monotonic() - started
        finished_at = datetime.now(UTC).isoformat()
        try:
            payload = self._parse_stdout(completed.stdout)
        except RunnerError:
            write_finish(
                failure_metrics(
                    status="failed",
                    error_type="invalid_output",
                    finished_at=finished_at,
                    duration_seconds=duration,
                    exit_code=completed.returncode,
                )
            )
            raise
        model_usage = payload.get("modelUsage") or {}
        session_id = payload.get("session_id")
        result = payload.get("result") or ""
        total_cost = payload.get("total_cost_usd")
        if not isinstance(total_cost, (int, float)) or isinstance(total_cost, bool):
            total_cost = None
        usage = Usage.from_model_usage(model_usage, total_cost_usd=total_cost)
        request_count = payload.get("request_count")
        if not isinstance(request_count, int) or isinstance(request_count, bool):
            request_count = None
        num_turns = payload.get("num_turns")
        if not isinstance(num_turns, int) or isinstance(num_turns, bool):
            num_turns = None
        is_error = bool(payload.get("is_error"))
        evidence = {
            "role": role,
            "requested_model": model,
            "agent": agent,
            "permission_mode": permission_mode,
            "allowed_tools": allowed_tools,
            "returncode": completed.returncode,
            "session_id": session_id,
            "invocation_id": invocation_id,
            "started_at": started_at,
            "finished_at": finished_at,
            "request_count": request_count,
            "num_turns": num_turns,
            "modelUsage": model_usage,
            "usage": usage.to_dict(),
            "total_cost_usd": total_cost,
            "is_error": payload.get("is_error"),
            "result": result,
            "duration_seconds": duration,
            "stderr_tail": completed.stderr[-2000:],
        }
        if completed.returncode != 0 or is_error:
            write_finish(
                failure_metrics(
                    status="failed",
                    error_type="api_error",
                    finished_at=finished_at,
                    duration_seconds=duration,
                    exit_code=completed.returncode,
                    session_id=session_id,
                    model_usage=model_usage,
                    total_cost=total_cost,
                    request_count=request_count,
                    num_turns=num_turns,
                    is_error=is_error,
                )
            )
            self._write_evidence(evidence)
            raise RunnerError(f"{role} failed: {result or completed.stderr[-500:]}")
        if not self._actual_model_matches(role, model_usage, model):
            write_finish(
                failure_metrics(
                    status="failed",
                    error_type="model_mismatch",
                    finished_at=finished_at,
                    duration_seconds=duration,
                    exit_code=completed.returncode,
                    session_id=session_id,
                    model_usage=model_usage,
                    total_cost=total_cost,
                    request_count=request_count,
                    num_turns=num_turns,
                    is_error=False,
                )
            )
            self._write_evidence(evidence)
            raise RunnerError(f"{role} did not use expected model {model}: {model_usage}")
        write_finish(
            from_outcome(
                invocation_id=invocation_id,
                agent=agent,
                role=role,
                model=model,
                status="ok",
                task_id=context.task_id,
                attempt_id=context.attempt_id,
                retry_count=context.retry_count,
                session_id=session_id,
                model_usage=model_usage,
                total_cost_usd=total_cost,
                request_count=request_count,
                num_turns=num_turns,
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=duration,
                exit_code=completed.returncode,
                is_error=False,
            )
        )
        evidence_path = self._write_evidence(evidence)
        return RunResult(
            role=role,
            model=model,
            agent=agent,
            returncode=completed.returncode,
            session_id=session_id,
            model_usage=model_usage,
            result=result,
            evidence_path=evidence_path,
            duration_seconds=duration,
            total_cost_usd=total_cost,
            invocation_id=invocation_id,
            started_at=started_at,
            finished_at=finished_at,
            request_count=request_count,
            num_turns=num_turns,
        )

    @staticmethod
    def _parse_stdout(stdout: str) -> dict[str, Any]:
        stdout = stdout.strip()
        if not stdout:
            return {}
        try:
            value = json.loads(stdout)
        except json.JSONDecodeError:
            for line in reversed(stdout.splitlines()):
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    return value
            raise RunnerError("model output was not JSON") from None
        if not isinstance(value, dict):
            raise RunnerError("model output JSON is not an object")
        return value

    @staticmethod
    def _actual_model_matches(
        role: str,
        model_usage: dict[str, Any],
        requested_model: str | None = None,
    ) -> bool:
        if not isinstance(model_usage, dict) or not model_usage:
            return False
        expected = "v4-pro" if role in {"architect", "reviewer"} else "flash"
        if requested_model:
            candidates = [requested_model] if requested_model in model_usage else []
        else:
            candidates = [name for name in model_usage if expected in name]
        for name in candidates:
            usage = model_usage.get(name)
            if not isinstance(usage, dict):
                continue
            input_tokens = usage.get("inputTokens", 0) or 0
            output_tokens = usage.get("outputTokens", 0) or 0
            if (
                isinstance(input_tokens, int)
                and isinstance(output_tokens, int)
                and input_tokens + output_tokens > 0
            ):
                return True
        return False

    @staticmethod
    def _write_evidence(evidence: dict[str, Any]) -> str:
        EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
        path = EVIDENCE_ROOT / f"{evidence['role']}-{uuid.uuid4()}.json"
        temp = path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temp.replace(path)
        return str(path)

    def architect(
        self,
        prompt: str,
        cwd: Path | None = None,
        *,
        context: InvocationContext | None = None,
    ) -> RunResult:
        return self.run(
            role="architect",
            model=ARCHITECT_MODEL,
            agent="autonomy-architect",
            prompt=prompt,
            allowed_tools=["Read", "Grep", "Glob"],
            permission_mode="plan",
            cwd=self._worktree_cwd("architect", cwd),
            context=context,
        )

    def developer(
        self,
        prompt: str,
        cwd: Path | None = None,
        *,
        context: InvocationContext | None = None,
    ) -> RunResult:
        return self.run(
            role="developer",
            model=DEVELOPER_MODEL,
            agent="autonomy-developer",
            prompt=prompt,
            allowed_tools=[
                "Read",
                "Grep",
                "Glob",
                "Edit",
                "Write",
            ],
            permission_mode="acceptEdits",
            cwd=self._worktree_cwd("developer", cwd),
            context=context,
        )

    def qa(
        self,
        prompt: str,
        cwd: Path | None = None,
        *,
        context: InvocationContext | None = None,
    ) -> RunResult:
        return self.run(
            role="qa",
            model=QA_MODEL,
            agent="autonomy-qa",
            prompt=prompt,
            allowed_tools=["Read", "Grep", "Glob"],
            permission_mode="acceptEdits",
            cwd=self._worktree_cwd("qa", cwd),
            context=context,
        )

    def reviewer(
        self,
        prompt: str,
        cwd: Path | None = None,
        *,
        context: InvocationContext | None = None,
    ) -> RunResult:
        return self.run(
            role="reviewer",
            model=REVIEWER_MODEL,
            agent="autonomy-reviewer",
            prompt=prompt,
            allowed_tools=["Read", "Grep", "Glob"],
            permission_mode="plan",
            cwd=self._worktree_cwd("reviewer", cwd),
            context=context,
        )
