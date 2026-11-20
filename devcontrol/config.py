"""Configuration loading for BA Dev Control.

Secrets live in ``creds/telegram.env`` (mode 0600, not tracked by Git) or in
the process environment. Nothing in this module ever logs a token.
"""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CREDS = PROJECT_ROOT / "creds" / "telegram.env"
DEFAULT_SESSION_NAME = "BA autonomous"
TOKEN_RE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{20,}$")


class ConfigError(Exception):
    """Configuration is missing or unsafe."""


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ConfigError(f"{path} must not be group/world accessible; run: chmod 600 {path}")
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def default_runtime_dir() -> Path:
    """State lives outside the repo: var/ may be root-owned by Docker."""
    override = os.environ.get("DEVCONTROL_RUNTIME_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".local" / "state" / "ba-devcontrol"


def redact(text: str, token: str | None = None) -> str:
    """Remove configured and token-shaped secrets from logs/messages."""
    if token:
        text = text.replace(token, "<redacted>")
    return re.sub(r"\d{5,}:[A-Za-z0-9_-]{20,}", "<redacted>", text)


@dataclass(frozen=True)
class Config:
    token: str = field(repr=False)
    owner_id: int
    project_dir: Path
    runtime_dir: Path
    creds_path: Path
    session_name: str = DEFAULT_SESSION_NAME
    poll_timeout: int = 25
    monitor_interval: int = 20
    claude_bin: str = "claude"
    max_log_chars: int = 3500
    bot_username: str | None = None
    allow_autonomous: bool = False

    @property
    def settings_path(self) -> Path:
        return self.project_dir / "devcontrol" / "claude-settings.json"

    @property
    def prompt_path(self) -> Path:
        return self.project_dir / "devcontrol" / "prompts" / "autonomous.md"

    @classmethod
    def load(
        cls,
        *,
        creds_path: Path | None = None,
        project_dir: Path | None = None,
        require_secrets: bool = True,
    ) -> Config:
        project = Path(project_dir or PROJECT_ROOT).resolve()
        creds = Path(creds_path or DEFAULT_CREDS)
        values = _parse_env_file(creds)
        token = os.environ.get("TELEGRAM_BOT_TOKEN") or values.get("TELEGRAM_BOT_TOKEN", "")
        owner_raw = os.environ.get("TELEGRAM_OWNER_ID") or values.get("TELEGRAM_OWNER_ID", "")
        if require_secrets:
            if not token:
                raise ConfigError(
                    "TELEGRAM_BOT_TOKEN is missing; run "
                    f"python3 devcontrol/setup_token.py ({creds})"
                )
            if not TOKEN_RE.match(token):
                raise ConfigError("TELEGRAM_BOT_TOKEN has an unexpected format")
            if not owner_raw:
                raise ConfigError(
                    "TELEGRAM_OWNER_ID is missing; run python3 devcontrol/setup_token.py"
                )
        owner_id = 0
        if owner_raw:
            try:
                owner_id = int(owner_raw)
            except ValueError:
                raise ConfigError("TELEGRAM_OWNER_ID must be an integer") from None
            if owner_id <= 0:
                raise ConfigError("TELEGRAM_OWNER_ID must be positive")
        session_name = values.get("DEVCONTROL_SESSION_NAME", DEFAULT_SESSION_NAME)
        allow_raw = os.environ.get("DEVCONTROL_ALLOW_AUTONOMOUS") or values.get(
            "DEVCONTROL_ALLOW_AUTONOMOUS", "0"
        )
        return cls(
            token=token,
            owner_id=owner_id,
            project_dir=project,
            runtime_dir=default_runtime_dir(),
            creds_path=creds,
            session_name=session_name,
            poll_timeout=int(values.get("DEVCONTROL_POLL_TIMEOUT", "25")),
            monitor_interval=int(values.get("DEVCONTROL_MONITOR_INTERVAL", "20")),
            claude_bin=values.get("DEVCONTROL_CLAUDE_BIN", "claude"),
            max_log_chars=int(values.get("DEVCONTROL_MAX_LOG_CHARS", "3500")),
            bot_username=values.get("TELEGRAM_BOT_USERNAME"),
            allow_autonomous=allow_raw.strip().lower() in {"1", "true", "yes", "on"},
        )
