# ruff: noqa: S108, S603, S607, T201
"""Run BA tests in an isolated, secret-free Docker sandbox.

The agent may edit source/tests, but it must not execute them on the host or
in the web container (which holds .env/DB/Redis). This runner copies only
tracked/untracked non-ignored project files (never .env/certs/creds), starts
a private test PostgreSQL/Redis/Mailpit on an internal network, and runs
pytest in a read-only-rootfs container without docker.sock.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKTREE_ROOT = PROJECT_ROOT / ".autonomy" / "worktrees"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from devcontrol.config import default_runtime_dir  # noqa: E402

NODE_IMAGE = (
    "node:22-bookworm-slim@sha256:66cb8ef75184df13dc0dcf866330488996b485d404db60555756865300ced4a5"
)

ALLOWED_ROOTS = (
    ".claude/agents",
    ".claude/hooks",
    ".claude/settings.json",
    "apps",
    "autonomy",
    "config",
    "devcontrol",
    "games-src",
    "infra/scripts",
    "scripts",
    "sdk",
    "schemas",
    "static/src",
    "templates",
    "tests",
    "docs/audits",
    "docs/contracts",
    "docs/decisions",
    "docs/foundation",
    "docs/handoff",
    "docs/runbook",
    "docs/status",
    "docs/tasks",
    "compose.yml",
    "compose.dev-lite.yml",
    "compose.staging.yml",
    "compose.prod.yml",
    "conftest.py",
    "manage.py",
    "mypy.ini",
    "pytest.ini",
    "pyproject.toml",
    "ruff.toml",
)
FORBIDDEN_PARTS = {
    ".env",
    "certs",
    "creds",
    "var",
    "media",
    "staticfiles",
    ".git",
    "node_modules",
    "__pycache__",
}
SAFE_ENV_FILES = {".env.example", ".env.staging.example"}
REDIS_IMAGE = (
    "redis:8-alpine@sha256:7958cfbb9d152f87dadfbc89f1b0b15938f0b81ff8982feb327476f4911935c3"
)
MAILPIT_IMAGE = (
    "axllent/mailpit:latest@sha256:aef2aacc11f075ec0fb6874275ee4a421e688e11a96ebb296134d1735c7761ce"
)


class SandboxError(Exception):
    pass


def acquire_lock() -> int:
    state = default_runtime_dir()
    state.mkdir(parents=True, mode=0o700, exist_ok=True)
    fd = os.open(state / "sandbox.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise SandboxError("another sandbox test run is active") from None
    return fd


def cleanup_stale_projects() -> None:
    proc = subprocess.run(
        ["docker", "ps", "-a", "--format", '{{.Label "com.docker.compose.project"}}'],
        capture_output=True,
        text=True,
        check=False,
    )
    projects = sorted(
        {
            line.strip()
            for line in proc.stdout.splitlines()
            if line.strip().startswith("ba-sandbox-")
        }
    )
    for project in projects:
        subprocess.run(
            ["docker", "compose", "-p", project, "down", "-v", "--remove-orphans"],
            capture_output=True,
            timeout=120,
            check=False,
        )


def validate_source_root(value: str | None) -> Path:
    """Return the trusted project root or a validated isolated worktree.

    The agent-facing trusted runner is invoked from the main checkout with
    ``--source-root .`` (its cwd is a task worktree). Only real worktrees
    below ``.autonomy/worktrees`` are accepted; arbitrary host paths, the main
    checkout and symlink escapes are rejected before any file is copied.
    """
    task_root = os.environ.get("BA_TASK_WORKTREE")
    if not value and task_root:
        value = task_root
    if not value:
        return PROJECT_ROOT
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    root = candidate.resolve()
    if root == PROJECT_ROOT.resolve() or not root.is_relative_to(WORKTREE_ROOT.resolve()):
        raise SandboxError("source root must be an isolated .autonomy worktree")
    if task_root and root != Path(task_root).resolve():
        raise SandboxError("source root does not match the assigned task worktree")
    if root.is_symlink() or not root.is_dir():
        raise SandboxError("source root must be a real directory")
    git_marker = root / ".git"
    if git_marker.is_symlink() or not git_marker.is_file():
        raise SandboxError("source root is not a linked git worktree")
    try:
        marker = git_marker.read_text(encoding="utf-8").strip()
    except OSError:
        raise SandboxError("source root git metadata is unreadable") from None
    if not marker.startswith("gitdir:"):
        raise SandboxError("source root is not a linked git worktree")
    git_dir = Path(marker.split(":", 1)[1].strip()).resolve()
    expected_root = (PROJECT_ROOT / ".git" / "worktrees").resolve()
    if not git_dir.is_relative_to(expected_root):
        raise SandboxError("source root git metadata points outside the main repository")
    return root


def validate_path(value: str | None, source_root: Path = PROJECT_ROOT) -> str | None:
    if not value:
        return None
    node = value.split("::", 1)[0]
    path = Path(node)
    if path.is_absolute() or ".." in path.parts:
        raise SandboxError("path must be relative and must not contain '..'")
    if not path.parts or path.parts[0] not in {"tests", "apps"}:
        raise SandboxError("test path must start with tests/ or apps/")
    if not (source_root / path).exists():
        raise SandboxError(f"test path does not exist: {path}")
    if value.count("::") > 1:
        raise SandboxError("only one ::node selector is allowed")
    return value


def project_files(source_root: Path = PROJECT_ROOT) -> list[Path]:
    proc = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=source_root,
        capture_output=True,
        text=True,
        check=True,
    )
    files: list[Path] = []
    for name in proc.stdout.split("\0"):
        if not name:
            continue
        rel = Path(name)
        if rel.is_absolute() or ".." in rel.parts:
            continue
        if rel.name == ".env" or (rel.name.startswith(".env.") and rel.name not in SAFE_ENV_FILES):
            continue
        if any(part in FORBIDDEN_PARTS for part in rel.parts):
            continue
        if not any(name == root or name.startswith(root + "/") for root in ALLOWED_ROOTS):
            continue
        source = source_root / rel
        if not source.is_file() or source.is_symlink():
            continue
        files.append(rel)
    return files


def copy_project(code_dir: Path, source_root: Path = PROJECT_ROOT) -> int:
    count = 0
    for rel in project_files(source_root):
        destination = code_dir / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / rel, destination)
        count += 1
    for name in ("staticfiles", "media", "var"):
        (code_dir / name).mkdir(mode=0o755, exist_ok=True)
    return count


def compose_document(project: str, code_dir: Path, command: list[str]) -> str:
    image = f"ba/app:{os.environ.get('IMAGE_TAG', 'dev')}"
    environment = {
        "DJANGO_SETTINGS_MODULE": "config.settings.dev",
        "DJANGO_SECRET_KEY": "test-only-not-a-secret",
        "DJANGO_ALLOWED_HOSTS": "testserver,localhost,127.0.0.1",
        "DEBUG": "1",
        "DATABASE_URL": "postgres://ba:test-only@db:5432/ba_test",
        "REDIS_CACHE_URL": "redis://redis-cache:6379/1",
        "REDIS_BROKER_URL": "redis://redis-broker:6379/2",
        "CELERY_BROKER_URL": "redis://redis-broker:6379/2",
        "REDIS_THROTTLE_URL": "redis://redis-throttle:6379/0",
        "EMAIL_HOST": "mailpit",
        "EMAIL_PORT": "1025",
        "EMAIL_USE_TLS": "0",
        "DEFAULT_FROM_EMAIL": "no-reply@test.invalid",
        "PORTAL_ORIGIN": "https://portal.test:8443",
        "GAMES_DOMAIN": "games.test",
        "BA_BACKUP_CHECK_ENABLED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
        "HOME": "/tmp",
        "TMPDIR": "/tmp",
    }
    env_yaml = "\n".join(f"      {key}: {json.dumps(value)}" for key, value in environment.items())
    command_json = json.dumps(command)
    return f"""name: {project}
