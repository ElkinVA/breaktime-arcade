"""Isolation tests for autonomous Claude child processes.

These tests exercise only the application-level controls: the explicit
environment allowlist and the worktree-only working-directory validator. They
never start Claude, Docker or the network.
"""

from __future__ import annotations

import json
import socket
import tempfile
from pathlib import Path

import autonomy.runner as runner_module
import pytest
from autonomy.runner import ClaudeRunner, RunnerError
from autonomy.sandbox import (
    SandboxError,
    build_child_env,
    is_forbidden_env_key,
    validate_worktree_cwd,
    worktree_has_secret_files,
)

SECRET_ENV = {
    "DATABASE_URL": "postgres://user:hunter2@db:5432/ba",
    "POSTGRES_PASSWORD": "pg-secret",
    "REDIS_URL": "redis://redis:6379/20",
    "CELERY_BROKER_URL": "redis://redis:6379/21",
    "DJANGO_SECRET_KEY": "django-secret",
    "TELEGRAM_BOT_TOKEN": "12345678:abcdefghijklmnopqrstuvwxyzABCDE",
    "TELEGRAM_OWNER_ID": "111",
    "AWS_ACCESS_KEY_ID": "AKIAEXAMPLE",
    "AWS_SECRET_ACCESS_KEY": "aws-secret",
    "DOCKER_HOST": "unix:///var/run/docker.sock",
    "GITHUB_TOKEN": "ghp_example",
    "SENTRY_DSN": "https://public@example.invalid/1",
    "UNRELATED_VARIABLE": "unrelated",
}


def _layout(tmp_path: Path) -> tuple[Path, Path, Path]:
    project = tmp_path / "project"
    worktrees = project / ".autonomy" / "worktrees"
    worktree = worktrees / "AUTONOMY-TASK-abc123" / "ba"
    worktree.mkdir(parents=True)
    return project, worktrees, worktree


def _payload(model: str) -> str:
    return json.dumps(
        {
            "modelUsage": {model: {"inputTokens": 10, "outputTokens": 5}},
            "session_id": "session-test",
            "result": "{}",
        }
    )


class _Completed:
    def __init__(self, model: str) -> None:
        self.returncode = 0
        self.stdout = _payload(model)
        self.stderr = ""


def test_build_child_env_uses_explicit_allowlist() -> None:
    base = {
        "ANTHROPIC_AUTH_TOKEN": "model-token",
        "HOME": "/home/test",
        "PATH": "/usr/bin",
        **SECRET_ENV,
    }

    env = build_child_env(base)

    assert env["ANTHROPIC_AUTH_TOKEN"] == "model-token"
    assert env["HOME"] == "/home/test"
    assert env["PATH"] == "/usr/bin"
    assert env["GIT_ALLOW_PROTOCOL"] == "ssh,https"
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    for key in SECRET_ENV:
        assert key not in env, f"{key} leaked into the child environment"


def test_forbidden_env_namespaces_are_rejected() -> None:
    for key in (
        "TELEGRAM_BOT_TOKEN",
        "AWS_SECRET_ACCESS_KEY",
        "DATABASE_URL",
        "DJANGO_SECRET_KEY",
        "DOCKER_HOST",
        "GITHUB_TOKEN",
        "SOME_PASSWORD",
    ):
        assert is_forbidden_env_key(key), key
    assert not is_forbidden_env_key("ANTHROPIC_AUTH_TOKEN")
    assert not is_forbidden_env_key("ANTHROPIC_API_KEY")
    assert not is_forbidden_env_key("LANG")


def test_proxy_urls_with_credentials_are_dropped() -> None:
    env = build_child_env(
        {
            "HTTPS_PROXY": "http://user:password@proxy.invalid:8080",
            "HTTP_PROXY": "http://proxy.invalid:8080",
            "NO_PROXY": "localhost,127.0.0.1",
        }
    )
    assert "HTTPS_PROXY" not in env
    assert env["HTTP_PROXY"] == "http://proxy.invalid:8080"
    assert env["NO_PROXY"] == "localhost,127.0.0.1"


def test_validate_worktree_cwd_accepts_task_worktree(tmp_path: Path) -> None:
    project, worktrees, worktree = _layout(tmp_path)

    assert (
        validate_worktree_cwd(worktree, project_root=project, worktree_root=worktrees)
        == worktree.resolve()
    )


def test_validate_worktree_cwd_rejects_main_relative_and_outside(tmp_path: Path) -> None:
    project, worktrees, _worktree = _layout(tmp_path)
    (project / "apps").mkdir()
    sibling = tmp_path / "ai-dev"
    sibling.mkdir()

    for candidate in (
        project,
        worktrees,
        project / "apps",
        sibling,
        Path("relative/path"),
        tmp_path / "missing",
    ):
        with pytest.raises(SandboxError):
            validate_worktree_cwd(candidate, project_root=project, worktree_root=worktrees)


