"""Supported Claude Code background-session control.

Only documented commands are used: ``claude --bg``, ``claude agents --json``,
``claude logs`` and ``claude stop``. No shell is involved and no arbitrary
command from Telegram reaches the CLI.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from devcontrol.config import redact

SAFE_ENV_KEYS = (
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "CLAUDE_CODE_SUBAGENT_MODEL",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
    "TMPDIR",
    "XDG_CONFIG_HOME",
    "XDG_CACHE_HOME",
    "DOCKER_HOST",
    "DOCKER_CONTEXT",
    "DEVCONTROL_RUNTIME_DIR",
)

INACTIVE_STATES = {"done", "exited", "failed", "stopped", "completed"}
START_REF_RE = re.compile(r"backgrounded\s*[·.-]\s*([A-Za-z0-9_-]{4,40})")
ATTACH_REF_RE = re.compile(r"claude attach\s+([A-Za-z0-9_-]{4,40})")


class ClaudeError(Exception):
    """Claude CLI failure with a sanitised message."""


def parse_start_reference(raw: str) -> str | None:
    """Extract the short id printed by ``claude --bg`` from its output."""
    for pattern in (START_REF_RE, ATTACH_REF_RE):
        match = pattern.search(raw)
        if match:
            return match.group(1)
    return None


@dataclass(frozen=True)
class StartResult:
    ok: bool
    message: str
    session: dict[str, Any] | None = None
    raw: str = ""


@dataclass(frozen=True)
class ClaudeSession:
    pid: int | None
    cwd: str
    kind: str
    session_id: str | None
    name: str | None
    status: str
    started_at: int | None
    raw_id: str | None
    state: str | None = None
    waiting_for: str | None = None

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> ClaudeSession:
        return cls(
            pid=value.get("pid") if isinstance(value.get("pid"), int) else None,
            cwd=str(value.get("cwd") or ""),
            kind=str(value.get("kind") or ""),
            session_id=value.get("sessionId") if isinstance(value.get("sessionId"), str) else None,
            name=value.get("name") if isinstance(value.get("name"), str) else None,
            status=str(value.get("status") or ""),
            started_at=value.get("startedAt") if isinstance(value.get("startedAt"), int) else None,
            raw_id=value.get("id") if isinstance(value.get("id"), str) else None,
            state=value.get("state") if isinstance(value.get("state"), str) else None,
            waiting_for=value.get("waitingFor")
            if isinstance(value.get("waitingFor"), str)
            else None,
        )

    @property
    def active(self) -> bool:
        if self.state in INACTIVE_STATES:
            return False
        return self.pid is not None or self.status in {"busy", "working", "waiting"}

    @property
    def reference(self) -> str:
        return self.raw_id or self.name or self.session_id or ""


class ClaudeController:
    def __init__(
        self,
        *,
        project_dir: Path,
        claude_bin: str = "claude",
        session_name: str,
        settings_path: Path,
        timeout: int = 60,
    ) -> None:
        self.project_dir = project_dir
        self.claude_bin = claude_bin
        self.session_name = session_name
        self.settings_path = settings_path
        self.timeout = timeout

    def available(self) -> bool:
        return shutil.which(self.claude_bin) is not None

    def _env(self) -> dict[str, str]:
        env = {key: os.environ[key] for key in SAFE_ENV_KEYS if key in os.environ}
        env.setdefault("PATH", f"{Path.home()}/.local/bin:/usr/local/bin:/usr/bin:/bin")
        return env

    def _run(
        self, argv: list[str], *, timeout: int | None = None
    ) -> subprocess.CompletedProcess[str]:
        if not self.available():
            raise ClaudeError(f"Claude CLI not found: {self.claude_bin}")
        try:
            # argv is a fixed list built by this module; shell=False; filtered env.
            return subprocess.run(  # noqa: S603
                argv,
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=timeout or self.timeout,
                check=False,
                env=self._env(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ClaudeError(redact(f"{type(exc).__name__}: {exc}")) from None

    def list_sessions(self) -> list[ClaudeSession]:
        proc = self._run([self.claude_bin, "agents", "--json"], timeout=20)
        if proc.returncode != 0:
            raise ClaudeError(redact((proc.stderr or proc.stdout or "agents failed").strip()))
        try:
            parsed = json.loads(proc.stdout)
        except ValueError:
            raise ClaudeError("claude agents returned non-JSON output") from None
        if not isinstance(parsed, list):
            raise ClaudeError("claude agents returned an unexpected payload")
        sessions = [ClaudeSession.from_json(item) for item in parsed if isinstance(item, dict)]
        return [item for item in sessions if item.cwd == str(self.project_dir)]

    def find_session(self, *, session_id: str | None = None) -> ClaudeSession | None:
        sessions = self.list_sessions()
        for item in sessions:
            if session_id and item.session_id == session_id:
                return item
        ours = [item for item in sessions if item.name == self.session_name]
        if ours:
            return max(ours, key=lambda item: item.started_at or 0)
        return None

    def _start_argv(self, prompt: str, *, resume_id: str | None) -> list[str]:
        argv = [
            self.claude_bin,
            "--bg",
            "--name",
            self.session_name,
            "--permission-mode",
            "acceptEdits",
        ]
        if self.settings_path.exists():
            argv.extend(["--settings", str(self.settings_path)])
        if resume_id:
            argv.extend(["--resume", resume_id])
        # --bg has no -p; the prompt is positional and "--" protects a leading '-'.
        argv.extend(["--", prompt])
        return argv

    def start(self, prompt: str, *, resume_id: str | None = None) -> StartResult:
        active = [item for item in self.list_sessions() if item.active]
        if active:
            names = ", ".join(item.name or item.session_id or "session" for item in active[:3])
            return StartResult(False, f"Уже есть активная сессия в проекте: {names}")
        proc = self._run(
            self._start_argv(prompt, resume_id=resume_id), timeout=max(self.timeout, 120)
        )
        raw = redact((proc.stdout or "") + (proc.stderr or "")).strip()
        if proc.returncode != 0:
            return StartResult(False, raw or "claude --bg завершился с ошибкой", raw=raw)
        # The CLI prints the id; also poll the supported session list for the
        # canonical sessionId (needed for --resume).
        session: ClaudeSession | None = None
        for _ in range(20):
            try:
                session = self.find_session(session_id=resume_id)
            except ClaudeError:
                session = None
            if session is not None:
                break
            time.sleep(0.5)
        if session is None:
            return StartResult(True, raw or "Фоновая сессия запущена", session=None, raw=raw)
        reference = session.raw_id or parse_start_reference(raw) or session.name or ""
        return StartResult(
            True,
            f"Фоновая сессия запущена: {session.name or session.session_id or session.pid}",
            session={
                "pid": session.pid,
                "cwd": session.cwd,
                "kind": session.kind,
                "session_id": session.session_id,
                "name": session.name,
                "status": session.status,
                "started_at": session.started_at,
                "reference": reference,
            },
            raw=raw,
        )

    def stop(self, reference: str) -> tuple[bool, str]:
        proc = self._run([self.claude_bin, "stop", reference], timeout=30)
        text = redact(((proc.stdout or "") + (proc.stderr or "")).strip())
        return proc.returncode == 0, text or ("stopped" if proc.returncode == 0 else "stop failed")

    def logs(self, reference: str, *, max_chars: int = 3500) -> str:
        proc = self._run([self.claude_bin, "logs", reference], timeout=30)
        text = redact(((proc.stdout or "") + (proc.stderr or "")).strip())
        if proc.returncode != 0:
            raise ClaudeError(text or "logs failed")
        return text[-max_chars:]
