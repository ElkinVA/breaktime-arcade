"""Minimal isolation for autonomous Claude child processes.

This module provides two application-level controls:

* an explicit environment allowlist for the child process, so database,
  Telegram, AWS, Docker, CI and other unrelated secrets are never inherited;
* a worktree-only working-directory validator that rejects the main checkout,
  relative/escaping paths, symlink escapes, secret files/directories and
  socket files (including ``docker.sock``).

It is deliberately *not* an OS sandbox. The child still runs as the host user
and can reach absolute host paths through tools that the hooks do not cover.
That residual gap is tracked as technical debt R-040 in
``docs/risks/RISK_REGISTER.md``.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from pathlib import Path

# Environment variables the model process legitimately needs. Everything else
# is dropped, regardless of whether it looks secret.
ALLOWED_ENV_KEYS = frozenset(
    {
        # Model/provider routing and authentication (the only credentials the
        # child is allowed to receive).
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "ANTHROPIC_SMALL_FAST_MODEL",
        "CLAUDE_CODE_SUBAGENT_MODEL",
        # Process basics.
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LC_MESSAGES",
        "LC_NUMERIC",
        "LC_TIME",
        "TERM",
        "TZ",
        "TMPDIR",
        "PATH",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
        # Non-secret network/CA settings. Proxy URLs with userinfo are dropped
        # by _safe_env_value below.
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
        "all_proxy",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "NODE_EXTRA_CA_CERTS",
    }
)

# Explicitly forbidden namespaces even if a key were accidentally added to the
# allowlist. This is defense in depth; the allowlist is still authoritative.
FORBIDDEN_ENV_PREFIXES = (
    "AWS_",
    "AZURE_",
    "BOTO",
    "CELERY_",
    "CI",
    "DATABASE_",
    "DJANGO_",
    "DOCKER_",
    "EMAIL_",
    "GCP_",
    "GH_",
    "GITHUB_",
    "GITLAB_",
    "GPG_",
    "GOOGLE_",
    "KUBERNETES_",
    "MAIL_",
    "NPM_",
    "OPENAI_",
    "PG",
    "PIP_",
    "POSTGRES_",
    "PYPI_",
    "REDIS_",
    "S3_",
    "SENTRY_",
    "SLACK_",
    "SMTP_",
    "SSH_",
    "STRIPE_",
    "TELEGRAM_",
    "TWILIO_",
    "UV_",
    "VAULT_",
)

FORBIDDEN_ENV_MARKERS = (
    "ACCESS_KEY",
    "API_KEY",
    "AUTH_KEY",
    "CONNECTION_STRING",
    "CREDENTIAL",
    "DSN",
    "PASSWORD",
    "PASSWD",
    "PRIVATE_KEY",
    "SECRET",
    "TOKEN",
)

# The model credentials are expected to contain "TOKEN"/"API_KEY"; keep them
# exempt from the marker heuristic while still requiring an allowlist entry.
MODEL_CREDENTIAL_KEYS = frozenset({"ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"})

PROXY_ENV_KEYS = frozenset(
    {
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
        "all_proxy",
    }
)

# Fixed values appended after filtering. They prevent git from using the
# ext:: transport or prompting for credentials.
FIXED_ENV = {
    "GIT_ALLOW_PROTOCOL": "ssh,https",
    "GIT_TERMINAL_PROMPT": "0",
}

DEFAULT_PATH = "/usr/local/bin:/usr/bin:/bin"

SAFE_ENV_FILES = frozenset({".env.example", ".env.staging.example"})
SECRET_DIR_NAMES = frozenset({".aws", ".docker", ".gnupg", ".ssh", "certs", "creds", "secrets"})
SECRET_FILE_NAMES = frozenset({"docker.sock", "id_ecdsa", "id_ed25519", "id_rsa"})
SKIP_DIR_NAMES = frozenset(
    {".git", ".venv", "__pycache__", "media", "node_modules", "staticfiles", "var"}
)

_SOCKET = getattr(stat, "S_ISSOCK", None)


class SandboxError(RuntimeError):
    """A child process requested an unsafe environment or working directory."""


def is_forbidden_env_key(key: str) -> bool:
    """Return True when a variable name belongs to a forbidden namespace."""
    if key in MODEL_CREDENTIAL_KEYS:
        return False
    upper = key.upper()
    if upper.startswith(FORBIDDEN_ENV_PREFIXES):
        return True
    return any(marker in upper for marker in FORBIDDEN_ENV_MARKERS)


def _safe_env_value(key: str, value: str) -> bool:
    if not value:
        return True
    # Proxy URLs may embed user:password credentials; drop those entirely.
    return not (key in PROXY_ENV_KEYS and "@" in value)


def build_child_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build the explicit allowlisted environment for a Claude child process.

    ``base`` defaults to :data:`os.environ`. Only :data:`ALLOWED_ENV_KEYS` are
    copied; forbidden namespaces and proxy URLs carrying credentials are
    dropped. Fixed non-secret git guards are always added.
    """
    source: Mapping[str, str] = os.environ if base is None else base
    env: dict[str, str] = {}
    for key in sorted(ALLOWED_ENV_KEYS):
        value = source.get(key)
        if not isinstance(value, str):
            continue
        if is_forbidden_env_key(key):
            continue
        if not _safe_env_value(key, value):
            continue
        env[key] = value
    env.setdefault("PATH", DEFAULT_PATH)
    env.setdefault("HOME", str(Path.home()))
    env.update(FIXED_ENV)
    # Docker-like endpoints must never be inherited even if a future allowlist
    # entry is added by mistake.
    env.pop("DOCKER_HOST", None)
    env.pop("DOCKER_CONTEXT", None)
    return env


