"""Static validation for the low-risk VPS transfer package.

These tests only read the packaged unit/template/runbook. They never start
systemd, Docker, Claude or the orchestrator, and they never need secrets.
"""

from __future__ import annotations

import configparser
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DIR = REPO_ROOT / "autonomy" / "vps"
UNIT_PATH = PACKAGE_DIR / "ba-autonomy-orchestrator.service"
ENV_PATH = PACKAGE_DIR / "orchestrator.env.example"
RUNBOOK_PATH = PACKAGE_DIR / "README.md"
WSL_DIR = PACKAGE_DIR / "wsl"
WSL_SERVICE_PATH = WSL_DIR / "ba-autonomy-orchestrator.service"
WSL_TIMER_PATH = WSL_DIR / "ba-autonomy-orchestrator.timer"

# Values that are tuning, not credentials. BA_MAX_TOKENS contains "TOKEN" but
# is a numeric budget, so the allowlist must win over the name heuristic.
NON_SECRET_KEYS = frozenset(
    {
        "BA_ARCHITECT_MODEL",
        "BA_DEVELOPER_MODEL",
        "BA_QA_MODEL",
        "BA_REVIEWER_MODEL",
        "BA_MODEL_TIMEOUT",
        "BA_MAX_TASKS_PER_RUN",
        "BA_MAX_RUN_SECONDS",
        "BA_MAX_TOKENS",
        "BA_MAX_COST_USD",
        "TELEGRAM_CHAT_ID",
        "TELEGRAM_PROXY",
        "PYTHONUNBUFFERED",
        "PATH",
    }
)
SECRET_MARKERS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "PRIVATE_KEY",
    "API_KEY",
    "AUTH_KEY",
    "ACCESS_KEY",
    "CREDENTIAL",
)
TOKEN_PATTERNS = (
    # Telegram bot token.
    re.compile(r"(?<!\d)\d{5,}:[A-Za-z0-9_-]{20,}(?!\w)"),
    # Anthropic/OpenAI-style API keys.
    re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{16,}\b"),
    # GitHub tokens.
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    # AWS access key ids.
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    # Private key material.
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
URL_WITH_CREDENTIALS = re.compile(r"://[^/\s:@]+:[^/\s@]+@")


def _read(path: Path) -> str:
    assert path.is_file(), f"missing package file: {path.relative_to(REPO_ROOT)}"
    assert not path.is_symlink(), f"package file must not be a symlink: {path.name}"
    return path.read_text(encoding="utf-8")


def _env_assignments(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _is_secret_key(key: str) -> bool:
    if key in NON_SECRET_KEYS:
        return False
    upper = key.upper()
    return any(marker in upper for marker in SECRET_MARKERS)


def _assert_no_tokens(text: str, source: str) -> None:
    for pattern in TOKEN_PATTERNS:
        if pattern.search(text):
            pytest.fail(f"token-like value found in {source}; remove it before packaging")


def test_package_files_exist() -> None:
    for path in (UNIT_PATH, ENV_PATH, RUNBOOK_PATH):
        assert path.is_file(), f"missing package file: {path.relative_to(REPO_ROOT)}"
        assert not path.is_symlink(), f"package file must not be a symlink: {path.name}"


def test_unit_parses_and_runs_the_existing_orchestrator() -> None:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    parser.read_string(_read(UNIT_PATH))

    assert {"Unit", "Service", "Install"} <= set(parser.sections())
    service = parser["Service"]
    exec_start = service["ExecStart"]
    assert exec_start.split() == [
        "/usr/bin/python3",
        "-m",
        "autonomy.orchestrator",
        "run",
        "--max-tasks",
        "1",
    ]
    assert service["Type"] == "oneshot"
    assert service["WorkingDirectory"].startswith("%h/")
    assert parser["Install"]["WantedBy"] == "default.target"

    # The unit must call the existing module, not a copy or wrapper.
    assert (REPO_ROOT / "autonomy" / "orchestrator.py").is_file()
    assert "--dangerously-skip-permissions" not in exec_start
    for metachar in ("|", ";", "&", "$(", "`"):
        assert metachar not in exec_start


def test_unit_does_not_auto_deploy_or_auto_start() -> None:
    raw = _read(UNIT_PATH)
    for marker in (
        "ExecStartPre",
        "ExecStartPost",
        "ExecReload",
        "Restart=",
        "git clone",
        "docker",
        "compose",
        "make up",
        "systemctl",
        "deploy",
    ):
        assert marker not in raw, f"unit must not contain {marker!r}"
    assert "WantedBy=default.target" in raw


def test_unit_references_only_external_env_files() -> None:
    raw = _read(UNIT_PATH)
    env_files = re.findall(r"^EnvironmentFile=(-?)(\S+)", raw, re.MULTILINE)
    assert env_files, "unit must load external environment files"
    for _, path in env_files:
        assert path.startswith("%h/.config/ba/"), path
        assert path.endswith(".env"), path


def test_unit_contains_no_secret_assignments_or_tokens() -> None:
    raw = _read(UNIT_PATH)
    for key, value in re.findall(r"^Environment=(\w+)=(.*)$", raw, re.MULTILINE):
        assert key in NON_SECRET_KEYS, f"unexpected unit environment key {key}"
        assert not _is_secret_key(key), f"unit must not set secret key {key}"
        _assert_no_tokens(value, "unit Environment")
    _assert_no_tokens(raw, "unit")


def test_env_template_contains_no_secrets() -> None:
    text = _read(ENV_PATH)
    assignments = _env_assignments(text)
    assert set(assignments) <= NON_SECRET_KEYS, "template exposes an unexpected key"
    for key, value in assignments.items():
        assert not _is_secret_key(key), f"template must not set secret key {key}"
        assert not URL_WITH_CREDENTIALS.search(value), f"credentials in URL for {key}"
        _assert_no_tokens(value, "env template value")
    _assert_no_tokens(text, "env template")


def test_env_template_secret_keys_are_comment_only() -> None:
    text = _read(ENV_PATH)
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key = line.split("=", 1)[0].strip()
        assert not _is_secret_key(key), f"secret key must stay commented: {key}"
    folded = text.casefold()
    assert "deepseek.env" in folded
    assert "creds/telegram.env" in folded
    assert "0600" in folded


def test_runbook_covers_backup_restore_and_prerequisites() -> None:
    text = _read(RUNBOOK_PATH)
    folded = text.casefold()
    for fragment in (
        ".autonomy/state.json",
        ".autonomy/evidence",
        ".autonomy/events.jsonl",
        "sha256sum",
        "systemctl --user stop",
        "systemctl --user start ba-autonomy-orchestrator.service",
        "journalctl --user",
        "enable-linger",
    ):
        assert fragment in text, f"runbook is missing {fragment!r}"
    assert "предпосылки" in folded
    assert "deploy" in folded
    assert "docker" in folded
    assert "секрет" in folded


def test_package_has_no_secret_artifacts() -> None:
    forbidden_names = {".env", "telegram.env", "deepseek.env", "id_rsa", "id_ed25519"}
    for path in PACKAGE_DIR.rglob("*"):
        if not path.is_file():
            continue
        assert not path.is_symlink(), f"unexpected symlink: {path.name}"
        assert path.name not in forbidden_names, f"secret-like file: {path.name}"
        assert path.suffix not in {".pem", ".key", ".p12", ".pfx"}, path.name
        _assert_no_tokens(path.read_text(encoding="utf-8"), path.name)


def _parse_unit(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    parser.read_string(_read(path))
    return parser


def test_wsl_heartbeat_files_exist() -> None:
    for path in (WSL_SERVICE_PATH, WSL_TIMER_PATH):
        assert path.is_file(), f"missing WSL heartbeat file: {path.name}"
        assert not path.is_symlink(), f"WSL heartbeat file must not be a symlink: {path.name}"


def test_wsl_service_runs_the_existing_orchestrator() -> None:
    parser = _parse_unit(WSL_SERVICE_PATH)
    service = parser["Service"]
    assert service["ExecStart"].split() == [
        "/home/elkinva/projects/ba/.venv/bin/python",
        "-m",
        "autonomy.orchestrator",
        "run",
        "--max-tasks",
        "1",
    ]
    assert service["WorkingDirectory"] == "/home/elkinva/projects/ba"
    assert service["Type"] == "oneshot"
    assert "--dangerously-skip-permissions" not in service["ExecStart"]
    assert (REPO_ROOT / "autonomy" / "orchestrator.py").is_file()
    env_files = re.findall(r"^EnvironmentFile=(-?)(\S+)", _read(WSL_SERVICE_PATH), re.MULTILINE)
    assert env_files
    for _, path in env_files:
        assert path.startswith("/home/elkinva/.config/ba/"), path
        assert path.endswith(".env"), path
    for key, value in re.findall(
        r"^Environment=(\w+)=(.*)$", _read(WSL_SERVICE_PATH), re.MULTILINE
    ):
        assert key in NON_SECRET_KEYS, f"unexpected WSL unit environment key {key}"
        _assert_no_tokens(value, "WSL unit Environment")


def test_wsl_timer_is_bounded_and_uses_the_service() -> None:
    parser = _parse_unit(WSL_TIMER_PATH)
    timer = parser["Timer"]
    assert timer["Unit"] == "ba-autonomy-orchestrator.service"
    assert timer["OnBootSec"] == "5min"
    assert timer["OnUnitActiveSec"] == "30min"
    assert timer["Persistent"] == "true"
    assert parser["Install"]["WantedBy"] == "timers.target"
