"""Measured critical path after SDK injection (§2.14.3)."""

from __future__ import annotations

import gzip
from dataclasses import dataclass, field
from pathlib import Path

MANDATORY_CRITICAL = (
    "index.html",
    "css/style.css",
    "js/ba-sdk.js",
    "js/game.js",
    "js/rng.js",
)


@dataclass(slots=True)
class CriticalPathResult:
    measured_bytes: int = 0
    files: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def measure_critical_path(
    root: Path,
    critical: list[str],
    default_language: str | None = None,
) -> CriticalPathResult:
    """Gzip-sum the declared critical files and the mandatory minimum."""
    names = list(dict.fromkeys([*MANDATORY_CRITICAL, *critical]))
    if default_language:
        names.append(f"locales/{default_language}.json")
    result = CriticalPathResult()
    total = 0
    for name in names:
        path = root / name
        if not path.is_file() or path.is_symlink():
            result.missing.append(name)
            continue
        try:
            data = path.read_bytes()
        except OSError:
            result.missing.append(name)
            continue
        total += len(gzip.compress(data, mtime=0))
        result.files.append(name)
    result.measured_bytes = total
    return result
