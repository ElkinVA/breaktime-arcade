"""Safe ZIP extraction for the game package pipeline (§2.14.2).

The preflight stage only inspects metadata. This stage materialises a package
in a fresh directory, but never executes it. Extraction is streaming and
independent of header sizes: every byte read from the archive is counted
against per-file and total limits, CRC is checked by :mod:`zipfile`, and the
result is published with an atomic directory rename.
"""

from __future__ import annotations

import contextlib
import errno
import hashlib
import io
import lzma
import os
import re
import shutil
import tempfile
import time
import unicodedata
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from apps.pipeline.validation.codes import (
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_UNCOMPRESSED_BYTES,
    PreflightReport,
)
from apps.pipeline.validation.structure import preflight_zip

X_PREFLIGHT_REJECTED = "X_PREFLIGHT_REJECTED"
X_DESTINATION_EXISTS = "X_DESTINATION_EXISTS"
X_LIMIT_FILE = "X_LIMIT_FILE"
X_LIMIT_TOTAL = "X_LIMIT_TOTAL"
X_LIMIT_FILES = "X_LIMIT_FILES"
X_PATH_UNSAFE = "X_PATH_UNSAFE"
X_PREFIX_CONFLICT = "X_PREFIX_CONFLICT"
X_CRC_MISMATCH = "X_CRC_MISMATCH"
X_SIZE_MISMATCH = "X_SIZE_MISMATCH"
X_ARCHIVE_BAD = "X_ARCHIVE_BAD"
X_TIMEOUT = "X_TIMEOUT"
X_CANCELLED = "X_CANCELLED"
X_IO = "X_IO"

_CHUNK = 64 * 1024
_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_MAX_PATH_BYTES = 1024
_MAX_COMPONENTS = 64
_BAD_UNICODE = {"‪", "‫", "‬", "‭", "‮", "⁦", "⁧", "⁨", "⁩"}


