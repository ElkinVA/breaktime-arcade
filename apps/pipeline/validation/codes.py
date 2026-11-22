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
V_METHOD_UNSUPPORTED = "V_METHOD_UNSUPPORTED"
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

# Content-level (§2.14.2, Приложение K)
V_MANIFEST_MISSING = "V_MANIFEST_MISSING"
V_MANIFEST_SCHEMA = "V_MANIFEST_SCHEMA"
V_ENCODING = "V_ENCODING"
V_ID_FORMAT = "V_ID_FORMAT"
V_ID_MISMATCH = "V_ID_MISMATCH"
V_VERSION_DUP = "V_VERSION_DUP"
V_SDK_MISSING = "V_SDK_MISSING"
V_SDK_INCOMPATIBLE = "V_SDK_INCOMPATIBLE"
V_ENTRY_INVALID = "V_ENTRY_INVALID"
V_CRITICAL_MISSING = "V_CRITICAL_MISSING"
V_CRITICAL_TOO_LARGE = "V_CRITICAL_TOO_LARGE"
V_EXTERNAL_ORIGIN = "V_EXTERNAL_ORIGIN"
V_EXTERNAL_URL = "V_EXTERNAL_URL"
V_ABSOLUTE_PATH = "V_ABSOLUTE_PATH"
V_FORBIDDEN_API = "V_FORBIDDEN_API"
V_GENRE_UNKNOWN = "V_GENRE_UNKNOWN"
V_LANG_UNKNOWN = "V_LANG_UNKNOWN"
V_LOCALE_MISSING = "V_LOCALE_MISSING"
V_LOCALE_PARITY = "V_LOCALE_PARITY"
V_CATALOG_MISSING = "V_CATALOG_MISSING"
V_CATALOG_SCHEMA = "V_CATALOG_SCHEMA"
V_COVER_MISSING = "V_COVER_MISSING"
V_COVER_SIZE = "V_COVER_SIZE"
V_SCREENSHOT_COUNT = "V_SCREENSHOT_COUNT"
V_SCORE_BOUNDS = "V_SCORE_BOUNDS"
V_LIMITS_RANGE = "V_LIMITS_RANGE"
V_STORAGE_LOCAL = "V_STORAGE_LOCAL"
V_EVENT_SCHEMA = "V_EVENT_SCHEMA"
V_AUTOTEST_FAILED = "V_AUTOTEST_FAILED"
V_MANUAL_REVIEW_REQUIRED = "V_MANUAL_REVIEW_REQUIRED"
V_EPOCH_DECISION_REQUIRED = "V_EPOCH_DECISION_REQUIRED"

# Warnings (§2.14.2, Приложение K)
W_PACKAGE_LARGE = "W_PACKAGE_LARGE"
W_CRITICAL_DECLARED_MISMATCH = "W_CRITICAL_DECLARED_MISMATCH"
W_CRITICAL_OVER_2MB = "W_CRITICAL_OVER_2MB"
W_TAG_NEW = "W_TAG_NEW"
W_TAG_UNTRANSLATED = "W_TAG_UNTRANSLATED"
W_LANG_PARTIAL = "W_LANG_PARTIAL"
W_SEMVER_LOWER = "W_SEMVER_LOWER"
W_ALT_MISSING = "W_ALT_MISSING"
W_UNUSED_ASSET = "W_UNUSED_ASSET"
W_CREDITS_INCOMPLETE = "W_CREDITS_INCOMPLETE"
W_SCORE_RULES_CHANGED = "W_SCORE_RULES_CHANGED"
W_IMPORT_CONFLICT = "W_IMPORT_CONFLICT"

# Informational (§2.14.2, Приложение K)
I_SDK_INJECTED = "I_SDK_INJECTED"
I_RUNTIME_HASH = "I_RUNTIME_HASH"
I_IMPORT_CREATED = "I_IMPORT_CREATED"
I_IMPORT_UPDATED = "I_IMPORT_UPDATED"
I_IMPORT_CONFLICT = "I_IMPORT_CONFLICT"
I_DUPLICATE_PACKAGE = "I_DUPLICATE_PACKAGE"

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
