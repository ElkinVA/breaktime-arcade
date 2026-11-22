"""Text file helpers shared by content validators (§2.14.2)."""

from __future__ import annotations

from pathlib import Path

TEXT_SUFFIXES = frozenset({".html", ".css", ".js", ".mjs", ".json", ".svg", ".txt", ".md"})
BOM = b"\xef\xbb\xbf"
MAX_TEXT_BYTES = 20 * 1024 * 1024


def read_text(path: Path) -> str:
    """Read UTF-8 text, rejecting BOM and NUL bytes."""
    raw = path.read_bytes()
    if raw.startswith(BOM):
        raise UnicodeDecodeError("utf-8-sig", raw, 0, 3, "UTF-8 BOM is not allowed")
    if b"\x00" in raw:
        raise UnicodeDecodeError("utf-8", raw, 0, 1, "NUL byte in text file")
    return raw.decode("utf-8")


def has_bom(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(3) == BOM
    except OSError:
        return False


def has_crlf(path: Path) -> bool:
    try:
        return b"\r\n" in path.read_bytes()
    except OSError:
        return False


def iter_text_files(root: Path) -> list[Path]:
    """All text files under ``root`` for encoding/security scans."""
    result: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        if path.suffix.lower() in TEXT_SUFFIXES:
            result.append(path)
    return result


def relative(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
