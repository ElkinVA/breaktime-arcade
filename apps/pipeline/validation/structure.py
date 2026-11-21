"""Safe ZIP preflight (§2.14.2): metadata only, no extraction, no execution.

Only the archive directory is inspected. Paths, entry types, limits and
collisions are checked before any future extraction stage; this module never
writes to disk, so Zip Slip/symlink attacks cannot materialise here.
"""

from __future__ import annotations

import hashlib
import io
import re
import stat
import struct
import unicodedata
import zipfile

from apps.pipeline.validation.codes import (
    ALLOWED_EXTENSIONS,
    FORBIDDEN_SUFFIXES,
    MAX_COMPRESSION_RATIO,
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_UNCOMPRESSED_BYTES,
    MAX_ZIP_BYTES,
    SERVICE_NAMES,
    SERVICE_SEGMENTS,
    SEVERITY_BLOCKER,
    V_ARCHIVE_BAD,
    V_ARCHIVE_EMPTY,
    V_ARCHIVE_ENCRYPTED,
    V_ARCHIVE_HEADER_MISMATCH,
    V_ARCHIVE_TOO_LARGE,
    V_ARCHIVE_TOO_MANY_FILES,
    V_ARCHIVE_UNCOMPRESSED_TOO_LARGE,
    V_COMPRESSION_RATIO,
    V_EXT_UNSUPPORTED,
    V_FILE_TOO_LARGE,
    V_METHOD_UNSUPPORTED,
    V_PATH_ABSOLUTE,
    V_PATH_BACKSLASH,
    V_PATH_COLLISION,
    V_PATH_DUPLICATE,
    V_PATH_INVALID,
    V_PATH_TRAVERSAL,
    V_SERVICE_FILE,
    V_SPECIAL_ENTRY,
    V_SYMLINK,
    WINDOWS_RESERVED,
    Diagnostic,
    PreflightReport,
)

_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_BAD_UNICODE = {"‪", "‫", "‬", "‭", "‮", "⁦", "⁧", "⁨", "⁩"}


def _diag(
    report: PreflightReport,
    code: str,
    message: str,
    *,
    hint: str = "",
    file: str = "",
    severity: str = SEVERITY_BLOCKER,
    meta: dict[str, object] | None = None,
) -> None:
    report.diagnostics.append(
        Diagnostic(
            code=code,
            severity=severity,
            message=message,
            hint=hint,
            file=file,
            meta=dict(meta or {}),
        )
    )


