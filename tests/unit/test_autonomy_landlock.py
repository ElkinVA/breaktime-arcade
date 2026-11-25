"""Kernel Landlock boundary for autonomous model children."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from autonomy.landlock import SANDBOX_FAILURE_EXIT, abi_version, sandbox_preexec

pytestmark = pytest.mark.skipif(abi_version() < 1, reason="Landlock is unavailable")


def test_child_can_use_worktree_but_not_host_files(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    home = tmp_path / "home"
    temp = tmp_path / "temp"
    for path in (worktree, home, temp):
        path.mkdir()
    (worktree / "inside.txt").write_text("inside", encoding="utf-8")
    outside = tmp_path / "host-secret.txt"
    outside.write_text("host-only", encoding="utf-8")
    code = (
        "from pathlib import Path;"
        "print(Path('inside.txt').read_text());"
        f"print(Path({str(outside)!r}).read_text())"
    )

    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-c", code],
        cwd=worktree,
        env={**os.environ, "HOME": str(home), "TMPDIR": str(temp)},
        preexec_fn=sandbox_preexec(worktree, home, temp, namespaces=False),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert completed.stdout.strip() == "inside"
    assert "PermissionError" in completed.stderr


def test_missing_required_root_fails_closed(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    home = tmp_path / "home"
    temp = tmp_path / "temp"
    home.mkdir()
    temp.mkdir()

    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-c", "print('should not run')"],
        cwd=worktree,
        preexec_fn=sandbox_preexec(tmp_path / "missing", home, temp, namespaces=False),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == SANDBOX_FAILURE_EXIT
    assert "should not run" not in completed.stdout


def _user_namespaces_available() -> bool:
    try:
        return (
            subprocess.run(
                ["unshare", "-Ur", "true"],  # noqa: S607 - tool lookup is intentional
                capture_output=True,
                check=False,
                timeout=10,
            ).returncode
            == 0
        )
    except OSError, subprocess.TimeoutExpired:
        return False


@pytest.mark.skipif(not _user_namespaces_available(), reason="user namespaces unavailable")
def test_private_mount_namespace_hides_docker_socket(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    home = tmp_path / "home"
    temp = tmp_path / "temp"
    for path in (worktree, home, temp):
        path.mkdir()
    code = (
        "import socket;"
        "s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);"
        "s.connect('/var/run/docker.sock');"
        "print('connected')"
    )

    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-c", code],
        cwd=worktree,
        preexec_fn=sandbox_preexec(worktree, home, temp),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "connected" not in completed.stdout