services:
  db:
    image: postgres:18
    environment:
      POSTGRES_DB: "ba_test"
      POSTGRES_USER: "ba"
      POSTGRES_PASSWORD: "test-only"
    networks: [testnet]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ba -d ba_test"]
      interval: 3s
      timeout: 3s
      retries: 20

  redis-cache:
    image: {REDIS_IMAGE}
    command: [
      "redis-server", "--maxmemory", "64mb", "--maxmemory-policy", "allkeys-lru",
      "--save", "", "--appendonly", "no"
    ]
    networks: [testnet]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 3s
      timeout: 3s
      retries: 20

  redis-broker:
    image: {REDIS_IMAGE}
    command: [
      "redis-server", "--maxmemory", "64mb", "--maxmemory-policy", "noeviction",
      "--save", "", "--appendonly", "no"
    ]
    networks: [testnet]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 3s
      timeout: 3s
      retries: 20

  redis-throttle:
    image: {REDIS_IMAGE}
    command: [
      "redis-server", "--maxmemory", "64mb", "--maxmemory-policy", "noeviction",
      "--save", "", "--appendonly", "no"
    ]
    networks: [testnet]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 3s
      timeout: 3s
      retries: 20

  mailpit:
    image: {MAILPIT_IMAGE}
    networks: [testnet]

  test:
    image: {image}
    user: "1000:1000"
    working_dir: /app
    entrypoint: ["/app/infra/scripts/entrypoint.sh"]
    command: {command_json}
    environment:
{env_yaml}
    volumes:
      - {json.dumps(str(code_dir) + ":/app")}
    networks: [testnet]
    depends_on:
      db: {{ condition: service_healthy }}
      redis-cache: {{ condition: service_healthy }}
      redis-broker: {{ condition: service_healthy }}
      redis-throttle: {{ condition: service_healthy }}
      mailpit: {{ condition: service_started }}
    read_only: true
    tmpfs:
      - "/tmp:rw,size=512m,mode=1777"
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    pids_limit: 256
    mem_limit: 2g
    cpus: "2.0"
    stop_grace_period: 10s

