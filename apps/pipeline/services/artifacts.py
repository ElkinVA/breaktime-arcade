"""Filesystem artifacts for the package pipeline (§2.14.1, §2.14.3).

The original ZIP is stored once per ``package_hash`` and is never overwritten;
the runtime bundle lives in a separate directory keyed by ``runtime_hash``.
Both are published with an atomic rename so readers never observe a partial
tree.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import tempfile
from pathlib import Path

PACKAGES_DIR = "packages"


class ArtifactError(Exception):
    """Stable artifact failure (filesystem collision or corruption)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def ensure_root(root: Path) -> Path:
    root = Path(root)
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError:
        raise ArtifactError("X_ARTIFACT_IO", "Не удалось подготовить хранилище") from None
    if root.is_symlink() or not root.is_dir():
        raise ArtifactError("X_ARTIFACT_UNSAFE", "Хранилище небезопасно")
    return root


def package_path(root: Path, package_hash: str) -> Path:
    return Path(root) / PACKAGES_DIR / f"{package_hash}.zip"


def runtime_path(root: Path, runtime_hash: str, host_label: str | None = None) -> Path:
    base = Path(root) / host_label if host_label else Path(root)
    return base / runtime_hash


def read_immutable(path: Path) -> bytes:
    return path.read_bytes()


def store_immutable(path: Path, data: bytes) -> bool:
    """Create ``path`` once. Return ``True`` when a new file was written.

    An existing file must match byte-for-byte; a mismatch means the hash
    invariant is violated and is treated as an integrity error.
    """
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        try:
            existing = path.read_bytes()
        except OSError:
            raise ArtifactError("X_ARTIFACT_IO", "Не удалось прочитать артефакт") from None
        if existing != data:
            raise ArtifactError(
                "X_ARTIFACT_CONFLICT", "Артефакт с тем же хешем различается"
            ) from None
        return False
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    _fsync_dir(path.parent)
    return True


def tree_hashes(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_symlink():
            raise ArtifactError("X_ARTIFACT_UNSAFE", "Symlink в рабочем бандле")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def runtime_hash_for(hashes: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for name in sorted(hashes):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(hashes[name]))
        digest.update(b"\n")
    return digest.hexdigest()


def copy_tree(source: Path, destination: Path) -> None:
    """Copy regular files only; symlinks and special files are rejected."""
    source = Path(source)
    destination = Path(destination)
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        target = destination / relative
        if path.is_symlink():
            raise ArtifactError("X_ARTIFACT_UNSAFE", "Symlink в исходном пакете")
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if not path.is_file():
            raise ArtifactError("X_ARTIFACT_UNSAFE", "Специальный файл в пакете")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        try:
            target.chmod(0o600)
        except OSError:
            raise ArtifactError("X_ARTIFACT_IO", "Не удалось выставить права") from None


def _make_runtime_public(root: Path) -> None:
    """Give nginx (UID 101) read/traverse access to the published runtime.

    The runtime bundle is public by definition; the original package remains
    private. Directory/file modes are set explicitly because the extraction
    staging tree is created with private modes (``700``/``600``).
    """
    try:
        root.chmod(0o755)
        for path in root.rglob("*"):
            if path.is_symlink():
                raise ArtifactError("X_ARTIFACT_UNSAFE", "Symlink в runtime")
            if path.is_dir():
                path.chmod(0o755)
            elif path.is_file():
                path.chmod(0o644)
    except OSError as exc:
        raise ArtifactError("X_ARTIFACT_IO", f"Не удалось выставить права runtime: {exc}") from None


def store_runtime(
    root: Path,
    runtime_hash: str,
    staging: Path,
    *,
    host_label: str | None = None,
) -> Path:
    """Publish ``staging`` as ``<root>/[host]/<hash>`` atomically."""
    root = ensure_root(Path(root))
    target = runtime_path(root, runtime_hash, host_label)
    if host_label:
        try:
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            target.parent.chmod(0o755)
        except OSError:
            raise ArtifactError("X_ARTIFACT_IO", "Не удалось подготовить runtime-хост") from None
    if target.exists():
        if target.is_symlink() or not target.is_dir():
            raise ArtifactError("X_ARTIFACT_UNSAFE", "Путь runtime занят")
        if runtime_hash_for(tree_hashes(target)) != runtime_hash:
            raise ArtifactError("X_ARTIFACT_CONFLICT", "Runtime с тем же хешем различается")
        _make_runtime_public(target)
        with contextlib.suppress(OSError):
            shutil.rmtree(staging, ignore_errors=True)
        return target
    # Always copy into a staging directory next to the target. Artifact stores
    # live on different volumes in Compose, where rename(2) would fail with
    # EXDEV even when the bundle is otherwise valid.
    try:
        local = Path(tempfile.mkdtemp(prefix=".ba-runtime-", dir=target.parent))
    except OSError:
        raise ArtifactError("X_ARTIFACT_IO", "Не удалось создать staging-каталог") from None
    try:
        copy_tree(staging, local)
    except ArtifactError:
        shutil.rmtree(local, ignore_errors=True)
        raise
    try:
        local.rename(target)
    except OSError as exc:
        shutil.rmtree(local, ignore_errors=True)
        raise ArtifactError("X_ARTIFACT_IO", f"Не удалось опубликовать runtime: {exc}") from None
    shutil.rmtree(staging, ignore_errors=True)
    _make_runtime_public(target)
    _fsync_dir(target.parent)
    return target


def make_staging_dir(parent: Path, prefix: str = ".ba-runtime-") -> Path:
    ensure_root(parent)
    try:
        return Path(tempfile.mkdtemp(prefix=prefix, dir=parent))
    except OSError:
        raise ArtifactError("X_ARTIFACT_IO", "Не удалось создать staging-каталог") from None


def _fsync_dir(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        fd = os.open(path, flags)
    except OSError:
        return
    try:
        with contextlib.suppress(OSError):
            os.fsync(fd)
    finally:
        os.close(fd)