def _check_name(report: PreflightReport, name: str) -> list[str]:
    """Validate a ZIP path; return it split into non-empty segments."""
    if "\\" in name:
        _diag(report, V_PATH_BACKSLASH, "Обратные слэши в пути запрещены", file=name)
    normalized = unicodedata.normalize("NFKC", name)
    if normalized != name:
        _diag(
            report,
            V_PATH_INVALID,
            "Unicode-нормализация меняет путь",
            file=name,
            hint="Используйте каноническое имя без полноширинных/совместимых символов.",
        )
    if normalized.startswith("/") or _DRIVE_RE.match(normalized):
        _diag(report, V_PATH_ABSOLUTE, "Абсолютные пути запрещены", file=name)
    if any(ord(char) < 32 for char in normalized) or any(
        char in _BAD_UNICODE for char in normalized
    ):
        _diag(report, V_PATH_INVALID, "Управляющие символы в пути запрещены", file=name)
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        _diag(report, V_PATH_TRAVERSAL, "Path traversal (..) запрещён", file=name)
    canonical = "/".join(parts)
    if canonical != normalized.rstrip("/"):
        _diag(
            report,
            V_PATH_INVALID,
            "Неканонический путь (., // или пустой компонент)",
            file=name,
            hint="Используйте относительный путь без ./ и повторных слэшей.",
        )
    for part in parts:
        if len(part.encode("utf-8")) > 255:
            _diag(report, V_PATH_INVALID, "Компонент пути длиннее 255 байт", file=name)
        if part.endswith((".", " ")):
            _diag(
                report,
                V_PATH_INVALID,
                "Компонент пути не должен заканчиваться точкой или пробелом",
                file=name,
            )
        if part.split(".", 1)[0].casefold() in WINDOWS_RESERVED:
            _diag(report, V_PATH_INVALID, "Зарезервированное имя Windows", file=name)
    return parts


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def _local_size_mismatch(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bool:
    fp = archive.fp
    if fp is None:
        return False
    try:
        fp.seek(info.header_offset)
        header = fp.read(30)
    except OSError:
        return True
    if len(header) != 30 or header[:4] != b"PK\x03\x04":
        return True
    flags = struct.unpack_from("<H", header, 6)[0]
    if flags & 0x8:  # data descriptor: sizes live after the payload
        return False
    compressed, uncompressed = struct.unpack_from("<II", header, 18)
    if compressed == 0xFFFFFFFF or uncompressed == 0xFFFFFFFF:
        return False
    central_compressed = info.compress_size & 0xFFFFFFFF
    central_uncompressed = info.file_size & 0xFFFFFFFF
    return bool(compressed != central_compressed or uncompressed != central_uncompressed)


def _is_dir(info: zipfile.ZipInfo) -> bool:
    """Match zipfile extraction semantics: only a trailing slash is a directory."""
    return info.filename.endswith("/")


def _type_mismatch(info: zipfile.ZipInfo) -> bool:
    mode_type = (info.external_attr >> 16) & 0o170000
    slash_dir = info.filename.endswith("/")
    return (mode_type == stat.S_IFDIR and not slash_dir) or (
        mode_type == stat.S_IFREG and slash_dir
    )


def _is_special(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    file_type = mode & 0o170000
    if file_type == 0:
        # Permission-only attributes (common in Python-created archives).
        return False
    return not (stat.S_ISREG(mode) or stat.S_ISDIR(mode))


def preflight_zip(data: bytes) -> PreflightReport:
    report = PreflightReport(package_hash=hashlib.sha256(data).hexdigest())
    if len(data) > MAX_ZIP_BYTES:
        _diag(
            report,
            V_ARCHIVE_TOO_LARGE,
            "Архив превышает 25 МБ",
            hint="Уменьшите пакет; рекомендуется ≤8 МБ.",
            meta={"size": len(data), "limit": MAX_ZIP_BYTES},
        )
        return report

    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile, zipfile.LargeZipFile, OSError, RuntimeError:
        _diag(report, V_ARCHIVE_BAD, "Файл не является корректным ZIP-архивом")
        return report

    with archive:
        infos = archive.infolist()
        if not infos:
            _diag(report, V_ARCHIVE_EMPTY, "Архив пуст")
            return report
        if len(infos) > MAX_FILES:
            _diag(
                report,
                V_ARCHIVE_TOO_MANY_FILES,
                "Слишком много файлов в архиве",
                meta={"count": len(infos), "limit": MAX_FILES},
            )
            return report

        exact_paths: set[str] = set()
        folded_paths: set[str] = set()
        report.file_count = sum(1 for info in infos if not _is_dir(info))
        total_uncompressed = 0

        for info in infos:
            name = info.filename
            parts = _check_name(report, name)

            if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                _diag(
                    report,
                    V_METHOD_UNSUPPORTED,
                    "Метод сжатия не поддерживается",
                    file=name,
                    hint="Разрешены только stored и deflate.",
                )

            if info.flag_bits & 0x1:
                _diag(report, V_ARCHIVE_ENCRYPTED, "Зашифрованные записи запрещены", file=name)
            if _is_symlink(info):
                _diag(report, V_SYMLINK, "Символические ссылки запрещены", file=name)
            elif _is_special(info):
                _diag(report, V_SPECIAL_ENTRY, "Специальные файлы запрещены", file=name)
            if _type_mismatch(info):
                _diag(
                    report,
                    V_SPECIAL_ENTRY,
                    "Тип записи не соответствует имени",
                    file=name,
                    hint="Каталог должен оканчиваться на '/', файл — нет.",
                )

            if _local_size_mismatch(archive, info):
                _diag(
                    report,
                    V_ARCHIVE_HEADER_MISMATCH,
                    "Размеры в local и central заголовках не совпадают",
                    file=name,
                    hint="Пакет повреждён или подделан; пересоберите ZIP.",
                )

            canonical = "/".join(parts)
            folded = canonical.casefold()
            if canonical in exact_paths:
                _diag(report, V_PATH_DUPLICATE, "Дублирующийся путь в архиве", file=name)
            elif folded in folded_paths:
                _diag(
                    report,
                    V_PATH_COLLISION,
                    "Пути различаются только регистром",
                    file=name,
                    hint="Переименуйте файл: регистронезависимые ФС могут конфликтовать.",
                )
            exact_paths.add(canonical)
            folded_paths.add(folded)

            lower_parts = [part.casefold() for part in parts]
            basename = lower_parts[-1] if lower_parts else ""
            if SERVICE_NAMES.intersection(lower_parts) or SERVICE_SEGMENTS.intersection(
                lower_parts
            ):
                _diag(report, V_SERVICE_FILE, "Служебные файлы/каталоги запрещены", file=name)
            if basename.endswith(FORBIDDEN_SUFFIXES):
                _diag(report, V_SERVICE_FILE, "Файлы source map запрещены", file=name)

            if _is_dir(info):
                continue

            suffix = f".{basename.rsplit('.', 1)[-1]}" if "." in basename else ""
            if suffix not in ALLOWED_EXTENSIONS:
                _diag(
                    report,
                    V_EXT_UNSUPPORTED,
                    "Недопустимое расширение файла",
                    file=name,
                    meta={"extension": suffix or "(none)"},
                )

            if info.file_size > MAX_FILE_BYTES:
                _diag(
                    report,
                    V_FILE_TOO_LARGE,
                    "Файл превышает 20 МБ",
                    file=name,
                    meta={"size": info.file_size, "limit": MAX_FILE_BYTES},
                )

            if info.file_size > 0:
                ratio = info.file_size / max(info.compress_size, 1)
                if info.compress_size == 0 or ratio > MAX_COMPRESSION_RATIO:
                    _diag(
                        report,
                        V_COMPRESSION_RATIO,
                        "Подозрительная степень сжатия (ZIP-бомба)",
                        file=name,
                        meta={
                            "uncompressed": info.file_size,
                            "compressed": info.compress_size,
                            "ratio": round(ratio, 2),
                        },
                    )

            total_uncompressed += info.file_size
            if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                _diag(
                    report,
                    V_ARCHIVE_UNCOMPRESSED_TOO_LARGE,
                    "Распакованный объём превышает 100 МБ",
                    meta={"size": total_uncompressed, "limit": MAX_UNCOMPRESSED_BYTES},
                )
                total_uncompressed = MAX_UNCOMPRESSED_BYTES  # report once
                break

        report.total_uncompressed = total_uncompressed
        if data and report.file_count and (total_uncompressed / len(data)) > MAX_COMPRESSION_RATIO:
            _diag(
                report,
                V_COMPRESSION_RATIO,
                "Общий коэффициент сжатия архива превышает 100:1",
                meta={"ratio": round(total_uncompressed / len(data), 2)},
            )
    return report
