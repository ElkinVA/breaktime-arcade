"""Stable validation codes and diagnostics for the game package pipeline.

Codes are part of the CRM contract (§2.14.7): they are stable, machine-readable,
and paired with a human message/hint. The preflight stage only inspects the
archive directory; it never extracts or executes package content.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SEVERITY_BLOCKER = "blocker"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

# Archive-level
V_ARCHIVE_BAD = "V_ARCHIVE_BAD"
V_ARCHIVE_HEADER_MISMATCH = "V_ARCHIVE_HEADER_MISMATCH"
V_ARCHIVE_ENCRYPTED = "V_ARCHIVE_ENCRYPTED"
V_ARCHIVE_EMPTY = "V_ARCHIVE_EMPTY"
V_ARCHIVE_TOO_LARGE = "V_ARCHIVE_TOO_LARGE"
V_ARCHIVE_TOO_MANY_FILES = "V_ARCHIVE_TOO_MANY_FILES"
V_ARCHIVE_UNCOMPRESSED_TOO_LARGE = "V_ARCHIVE_UNCOMPRESSED_TOO_LARGE"
V_COMPRESSION_RATIO = "V_COMPRESSION_RATIO"

# Entry-level
V_FILE_TOO_LARGE = "V_FILE_TOO_LARGE"
V_PATH_ABSOLUTE = "V_PATH_ABSOLUTE"
V_PATH_TRAVERSAL = "V_PATH_TRAVERSAL"
V_PATH_BACKSLASH = "V_PATH_BACKSLASH"
V_PATH_INVALID = "V_PATH_INVALID"
V_SYMLINK = "V_SYMLINK"
V_SPECIAL_ENTRY = "V_SPECIAL_ENTRY"
V_EXT_UNSUPPORTED = "V_EXT_UNSUPPORTED"
V_SERVICE_FILE = "V_SERVICE_FILE"
V_PATH_DUPLICATE = "V_PATH_DUPLICATE"
V_PATH_COLLISION = "V_PATH_COLLISION"

MAX_ZIP_BYTES = 25 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_FILES = 2000
MAX_COMPRESSION_RATIO = 100

ALLOWED_EXTENSIONS = frozenset(
    {
        ".html",
        ".css",
        ".js",
        ".mjs",
        ".json",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".avif",
        ".gif",
        ".svg",
        ".woff2",
        ".mp3",
        ".ogg",
        ".wav",
        ".wasm",
        ".txt",
        ".md",
    }
)
SERVICE_SEGMENTS = frozenset({".git", "__macosx", "node_modules"})
SERVICE_NAMES = frozenset({".ds_store"})
FORBIDDEN_SUFFIXES = (".map",)
WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)}
)


@dataclass(slots=True)
class Diagnostic:
    code: str
    severity: str
    message: str
    hint: str = ""
    file: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }
        if self.file:
            payload["file"] = self.file
        if self.hint:
            payload["hint"] = self.hint
        if self.meta:
            payload["meta"] = self.meta
        return payload


@dataclass(slots=True)
class PreflightReport:
    package_hash: str
    file_count: int = 0
    total_uncompressed: int = 0
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(item.severity == SEVERITY_BLOCKER for item in self.diagnostics)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "package_hash": self.package_hash,
            "file_count": self.file_count,
            "total_uncompressed": self.total_uncompressed,
            "diagnostics": [item.as_dict() for item in self.diagnostics],
        }
