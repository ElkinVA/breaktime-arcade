"""Real Claude Code model invocations and evidence capture."""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autonomy.budget import Usage

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

    @property
    def usage(self) -> Usage:
        """Actual token and cost usage reported by the model invocation."""
        return Usage.from_model_usage(self.model_usage, total_cost_usd=self.total_cost_usd)


class ClaudeRunner:
    def __init__(self, root: Path = ROOT, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.root = root
        self.timeout = timeout
        EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)

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
    ) -> RunResult:
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
        started = time.monotonic()
        try:
            completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
                command,
                cwd=cwd or self.root,
                text=True,
                capture_output=True,
                timeout=timeout or self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RunnerError(f"{role} timed out after {timeout or self.timeout}s") from exc
        duration = time.monotonic() - started
        payload = self._parse_stdout(completed.stdout)
        model_usage = payload.get("modelUsage") or {}
        session_id = payload.get("session_id")
        result = payload.get("result") or ""
        total_cost = payload.get("total_cost_usd")
        if not isinstance(total_cost, (int, float)) or isinstance(total_cost, bool):
            total_cost = None
        usage = Usage.from_model_usage(model_usage, total_cost_usd=total_cost)
        evidence = {
            "role": role,
            "requested_model": model,
            "agent": agent,
            "permission_mode": permission_mode,
            "allowed_tools": allowed_tools,
            "returncode": completed.returncode,
            "session_id": session_id,
            "modelUsage": model_usage,
            "usage": usage.to_dict(),
            "total_cost_usd": total_cost,
            "is_error": payload.get("is_error"),
            "result": result,
            "duration_seconds": duration,
            "stderr_tail": completed.stderr[-2000:],
        }
        evidence_path = self._write_evidence(evidence)
        if completed.returncode != 0 or payload.get("is_error"):
            raise RunnerError(f"{role} failed: {result or completed.stderr[-500:]}")
        if not self._actual_model_matches(role, model_usage, model):
            raise RunnerError(f"{role} did not use expected model {model}: {model_usage}")
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

    def architect(self, prompt: str, cwd: Path | None = None) -> RunResult:
        return self.run(
            role="architect",
            model=ARCHITECT_MODEL,
            agent="autonomy-architect",
            prompt=prompt,
            allowed_tools=["Read", "Grep", "Glob"],
            permission_mode="plan",
            cwd=cwd,
        )

    def developer(self, prompt: str, cwd: Path | None = None) -> RunResult:
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
                "Bash(python3 devcontrol/sandbox/run_tests.py:*)",
                "Bash(/home/elkinva/projects/ba/.venv/bin/python -m ruff:*)",
                "Bash(/home/elkinva/projects/ba/.venv/bin/python -m mypy:*)",
                "Bash(/home/elkinva/projects/ba/.venv/bin/python -m pytest:*)",
                "Bash(git status:*)",
                "Bash(git diff:*)",
            ],
            permission_mode="acceptEdits",
            cwd=cwd,
        )

    def qa(self, prompt: str, cwd: Path | None = None) -> RunResult:
        return self.run(
            role="qa",
            model=QA_MODEL,
            agent="autonomy-qa",
            prompt=prompt,
            allowed_tools=[
                "Read",
                "Grep",
                "Glob",
                "Bash(python3 devcontrol/sandbox/run_tests.py:*)",
                "Bash(/home/elkinva/projects/ba/.venv/bin/python -m ruff:*)",
                "Bash(/home/elkinva/projects/ba/.venv/bin/python -m mypy:*)",
                "Bash(/home/elkinva/projects/ba/.venv/bin/python -m pytest:*)",
                "Bash(git diff:*)",
            ],
            permission_mode="acceptEdits",
            cwd=cwd,
        )

    def reviewer(self, prompt: str, cwd: Path | None = None) -> RunResult:
        return self.run(
            role="reviewer",
            model=REVIEWER_MODEL,
            agent="autonomy-reviewer",
            prompt=prompt,
            allowed_tools=["Read", "Grep", "Glob", "Bash(git diff:*)"],
            permission_mode="plan",
            cwd=cwd,
        )