# Compatibility aliases for callers/tests that use a shorter name.
filter_environment = build_child_env
filter_env = build_child_env


def _stat_mode(path: Path) -> int | None:
    try:
        return path.lstat().st_mode
    except OSError:
        return None


def _is_socket(path: Path) -> bool:
    mode = _stat_mode(path)
    return bool(mode is not None and _SOCKET is not None and _SOCKET(mode))


def _secret_file_name(name: str) -> bool:
    if name in SAFE_ENV_FILES:
        return False
    if name == ".env" or name.startswith(".env."):
        return True
    return name in SECRET_FILE_NAMES


def _symlink_escape(path: Path, worktree_root: Path) -> bool:
    try:
        target = path.resolve(strict=False)
    except OSError:
        return True
    if not target.is_relative_to(worktree_root):
        return True
    if target == worktree_root:
        return True
    return _secret_file_name(target.name) or any(part in SECRET_DIR_NAMES for part in target.parts)


def _secret_dir_unsafe(path: Path) -> bool:
    """A tracked placeholder such as ``certs/.gitkeep`` is not a secret."""
    placeholders = {".gitkeep", ".gitignore"}
    try:
        entries = list(os.scandir(path))
    except OSError:
        return True
    if not entries:
        return True
    return any(entry.name not in placeholders for entry in entries)


def find_secret_entries(root: Path) -> list[Path]:
    """Return unsafe entries found below ``root`` (recursive, no symlink follow)."""
    root = Path(root).resolve()
    findings: list[Path] = []

    def scan(directory: Path) -> None:
        try:
            entries = list(os.scandir(directory))
        except OSError:
            findings.append(directory)
            return
        for entry in entries:
            name = entry.name
            path = Path(entry.path)
            if _secret_file_name(name):
                findings.append(path)
                continue
            if entry.is_symlink():
                if _symlink_escape(path, root):
                    findings.append(path)
                continue
            if _is_socket(path):
                findings.append(path)
                continue
            if entry.is_dir(follow_symlinks=False):
                if name in SECRET_DIR_NAMES:
                    if _secret_dir_unsafe(path):
                        findings.append(path)
                    continue
                if name in SKIP_DIR_NAMES:
                    continue
                scan(path)

    scan(root)
    return findings


def worktree_has_secret_files(root: Path) -> bool:
    """True when the worktree contains a secret file/dir or socket entry."""
    return bool(find_secret_entries(root))


def validate_worktree_cwd(
    cwd: Path | str | None,
    *,
    project_root: Path,
    worktree_root: Path,
) -> Path:
    """Validate that a model process runs only inside an isolated worktree.

    Returns the resolved path. Raises :class:`SandboxError` for a missing or
    relative path, the main checkout/sibling repositories, symlink escapes and
    worktrees that contain secret files, secret directories or socket files.
    """
    if cwd is None:
        raise SandboxError("model cwd is required")
    candidate = Path(cwd).expanduser()
    if not candidate.is_absolute():
        raise SandboxError("model cwd must be an absolute path inside a worktree")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise SandboxError(f"model cwd does not exist: {candidate}") from exc

    project = Path(project_root).resolve()
    worktrees = Path(worktree_root).resolve()
    if resolved in (project, worktrees):
        raise SandboxError("model cwd must be a task worktree, not the project root")
    if not resolved.is_relative_to(worktrees):
        raise SandboxError("model cwd must be inside the isolated worktree root")
    if any(part in SECRET_DIR_NAMES for part in resolved.parts):
        raise SandboxError("model cwd must not be inside a secret directory")
    # Scan the whole task worktree, not just the requested subdirectory, so a
    # nested cwd cannot hide a sibling secret file.
    task_root = worktrees / resolved.relative_to(worktrees).parts[0]
    findings = find_secret_entries(task_root)
    if findings:
        sample = ", ".join(str(path.relative_to(task_root)) for path in findings[:3])
        raise SandboxError(f"worktree contains forbidden secret/socket entries: {sample}")
    return resolved


# Short alias used by early callers.
validate_cwd = validate_worktree_cwd