class ExtractionError(Exception):
    """Stable extraction failure with a machine-readable code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        report: PreflightReport | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.report = report


@dataclass(frozen=True, slots=True)
class ExtractedFile:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    root: Path
    package_hash: str
    files: tuple[ExtractedFile, ...]
    total_bytes: int
    preflight: PreflightReport


def _parts(name: str) -> tuple[str, ...]:
    """Revalidate a path independently of the preflight report."""
    if "\\" in name:
        raise ExtractionError(X_PATH_UNSAFE, "Обратные слэши в пути запрещены")
    normalized = unicodedata.normalize("NFKC", name)
    if normalized != name:
        raise ExtractionError(X_PATH_UNSAFE, "Неканоническая Unicode-форма пути")
    if normalized.startswith("/") or _DRIVE_RE.match(normalized):
        raise ExtractionError(X_PATH_UNSAFE, "Абсолютный путь запрещён")
    parts = tuple(part for part in normalized.split("/") if part not in {"", "."})
    if not parts:
        raise ExtractionError(X_PATH_UNSAFE, "Пустой путь запрещён")
    if any(part == ".." for part in parts):
        raise ExtractionError(X_PATH_UNSAFE, "Path traversal запрещён")
    canonical = "/".join(parts)
    if canonical != normalized.rstrip("/"):
        raise ExtractionError(X_PATH_UNSAFE, "Неканонический путь запрещён")
    if len(canonical.encode("utf-8")) > _MAX_PATH_BYTES or len(parts) > _MAX_COMPONENTS:
        raise ExtractionError(X_PATH_UNSAFE, "Слишком длинный или глубокий путь")
    for part in parts:
        if len(part.encode("utf-8")) > 255 or part.endswith((".", " ")):
            raise ExtractionError(X_PATH_UNSAFE, "Недопустимый компонент пути")
        if any(
            ord(char) < 32
            or 0x7F <= ord(char) <= 0x9F
            or char in _BAD_UNICODE
            or char in {"؜", "‎", "‏", " ", " "}
            for char in part
        ):
            raise ExtractionError(X_PATH_UNSAFE, "Управляющие символы в пути")
    return parts


def _ensure_dir(root: Path, parts: tuple[str, ...]) -> None:
    current = root
    for part in parts:
        current = current / part
        try:
            current.mkdir(mode=0o700)
        except FileExistsError:
            if current.is_symlink() or not current.is_dir():
                raise ExtractionError(X_PATH_UNSAFE, "Конфликт каталога и файла") from None
        except OSError:
            raise ExtractionError(X_IO, "Не удалось создать каталог") from None


def _entries(
    infos: list[zipfile.ZipInfo],
) -> tuple[list[tuple[zipfile.ZipInfo, tuple[str, ...]]], set[tuple[str, ...]]]:
    files: list[tuple[zipfile.ZipInfo, tuple[str, ...]]] = []
    dirs: set[tuple[str, ...]] = set()
    file_paths: set[tuple[str, ...]] = set()
    folded: set[str] = set()
    for info in infos:
        parts = _parts(info.filename)
        if info.filename.endswith("/"):
            dirs.add(parts)
            continue
        key = "/".join(parts).casefold()
        if key in folded:
            raise ExtractionError(X_PATH_UNSAFE, "Дубликат или регистровая коллизия")
        folded.add(key)
        if parts in dirs or parts in file_paths:
            raise ExtractionError(X_PATH_UNSAFE, "Дубликат пути")
        file_paths.add(parts)
        files.append((info, parts))

    for parts in file_paths:
        for index in range(1, len(parts)):
            if parts[:index] in file_paths:
                raise ExtractionError(
                    X_PREFIX_CONFLICT,
                    "Файл не может быть родительским каталогом другого файла",
                )
    if file_paths.intersection(dirs):
        raise ExtractionError(X_PREFIX_CONFLICT, "Файл и каталог имеют один путь")
    for parts in dirs:
        for index in range(1, len(parts)):
            if parts[:index] in file_paths:
                raise ExtractionError(
                    X_PREFIX_CONFLICT,
                    "Файл не может быть родительским каталогом каталога",
                )
    return files, dirs


def extract_zip(
    data: bytes,
    destination: Path,
    *,
    max_file_bytes: int = MAX_FILE_BYTES,
    max_total_bytes: int = MAX_UNCOMPRESSED_BYTES,
    max_files: int = MAX_FILES,
    deadline: float | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> ExtractionResult:
    """Extract ``data`` into a new ``destination`` directory.

    ``deadline`` is an absolute :func:`time.monotonic` value. ``cancel_check``
    is polled at bounded intervals (64 KiB chunks) and aborts with
    ``X_CANCELLED``; ``None`` preserves the previous behaviour. CPU, RAM, disk
    and network limits remain the responsibility of the isolated worker.
    """
    if not isinstance(data, bytes):
        data = bytes(data)
    report = preflight_zip(data)
    if not report.ok:
        raise ExtractionError(
            X_PREFLIGHT_REJECTED,
            "Архив не прошёл preflight",
            report=report,
        )

    max_file_bytes = min(max_file_bytes, MAX_FILE_BYTES)
    max_total_bytes = min(max_total_bytes, MAX_UNCOMPRESSED_BYTES)
    max_files = min(max_files, MAX_FILES)

    destination = Path(destination)
    if os.path.lexists(destination):
        raise ExtractionError(X_DESTINATION_EXISTS, "Целевой каталог уже существует")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise ExtractionError(X_IO, "Не удалось подготовить целевой каталог") from None

    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile, zipfile.LargeZipFile, OSError, RuntimeError:
        raise ExtractionError(X_ARCHIVE_BAD, "Некорректный ZIP-архив") from None

    with archive:
        infos = archive.infolist()
        if len(infos) > max_files:
            raise ExtractionError(X_LIMIT_FILES, "Превышен лимит числа записей")
        files, dirs = _entries(infos)

        try:
            staging = Path(tempfile.mkdtemp(prefix=".ba-extract-", dir=destination.parent))
        except OSError:
            raise ExtractionError(X_IO, "Не удалось создать staging-каталог") from None
        published = False
        try:
            for parts in sorted(dirs):
                if deadline is not None and time.monotonic() > deadline:
                    raise ExtractionError(X_TIMEOUT, "Превышено время распаковки")
                if cancel_check is not None and cancel_check():
                    raise ExtractionError(X_CANCELLED, "Распаковка отменена")
                _ensure_dir(staging, parts)

            extracted: list[ExtractedFile] = []
            total = 0
            for info, parts in files:
                if deadline is not None and time.monotonic() > deadline:
                    raise ExtractionError(X_TIMEOUT, "Превышено время распаковки")
                if cancel_check is not None and cancel_check():
                    raise ExtractionError(X_CANCELLED, "Распаковка отменена")
                _ensure_dir(staging, parts[:-1])
                target = staging.joinpath(*parts)
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                try:
                    fd = os.open(target, flags, 0o600)
                except OSError:
                    raise ExtractionError(X_IO, "Не удалось создать файл") from None

                hasher = hashlib.sha256()
                size = 0
                try:
                    with os.fdopen(fd, "wb") as sink, archive.open(info) as source:
                        while True:
                            chunk = source.read(_CHUNK)
                            if not chunk:
                                break
                            size += len(chunk)
                            total += len(chunk)
                            if size > max_file_bytes:
                                raise ExtractionError(
                                    X_LIMIT_FILE,
                                    "Файл превышает лимит распаковки",
                                )
                            if total > max_total_bytes:
                                raise ExtractionError(
                                    X_LIMIT_TOTAL,
                                    "Пакет превышает лимит распаковки",
                                )
                            if deadline is not None and time.monotonic() > deadline:
                                raise ExtractionError(X_TIMEOUT, "Превышено время распаковки")
                            if cancel_check is not None and cancel_check():
                                raise ExtractionError(X_CANCELLED, "Распаковка отменена")
                            sink.write(chunk)
                            hasher.update(chunk)
                except zipfile.BadZipFile:
                    raise ExtractionError(
                        X_CRC_MISMATCH, "CRC или данные файла повреждены"
                    ) from None
                except RuntimeError, EOFError, lzma.LZMAError:
                    raise ExtractionError(X_ARCHIVE_BAD, "Не удалось прочитать файл") from None
                except OSError:
                    raise ExtractionError(X_IO, "Ошибка записи") from None

                if size != info.file_size:
                    raise ExtractionError(
                        X_SIZE_MISMATCH,
                        "Фактический размер не совпадает с заголовком",
                    )
                extracted.append(
                    ExtractedFile(
                        path="/".join(parts),
                        size=size,
                        sha256=hasher.hexdigest(),
                    )
                )

            try:
                staging.rename(destination)
            except OSError as exc:
                code = (
                    X_DESTINATION_EXISTS if exc.errno in {errno.EEXIST, errno.ENOTEMPTY} else X_IO
                )
                raise ExtractionError(code, "Не удалось опубликовать результат") from None
            published = True
        finally:
            if not published:
                with contextlib.suppress(OSError, RecursionError):
                    shutil.rmtree(staging, ignore_errors=True)

    return ExtractionResult(
        root=destination.resolve(),
        package_hash=report.package_hash,
        files=tuple(extracted),
        total_bytes=total,
        preflight=report,
    )