networks:
  testnet:
    internal: true
"""


def js_compose_document(project: str, code_dir: Path) -> str:
    """Node-only test sandbox: no Python services, secrets or external network."""
    return f"""name: {project}
services:
  test:
    image: {NODE_IMAGE}
    user: "1000:1000"
    working_dir: /app
    environment:
      HOME: /tmp
      NODE_ENV: test
    command: ["/bin/sh", "-c", "node --test tests/js/*.test.mjs"]
    volumes:
      - {json.dumps(str(code_dir) + ":/app:ro")}
    networks: [testnet]
    read_only: true
    tmpfs:
      - "/tmp:rw,size=256m,mode=1777"
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    pids_limit: 128
    mem_limit: 1g
    cpus: "1.0"
    stop_grace_period: 10s

networks:
  testnet:
    internal: true
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run BA tests in a secret-free Docker sandbox")
    parser.add_argument("path", nargs="?", help="tests/... or apps/... path (optional)")
    parser.add_argument(
        "--source-root",
        help="trusted isolated worktree below .autonomy/worktrees (agent use)",
    )
    parser.add_argument(
        "--tool",
        choices=("pytest", "makemigrations-check", "ruff", "mypy", "js"),
        default="pytest",
        help="check to run inside the sandbox",
    )
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args(argv)
    try:
        source_root = validate_source_root(args.source_root)
        test_path = validate_path(args.path, source_root)
    except SandboxError as exc:
        print(f"sandbox: {exc}", file=sys.stderr)
        return 2

    sandbox_dir = default_runtime_dir() / "sandbox" / uuid.uuid4().hex
    code_dir = sandbox_dir / "code"
    compose_path = sandbox_dir / "compose.yml"
    project = f"ba-sandbox-{uuid.uuid4().hex[:12]}"
    if args.tool == "pytest":
        command = ["pytest", "-q", test_path] if test_path else ["pytest", "-q"]
    elif args.tool == "makemigrations-check":
        command = ["python", "manage.py", "makemigrations", "--check", "--dry-run"]
    elif args.tool == "ruff":
        # Mirror the project's `make lint` target. The sandbox also carries
        # agent harness files (.claude/) that are intentionally outside the
        # product quality gate; linting "." makes every candidate fail on
        # those unrelated files before its own diff is considered.
        command = [
            "/bin/sh",
            "-c",
            "ruff check apps config tests devcontrol && "
            "ruff format --check apps config tests devcontrol",
        ]
    elif args.tool == "mypy":
        command = ["mypy"]
    else:
        command = ["/bin/sh", "-c", "node --test tests/js/*.test.mjs"]
    lock_fd: int | None = None
    try:
        lock_fd = acquire_lock()
        cleanup_stale_projects()
        sandbox_root = sandbox_dir.parent
        sandbox_root.mkdir(parents=True, mode=0o700, exist_ok=True)
        sandbox_root.chmod(0o700)
        sandbox_dir.mkdir(mode=0o700)
        code_dir.mkdir(mode=0o700)
        copied = copy_project(code_dir, source_root)
        if args.tool == "js":
            compose_path.write_text(js_compose_document(project, code_dir), encoding="utf-8")
        else:
            compose_path.write_text(compose_document(project, code_dir, command), encoding="utf-8")
        print(
            f"sandbox: {project}, {copied} files, source={source_root}, tool={args.tool}, "
            f"no .env/certs/creds, internal network, test-only services",
            file=sys.stderr,
        )
        proc = subprocess.run(
            [
                "docker",
                "compose",
                "-p",
                project,
                "-f",
                str(compose_path),
                "run",
                "--rm",
                "-T",
                "test",
            ],
            cwd=code_dir,
            timeout=args.timeout,
            check=False,
        )
        return proc.returncode
    except SandboxError as exc:
        print(f"sandbox: {exc}", file=sys.stderr)
        return 3
    except subprocess.TimeoutExpired:
        print("sandbox: test run timed out", file=sys.stderr)
        return 124
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"sandbox: {exc}", file=sys.stderr)
        return 2
    finally:
        subprocess.run(
            [
                "docker",
                "compose",
                "-p",
                project,
                "-f",
                str(compose_path),
                "down",
                "-v",
                "--remove-orphans",
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            timeout=120,
            check=False,
        )
        shutil.rmtree(sandbox_dir, ignore_errors=True)
        if lock_fd is not None:
            os.close(lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
