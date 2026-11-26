"""Landlock OS sandbox for autonomous model child processes (Linux).

The runner already filters environment variables and validates the worktree.
This module adds a kernel-enforced filesystem boundary without root: the child
may read/execute system runtime paths and read/write only its task worktree and
a private HOME/TMPDIR. Host secrets, the main checkout, Docker's socket and
arbitrary host paths are not reachable. Network access is intentionally not
restricted (the model API needs it); Landlock network rules are ABI 4+ and are
out of scope for this minimal boundary.

Applied in ``preexec_fn`` immediately before ``exec``; on any setup error the
child exits with a reserved code instead of running unsandboxed.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import stat
import sys
from pathlib import Path

PR_SET_NO_NEW_PRIVS = 38
LANDLOCK_CREATE_RULESET_VERSION = 1
LANDLOCK_RULE_PATH_BENEATH = 1
SYS_LANDLOCK_CREATE_RULESET = 444  # x86_64
SYS_LANDLOCK_ADD_RULE = 445
SYS_LANDLOCK_RESTRICT_SELF = 446
SYS_UNSHARE = 272
SYS_MOUNT = 165

CLONE_NEWNS = 0x00020000
CLONE_NEWUSER = 0x10000000

# landlock_access_fs flags (see linux/landlock.h).
LL_EXECUTE = 1 << 0
LL_WRITE_FILE = 1 << 1
LL_READ_FILE = 1 << 2
LL_READ_DIR = 1 << 3
LL_REMOVE_DIR = 1 << 4
LL_REMOVE_FILE = 1 << 5
LL_MAKE_CHAR = 1 << 6
LL_MAKE_DIR = 1 << 7
LL_MAKE_REG = 1 << 8
LL_MAKE_SOCK = 1 << 9
LL_MAKE_FIFO = 1 << 10
LL_MAKE_BLOCK = 1 << 11
LL_MAKE_SYM = 1 << 12
LL_REFER = 1 << 13
LL_TRUNCATE = 1 << 14

READ_ACCESS = LL_READ_FILE | LL_READ_DIR | LL_EXECUTE
WRITE_ACCESS = (
    READ_ACCESS
    | LL_WRITE_FILE
    | LL_REMOVE_DIR
    | LL_REMOVE_FILE
    | LL_MAKE_DIR
    | LL_MAKE_REG
    | LL_MAKE_SYM
    | LL_MAKE_FIFO
    | LL_MAKE_SOCK
    | LL_REFER
    | LL_TRUNCATE
)
HANDLED_ACCESS = WRITE_ACCESS | LL_MAKE_CHAR | LL_MAKE_BLOCK

SANDBOX_FAILURE_EXIT = 125


class LandlockError(RuntimeError):
    pass


class _RulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class _PathBeneathAttr(ctypes.Structure):
    _layout_ = "ms"
    _pack_ = 1
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


def _syscall(number: int, *args: object) -> int:
    libc = ctypes.CDLL(None, use_errno=True)
    result = libc.syscall(number, *args)
    if result < 0:
        errno = ctypes.get_errno()
        raise LandlockError(f"landlock syscall {number} failed: errno {errno}")
    return int(result)


def abi_version() -> int:
    """Return the kernel Landlock ABI, or 0 when unavailable."""
    try:
        return _syscall(SYS_LANDLOCK_CREATE_RULESET, 0, 0, LANDLOCK_CREATE_RULESET_VERSION)
    except LandlockError:
        return 0


def _allow(ruleset_fd: int, path: Path, access: int) -> None:
    try:
        fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
        mode = os.fstat(fd).st_mode
    except OSError:
        return  # optional system path; required paths are checked separately
    try:
        if not stat.S_ISDIR(mode):
            # Landlock rejects directory/creation rights on a regular file.
            access &= LL_READ_FILE | LL_WRITE_FILE | LL_EXECUTE | LL_TRUNCATE
        attr = _PathBeneathAttr(allowed_access=access, parent_fd=fd)
        _syscall(
            SYS_LANDLOCK_ADD_RULE,
            ruleset_fd,
            LANDLOCK_RULE_PATH_BENEATH,
            ctypes.byref(attr),
            0,
        )
    finally:
        os.close(fd)


def _required_root(path: Path) -> None:
    if not path.is_dir():
        raise LandlockError(f"required sandbox path is missing: {path}")


def _write_proc(path: str, value: str) -> None:
    with Path(path).open("w", encoding="utf-8") as handle:
        handle.write(value)


def _mount_tmpfs(target: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.mount(b"tmpfs", str(target).encode(), b"tmpfs", 0, None) < 0:
        errno = ctypes.get_errno()
        raise LandlockError(f"cannot mount tmpfs on {target}: errno {errno}")


def enter_private_namespaces() -> None:
    """Hide host Unix sockets and /run inside a private user+mount namespace.

    Landlock does not mediate ``connect()`` on AF_UNIX sockets, so a child in
    the docker group could otherwise reach ``/var/run/docker.sock``. A user
    namespace (mapped to the current uid) plus a private mount namespace lets
    us replace ``/run`` and ``/dev/shm`` with empty tmpfs. No host mount is
    modified.
    """
    uid = os.getuid()
    gid = os.getgid()
    _syscall(SYS_UNSHARE, CLONE_NEWUSER | CLONE_NEWNS)
    _write_proc("/proc/self/setgroups", "deny")
    _write_proc("/proc/self/uid_map", f"0 {uid} 1")
    _write_proc("/proc/self/gid_map", f"0 {gid} 1")
    for target in (Path("/run"), Path("/dev/shm")):  # noqa: S108 - namespace mount point
        if target.is_dir():
            _mount_tmpfs(target)


def apply_landlock(
    *,
    worktree: Path,
    home: Path,
    temp: Path,
    extra_read_roots: tuple[Path, ...] = (),
) -> None:
    """Restrict the current process (and future children) with Landlock.

    Must be called in the soon-to-be-execed child. Raises LandlockError; the
    caller must fail closed.
    """
    if abi_version() < 1:
        raise LandlockError("Landlock is not available on this kernel")

    for path in (worktree, home, temp):
        _required_root(path)

    ruleset_attr = _RulesetAttr(handled_access_fs=HANDLED_ACCESS)
    ruleset_fd = _syscall(
        SYS_LANDLOCK_CREATE_RULESET,
        ctypes.byref(ruleset_attr),
        ctypes.sizeof(ruleset_attr),
        0,
    )
    try:
        for path in (worktree, home, temp):
            _allow(ruleset_fd, path, WRITE_ACCESS)
        for path in (
            Path("/usr"),
            Path("/bin"),
            Path("/sbin"),
            Path("/lib"),
            Path("/lib64"),
            Path("/etc"),
            Path("/opt"),
            Path("/dev"),
            Path("/sys"),
            *extra_read_roots,
        ):
            if path.exists():
                _allow(ruleset_fd, path, READ_ACCESS)
        # Node/Claude may consult these; avoid granting all of /proc, which
        # would expose other processes' environ/cmdline under the same UID.
        pid_dir = Path(f"/proc/{os.getpid()}")
        for path in (
            Path("/proc/self"),
            Path("/proc/thread-self"),
            pid_dir,
            pid_dir / "task",
            Path("/proc/meminfo"),
            Path("/proc/cpuinfo"),
            Path("/proc/loadavg"),
            Path("/proc/uptime"),
            Path("/mnt/wsl/resolv.conf"),
            Path("/run/systemd/resolve"),
        ):
            if path.exists():
                _allow(ruleset_fd, path, READ_ACCESS)
        _syscall(
            157,  # prctl
            PR_SET_NO_NEW_PRIVS,
            1,
            0,
            0,
            0,
        )
        _syscall(SYS_LANDLOCK_RESTRICT_SELF, ruleset_fd, 0)
    finally:
        os.close(ruleset_fd)


def interpreter_read_roots(executable: str | None = None) -> tuple[Path, ...]:
    """Return the narrow Python runtime roots needed to exec the interpreter.

    A venv executable is commonly ``<repo>/.venv/bin/python``; without an
    execute grant the Landlock child cannot even start Python, and the
    worktree is the only writable root. Grant the interpreter prefix (and its
    base prefix for the stdlib), never the host HOME or an arbitrary ancestor.
    """
    path = Path(executable or sys.executable).resolve()
    candidates = {
        Path(sys.prefix).resolve(),
        Path(sys.base_prefix).resolve(),
        path.parent,
    }
    roots: list[Path] = []
    for candidate in candidates:
        if candidate == Path("/") or candidate == Path.home().resolve():
            continue
        if candidate.is_dir() and candidate not in roots:
            roots.append(candidate)
    return tuple(roots)


def node_read_root(claude_path: str | None = None) -> Path | None:
    """Return the directory that contains the Node/Claude runtime, if any."""
    claude = claude_path or shutil.which("claude")
    if not claude:
        return None
    path = Path(claude).resolve()
    # .../.nvm/versions/node/<version>/bin/claude -> <version>.
    # Prefer the narrow runtime root; never grant the whole host HOME or .nvm.
    parents = list(path.parents)
    for parent in parents:
        if (
            parent.parent.name == "node"
            and parent.parent.parent.name == "versions"
            and (parent / "lib" / "node_modules").is_dir()
        ):
            return parent
    # Native/non-nvm layouts are intentionally narrow: only the executable's
    # bin directory, never an ancestor such as the host HOME.
    return path.parent if path.parent.name == "bin" else None


def sandbox_preexec(
    worktree: Path,
    home: Path,
    temp: Path,
    *,
    claude_path: str | None = None,
    namespaces: bool = True,
):
    """Build a fail-closed ``preexec_fn`` for subprocess.

    ``namespaces=False`` is only for tests of the Landlock filesystem layer;
    production model runs always use the private user/mount namespace so host
    Unix sockets (Docker, SSH agent) are unreachable.
    """

    def _apply() -> None:
        try:
            if namespaces:
                enter_private_namespaces()
            extra = tuple(
                path
                for path in (*interpreter_read_roots(), node_read_root(claude_path))
                if path is not None
            )
            apply_landlock(worktree=worktree, home=home, temp=temp, extra_read_roots=extra)
        except BaseException:
            os._exit(SANDBOX_FAILURE_EXIT)

    return _apply