def test_validate_worktree_cwd_rejects_symlink_escape(tmp_path: Path) -> None:
    project, worktrees, worktree = _layout(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")

    link = worktree / "escape"
    link.symlink_to(outside, target_is_directory=True)

    assert worktree_has_secret_files(worktree)
    with pytest.raises(SandboxError):
        validate_worktree_cwd(worktree, project_root=project, worktree_root=worktrees)

    cwd_link = worktrees / "cwd-link"
    cwd_link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(SandboxError):
        validate_worktree_cwd(cwd_link, project_root=project, worktree_root=worktrees)


def test_worktree_scan_rejects_nested_secret_files_and_dirs(tmp_path: Path) -> None:
    _project, _worktrees, worktree = _layout(tmp_path)
    nested = worktree / "apps" / "nested"
    nested.mkdir(parents=True)
    (nested / ".env").write_text("SECRET=1", encoding="utf-8")
    assert worktree_has_secret_files(worktree)

    (nested / ".env").unlink()
    assert not worktree_has_secret_files(worktree)
    for name in ("certs", "creds", "secrets", ".ssh", ".aws"):
        target = worktree / name
        target.mkdir()
        assert worktree_has_secret_files(worktree), name
        target.rmdir()
    assert not worktree_has_secret_files(worktree)


def test_tracked_secret_dir_placeholder_is_allowed(tmp_path: Path) -> None:
    _project, _worktrees, worktree = _layout(tmp_path)
    certs = worktree / "certs"
    certs.mkdir()
    (certs / ".gitkeep").write_text("", encoding="utf-8")
    assert not worktree_has_secret_files(worktree)

    (certs / "server.pem").write_text("not-a-real-cert", encoding="utf-8")
    assert worktree_has_secret_files(worktree)


def test_validate_worktree_cwd_rejects_socket_file(tmp_path: Path) -> None:
    project, worktrees, worktree = _layout(tmp_path)
    socket_path = worktree / "docker.sock"
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        # AF_UNIX paths are limited to ~100 bytes; bind in a short temp dir and
        # move the socket into the (possibly longer) pytest worktree path.
        with tempfile.TemporaryDirectory(prefix="ba-sock-") as short_dir:
            short_path = Path(short_dir) / "s"
            sock.bind(str(short_path))
            short_path.rename(socket_path)
        assert worktree_has_secret_files(worktree)
        with pytest.raises(SandboxError):
            validate_worktree_cwd(worktree, project_root=project, worktree_root=worktrees)
    finally:
        sock.close()


def test_runner_passes_filtered_env_and_validated_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, worktrees, worktree = _layout(tmp_path)
    captured: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> _Completed:
        captured["argv"] = argv
        captured["env"] = kwargs["env"]
        captured["cwd"] = kwargs["cwd"]
        return _Completed(runner_module.DEVELOPER_MODEL)

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)
    monkeypatch.setattr(runner_module, "EVIDENCE_ROOT", tmp_path / "evidence")
    for key, value in SECRET_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "model-token")

    runner = ClaudeRunner(root=project, worktree_root=worktrees)
    result = runner.developer("prompt", cwd=worktree)

    assert result.returncode == 0
    assert captured["cwd"] == worktree.resolve()
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["ANTHROPIC_AUTH_TOKEN"] == "model-token"
    for key in SECRET_ENV:
        assert key not in env, f"{key} leaked into the child environment"

    argv = captured["argv"]
    assert isinstance(argv, list)
    assert argv[0] == "claude"
    assert argv[argv.index("--agent") + 1] == "autonomy-developer"
    assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"
    assert (
        "Bash(python3 devcontrol/sandbox/run_tests.py:*)" in argv[argv.index("--allowedTools") + 1]
    )


@pytest.mark.parametrize("role", ["architect", "developer", "qa", "reviewer"])
def test_roles_require_an_isolated_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    project, worktrees, worktree = _layout(tmp_path)
    monkeypatch.setattr(runner_module, "EVIDENCE_ROOT", tmp_path / "evidence")

    runner = ClaudeRunner(root=project, worktree_root=worktrees)
    method = getattr(runner, role)

    for candidate in (None, project, tmp_path / "outside"):
        with pytest.raises(RunnerError):
            method("prompt", cwd=candidate)

    # A valid worktree is accepted by the validator before any subprocess call.
    assert runner._worktree_cwd(role, worktree) == worktree.resolve()


def test_permission_modes_and_tools_are_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, worktrees, worktree = _layout(tmp_path)
    calls: dict[str, list[str]] = {}

    def fake_run(argv: list[str], **kwargs: object) -> _Completed:
        del kwargs
        agent = argv[argv.index("--agent") + 1]
        calls[agent] = argv
        models = {
            "autonomy-architect": runner_module.ARCHITECT_MODEL,
            "autonomy-developer": runner_module.DEVELOPER_MODEL,
            "autonomy-qa": runner_module.QA_MODEL,
            "autonomy-reviewer": runner_module.REVIEWER_MODEL,
        }
        return _Completed(models[agent])

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)
    monkeypatch.setattr(runner_module, "EVIDENCE_ROOT", tmp_path / "evidence")
    runner = ClaudeRunner(root=project, worktree_root=worktrees)

    runner.architect("prompt", cwd=worktree)
    runner.qa("prompt", cwd=worktree)
    runner.reviewer("prompt", cwd=worktree)

    architect = calls["autonomy-architect"]
    assert architect[architect.index("--permission-mode") + 1] == "plan"
    assert architect[architect.index("--allowedTools") + 1] == "Read,Grep,Glob"

    qa = calls["autonomy-qa"]
    assert qa[qa.index("--permission-mode") + 1] == "acceptEdits"

    reviewer = calls["autonomy-reviewer"]
    assert reviewer[reviewer.index("--permission-mode") + 1] == "plan"
    assert reviewer[reviewer.index("--allowedTools") + 1] == ("Read,Grep,Glob,Bash(git diff:*)")
