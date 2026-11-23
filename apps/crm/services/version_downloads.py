"""Staff-only downloads of immutable package artifacts and version reports.

The original ZIP is served from the private package store and the runtime
bundle is re-zipped from the published tree (§2.14.1, §2.16.3). Every path is
derived from the stored ``package_hash`` / ``runtime_hash`` through the
pipeline artifact helpers, then checked to stay inside its configured root, so
no request parameter can influence a filesystem path. Report downloads render
the persisted ``validation_report`` / ``e2e_report`` / ``import_report``
(§2.14.7).

Responses are always attachments with a fixed name derived from UUIDs only and
carry ``nosniff`` plus a private, non-cacheable policy.

The original package is read from the verified descriptor exactly once: its
bytes are copied into a temporary spool while SHA-256 is computed and the
response streams that spool only after the digest matches
``version.package_hash``. The served bytes are therefore the same bytes that
were hashed, a corrupted file is rejected before any body byte is served, and
the response never holds the whole ZIP in memory.

The runtime bundle is built through one verified-descriptor walk that computes
each file's SHA-256 from exactly the bytes written into the archive. The
canonical tree digest (``runtime_hash_for``) is compared with
``version.runtime_hash`` before the spool is served, so a file changed after
import yields ``ArtifactUnavailable`` instead of a body that no longer matches
the published hash.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, BinaryIO

from django.conf import settings
from django.http import FileResponse, HttpResponse

from apps.catalog.models import GameVersion
from apps.pipeline.services.artifacts import (
    ArtifactError,
    ensure_root,
    package_path,
    runtime_hash_for,
    runtime_path,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ARTIFACT_CHUNK_SIZE = 1024 * 1024

REPORT_KINDS = frozenset({"validation", "autotest", "import"})
REPORT_FORMATS = frozenset({"json", "md"})

_REPORT_FIELDS = {
    "validation": "validation_report",
    "autotest": "e2e_report",
    "import": "import_report",
}
_REPORT_TITLES = {
    "validation": "Отчёт валидации пакета",
    "autotest": "Отчёт автотеста версии",
    "import": "Отчёт импорта версии",
}
_JSON_CONTENT_TYPE = "application/json; charset=utf-8"
_MARKDOWN_CONTENT_TYPE = "text/markdown; charset=utf-8"


class ArtifactUnavailable(Exception):
    """The stored artifact is missing or its resolved path is unsafe."""


class UnknownReport(Exception):
    """The requested report kind or format is not supported."""


def _safe_root(value: Path) -> Path:
    try:
        return ensure_root(Path(value))
    except ArtifactError:
        raise ArtifactUnavailable("Artifact root is unavailable") from None


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.resolve(strict=False).relative_to(root.resolve(strict=False))
    except OSError, ValueError:
        return False
    return True


def _has_valid_hash(value: str) -> bool:
    return bool(value) and _SHA256_RE.fullmatch(value) is not None


def _safe_host_label(value: str) -> bool:
    return bool(value) and "/" not in value and "\\" not in value and value not in {".", ".."}


def _open_flags(*, directory: bool) -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if directory and hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    return flags


def _open_verified(path: Path, *, directory: bool) -> tuple[int, os.stat_result]:
    """Open ``path`` once and verify the handle against the resolved path.

    ``O_NOFOLLOW`` rejects a final symlink and ``fstat`` on the opened handle
    is compared with the path identity captured immediately before the open.
    A path swap between resolution and open therefore raises instead of
    returning a different inode; callers read only from the verified handle.
    """
    kind = "directory" if directory else "file"
    try:
        expected = path.stat(follow_symlinks=False)
    except OSError:
        raise ArtifactUnavailable(f"Artifact {kind} is missing") from None
    if stat.S_ISLNK(expected.st_mode):
        raise ArtifactUnavailable("Artifact path is a symlink")
    if directory:
        if not stat.S_ISDIR(expected.st_mode):
            raise ArtifactUnavailable("Artifact directory is missing")
    elif not stat.S_ISREG(expected.st_mode):
        raise ArtifactUnavailable("Artifact file is missing")
    try:
        fd = os.open(path, _open_flags(directory=directory))
    except OSError:
        raise ArtifactUnavailable(f"Artifact {kind} is unavailable") from None
    try:
        opened = os.fstat(fd)
    except OSError:
        os.close(fd)
        raise ArtifactUnavailable(f"Artifact {kind} is unavailable") from None
    expected_kind = stat.S_ISDIR(opened.st_mode) if directory else stat.S_ISREG(opened.st_mode)
    if not expected_kind or (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino):
        os.close(fd)
        raise ArtifactUnavailable("Artifact changed between resolution and read")
    return fd, opened


def _spool_verified_handle(fd: int, expected: str) -> BinaryIO:
    """Copy the opened handle into a spool, hashing the exact bytes copied.

    The descriptor is read once in bounded chunks; every chunk is fed both to
    SHA-256 and to the temporary spool. Only when the digest matches
    ``expected`` is the rewound spool returned, so the bytes later served are
    provably the bytes that were hashed and an in-place write after the open
    cannot slip into the response. Nothing is buffered beyond one chunk.
    """
    try:
        spool = tempfile.TemporaryFile(prefix="ba-package-", suffix=".zip")  # noqa: SIM115
    except OSError:
        raise ArtifactUnavailable("Artifact file is unavailable") from None
    digest = hashlib.sha256()
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        while True:
            chunk = os.read(fd, ARTIFACT_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            spool.write(chunk)
    except OSError:
        spool.close()
        raise ArtifactUnavailable("Artifact file is unavailable") from None
    except BaseException:
        spool.close()
        raise
    if digest.hexdigest() != expected:
        spool.close()
        raise ArtifactUnavailable("Artifact hash mismatch")
    spool.seek(0)
    return spool


def _write_handle_to_zip(archive: zipfile.ZipFile, info: zipfile.ZipInfo, fd: int) -> str:
    """Copy a verified descriptor into ``archive``, hashing the copied bytes."""
    digest = hashlib.sha256()
    try:
        with archive.open(info, "w") as target:
            while True:
                chunk = os.read(fd, ARTIFACT_CHUNK_SIZE)
                if not chunk:
                    break
                digest.update(chunk)
                target.write(chunk)
    except OSError:
        raise ArtifactUnavailable("Artifact file is unavailable") from None
    finally:
        os.close(fd)
    return digest.hexdigest()


def _open_child(
    parent_fd: int,
    name: str,
    *,
    directory: bool,
) -> tuple[int, os.stat_result]:
    """Open ``name`` relative to ``parent_fd`` and verify the opened inode."""
    kind = "directory" if directory else "file"
    try:
        expected = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError:
        raise ArtifactUnavailable(f"Artifact {kind} is missing") from None
    if stat.S_ISLNK(expected.st_mode):
        raise ArtifactUnavailable("Runtime tree contains a symlink")
    if directory:
        if not stat.S_ISDIR(expected.st_mode):
            raise ArtifactUnavailable("Runtime artifact is not a directory")
    elif not stat.S_ISREG(expected.st_mode):
        raise ArtifactUnavailable("Runtime artifact is not a regular file")
    try:
        fd = os.open(name, _open_flags(directory=directory), dir_fd=parent_fd)
    except OSError:
        raise ArtifactUnavailable(f"Artifact {kind} is unavailable") from None
    try:
        opened = os.fstat(fd)
    except OSError:
        os.close(fd)
        raise ArtifactUnavailable(f"Artifact {kind} is unavailable") from None
    expected_kind = stat.S_ISDIR(opened.st_mode) if directory else stat.S_ISREG(opened.st_mode)
    if not expected_kind or (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino):
        os.close(fd)
        raise ArtifactUnavailable("Runtime artifact changed between resolution and read")
    return fd, opened


def package_file(version: GameVersion) -> Path:
    """Resolve the immutable original ZIP for ``version`` inside its root."""
    if not _has_valid_hash(version.package_hash):
        raise ArtifactUnavailable("Invalid package hash")
    root = _safe_root(settings.ZIP_PIPELINE_STORAGE_ROOT)
    target = package_path(root, version.package_hash)
    if not _is_within(target, root):
        raise ArtifactUnavailable("Package path escapes the artifact root")
    if target.is_symlink() or not target.is_file():
        raise ArtifactUnavailable("Package artifact is missing")
    return target


def runtime_directory(version: GameVersion) -> Path:
    """Resolve the published runtime tree for ``version`` inside its root."""
    if not _has_valid_hash(version.runtime_hash):
        raise ArtifactUnavailable("Invalid runtime hash")
    host_label = str(version.game.host_label or "")
    if not _safe_host_label(host_label):
        raise ArtifactUnavailable("Invalid runtime host label")
    root = _safe_root(settings.ZIP_PUBLIC_RUNTIME_ROOT)
    target = runtime_path(root, version.runtime_hash, host_label)
    if not _is_within(target, root):
        raise ArtifactUnavailable("Runtime path escapes the artifact root")
    if target.is_symlink() or not target.is_dir():
        raise ArtifactUnavailable("Runtime artifact is missing")
    return target


def _zip_date_time(timestamp: float) -> tuple[int, int, int, int, int, int]:
    local = time.localtime(timestamp)
    return (local.tm_year, local.tm_mon, local.tm_mday, local.tm_hour, local.tm_min, local.tm_sec)


def _zip_tree(
    archive: zipfile.ZipFile,
    directory_fd: int,
    prefix: str,
    hashes: dict[str, str],
) -> None:
    """Archive a directory tree read through verified descriptors.

    Every entry is opened relative to the already verified parent descriptor
    with ``O_NOFOLLOW``; the opened handle is compared with the entry identity
    before any bytes are read, so a symlink or swap cannot substitute content.
    Each regular file's SHA-256 is accumulated under the archive name while the
    same bytes are written, so the digest describes exactly the served tree.
    """
    try:
        names = os.listdir(directory_fd)
    except OSError:
        raise ArtifactUnavailable("Runtime artifact is unavailable") from None
    for name in sorted(names):
        arcname = f"{prefix}{name}"
        try:
            entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except OSError:
            raise ArtifactUnavailable("Runtime artifact is unavailable") from None
        if stat.S_ISLNK(entry.st_mode):
            raise ArtifactUnavailable("Runtime tree contains a symlink")
        if stat.S_ISDIR(entry.st_mode):
            child_fd, _child_stat = _open_child(directory_fd, name, directory=True)
            try:
                _zip_tree(archive, child_fd, f"{arcname}/", hashes)
            finally:
                os.close(child_fd)
        elif stat.S_ISREG(entry.st_mode):
            file_fd, opened = _open_child(directory_fd, name, directory=False)
            info = zipfile.ZipInfo(arcname, date_time=_zip_date_time(opened.st_mtime))
            info.external_attr = (opened.st_mode & 0xFFFF) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            hashes[arcname] = _write_handle_to_zip(archive, info, file_fd)
        # Special files stay excluded, matching the regular-files-only contract.


def runtime_zip_file(directory: Path, expected_hash: str) -> BinaryIO:
    """Zip and hash-verify the published runtime tree into a temporary file.

    The tree is walked through verified directory descriptors opened relative
    to the resolved root; a symlink or path swap anywhere in the tree raises
    ``ArtifactUnavailable``. While each file is written into the archive its
    SHA-256 is accumulated under the archive name, then the canonical tree
    digest (``runtime_hash_for`` format) is compared with ``expected_hash``.
    The spool is served only after the digest matches, so a file changed after
    import is rejected before any body byte is written. The archive uses an
    anonymous temporary file rather than ``io.BytesIO`` so its size never lives
    in memory.
    """
    root_fd, _root_stat = _open_verified(directory, directory=True)
    try:
        # The response owns and closes this handle after streaming it.
        spool = tempfile.TemporaryFile(prefix="ba-runtime-", suffix=".zip")  # noqa: SIM115
    except OSError:
        os.close(root_fd)
        raise ArtifactUnavailable("Runtime artifact is unavailable") from None
    hashes: dict[str, str] = {}
    try:
        with zipfile.ZipFile(spool, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            _zip_tree(archive, root_fd, "", hashes)
    except OSError:
        spool.close()
        raise ArtifactUnavailable("Runtime artifact is unavailable") from None
    except Exception:
        spool.close()
        raise
    finally:
        os.close(root_fd)
    if runtime_hash_for(hashes) != expected_hash:
        spool.close()
        raise ArtifactUnavailable("Runtime hash mismatch")
    spool.seek(0)
    return spool


def _stream_attachment(
    filelike: BinaryIO,
    *,
    filename: str,
    content_type: str,
) -> FileResponse:
    """Serve ``filelike`` as a bounded-chunk streaming attachment."""
    response = FileResponse(
        filelike,
        content_type=content_type,
        as_attachment=True,
        filename=filename,
    )
    response.block_size = ARTIFACT_CHUNK_SIZE
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


def _attachment(content: bytes | str, *, filename: str, content_type: str) -> HttpResponse:
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


def _artifact_name(version: GameVersion, suffix: str) -> str:
    return f"game-{version.game_id}-version-{version.id}-{suffix}"


def package_response(version: GameVersion) -> FileResponse:
    """Verify and stream the immutable original ZIP in a single pass.

    The ``O_NOFOLLOW`` descriptor is read exactly once: bytes go into a
    temporary spool while SHA-256 is computed, the digest is checked against
    ``version.package_hash``, and only a matching spool is served. A mismatch
    raises ``ArtifactUnavailable`` without serving a single body byte, and an
    in-place write after the open is either part of the hashed bytes or the
    request fails -- never a served body that differs from the verified digest.
    """
    path = package_file(version)
    fd, _path_stat = _open_verified(path, directory=False)
    try:
        spool = _spool_verified_handle(fd, version.package_hash)
    finally:
        os.close(fd)
    try:
        return _stream_attachment(
            spool,
            filename=_artifact_name(version, "package.zip"),
            content_type="application/zip",
        )
    except BaseException:
        spool.close()
        raise


def runtime_response(version: GameVersion) -> FileResponse:
    spool = runtime_zip_file(runtime_directory(version), version.runtime_hash)
    try:
        return _stream_attachment(
            spool,
            filename=_artifact_name(version, "runtime.zip"),
            content_type="application/zip",
        )
    except BaseException:
        spool.close()
        raise


def _stored_report(version: GameVersion, report_kind: str) -> Any:
    return getattr(version, _REPORT_FIELDS[report_kind]) or {}


def _md(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _markdown_header(version: GameVersion, report_kind: str) -> list[str]:
    return [
        f"# {_REPORT_TITLES[report_kind]}",
        "",
        f"- Игра: `{version.game.technical_id}`",
        f"- Версия: `{version.semver}`",
        f"- package_hash: `{version.package_hash}`",
        f"- runtime_hash: `{version.runtime_hash}`",
        "",
    ]


def _validation_markdown(version: GameVersion, report: Any) -> str:
    lines = _markdown_header(version, "validation")
    data = report if isinstance(report, dict) else {}
    raw_summary = data.get("summary")
    summary = raw_summary if isinstance(raw_summary, dict) else {}
    lines.extend(
        [
            f"- blocker: {summary.get('blocker', 0)}",
            f"- warning: {summary.get('warning', 0)}",
            f"- info: {summary.get('info', 0)}",
            f"- итог: {'OK' if data.get('ok', True) else 'REJECTED'}",
            "",
        ]
    )
    diagnostics = data.get("diagnostics")
    entries = (
        [item for item in diagnostics if isinstance(item, dict)]
        if isinstance(diagnostics, list)
        else []
    )
    if not entries:
        lines.append("Замечаний нет.")
        return "\n".join(lines) + "\n"
    lines.extend(["| severity | code | file | message | hint |", "|---|---|---|---|---|"])
    for item in entries:
        lines.append(
            "| {severity} | {code} | {file} | {message} | {hint} |".format(
                severity=_md(item.get("severity")),
                code=_md(item.get("code")),
                file=_md(item.get("file")) or "—",
                message=_md(item.get("message")),
                hint=_md(item.get("hint")) or "—",
            )
        )
    return "\n".join(lines) + "\n"


def _autotest_markdown(version: GameVersion, report: Any) -> str:
    lines = _markdown_header(version, "autotest")
    data = report if isinstance(report, dict) else {}
    lines.append(f"- итог: {'Пройден' if data.get('passed') else 'Не пройден'}")
    lines.append("")
    checks = data.get("checks")
    entries = (
        [item for item in checks if isinstance(item, dict)] if isinstance(checks, list) else []
    )
    if entries:
        lines.extend(["| проверка | результат | детали |", "|---|---|---|"])
        for item in entries:
            lines.append(
                "| {name} | {passed} | {detail} |".format(
                    name=_md(item.get("name")),
                    passed="OK" if item.get("passed") else "FAIL",
                    detail=_md(item.get("detail")) or "—",
                )
            )
        lines.append("")
    notes = data.get("notes")
    if isinstance(notes, list) and notes:
        lines.extend(["> Примечания:", ">"])
        for note in notes:
            lines.append(f"> - {_md(note)}")
        lines.append("")
    return "\n".join(lines) + "\n"


def _import_markdown(version: GameVersion, report: Any) -> str:
    lines = _markdown_header(version, "import")
    data = report if isinstance(report, dict) else {}
    lines.append(f"- статус: {_md(data.get('status')) or '—'}")
    lines.append("")
    updated = data.get("updated_fields")
    fields = [str(item) for item in updated] if isinstance(updated, list) else []
    if fields:
        lines.extend(["Изменённые поля: " + ", ".join(f"`{_md(item)}`" for item in fields), ""])
    conflicts = data.get("conflicts")
    entries = (
        [item for item in conflicts if isinstance(item, dict)]
        if isinstance(conflicts, list)
        else []
    )
    if entries:
        lines.extend(["| scope | field | resolution |", "|---|---|---|"])
        for item in entries:
            lines.append(
                "| {scope} | {field} | {resolution} |".format(
                    scope=_md(item.get("scope")) or "—",
                    field=_md(item.get("field")) or "—",
                    resolution=_md(item.get("resolution")) or "keep",
                )
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def _render_markdown(version: GameVersion, report_kind: str, report: Any) -> str:
    if report_kind == "validation":
        return _validation_markdown(version, report)
    if report_kind == "autotest":
        return _autotest_markdown(version, report)
    return _import_markdown(version, report)


def report_response(
    version: GameVersion,
    report_kind: str,
    report_format: str,
) -> HttpResponse:
    """Render a persisted per-version report as a JSON or Markdown attachment."""
    if report_kind not in REPORT_KINDS:
        raise UnknownReport(report_kind)
    if report_format not in REPORT_FORMATS:
        raise UnknownReport(report_format)
    report = _stored_report(version, report_kind)
    if report_format == "json":
        content = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
        content_type = _JSON_CONTENT_TYPE
    else:
        content = _render_markdown(version, report_kind, report)
        content_type = _MARKDOWN_CONTENT_TYPE
    return _attachment(
        content,
        filename=_artifact_name(version, f"{report_kind}.{report_format}"),
        content_type=content_type,
    )


__all__ = [
    "ARTIFACT_CHUNK_SIZE",
    "ArtifactUnavailable",
    "REPORT_FORMATS",
    "REPORT_KINDS",
    "UnknownReport",
    "package_file",
    "package_response",
    "report_response",
    "runtime_directory",
    "runtime_response",
    "runtime_zip_file",
]
