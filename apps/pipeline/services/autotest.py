"""Static autotest report (§2.14.8).

This deterministic pass checks the runtime bundle invariants that can be
verified without a browser. The importer merges its report with the isolated
browser runner's handshake evidence when that gate is enabled; publication
requires a green merged report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from apps.pipeline.services.critical_path import CriticalPathResult
from apps.pipeline.validation.locales import validate_locales
from apps.pipeline.validation.security_scan import scan_root


@dataclass(slots=True)
class AutotestCheck:
    name: str
    passed: bool
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(slots=True)
class AutotestResult:
    passed: bool
    report: dict[str, Any]
    checks: list[AutotestCheck] = field(default_factory=list)


def run_autotest(
    runtime_root: Path,
    *,
    manifest: dict[str, Any],
    sdk_path: Path,
    critical_path: CriticalPathResult,
    max_critical_bytes: int,
) -> AutotestResult:
    checks: list[AutotestCheck] = []

    entry = runtime_root / str(manifest.get("entry", "index.html"))
    checks.append(
        AutotestCheck(
            name="entry",
            passed=entry.is_file() and entry.stat().st_size > 0,
            detail=str(manifest.get("entry", "index.html")),
        )
    )

    sdk_target = runtime_root / "js" / "ba-sdk.js"
    sdk_ok = sdk_target.is_file() and sdk_target.read_bytes() == sdk_path.read_bytes()
    checks.append(AutotestCheck(name="sdk_injection", passed=sdk_ok, detail="official SDK"))

    languages = manifest.get("supportedLanguages")
    language_list = [str(item) for item in languages] if isinstance(languages, list) else []
    locales = validate_locales(runtime_root, language_list)
    checks.append(
        AutotestCheck(
            name="locales",
            passed=not locales.diagnostics,
            detail=f"{len(locales.locales)} locale(s)",
        )
    )

    security = scan_root(runtime_root)
    checks.append(
        AutotestCheck(
            name="security_scan",
            passed=not security.diagnostics,
            detail=f"{len(security.diagnostics)} issue(s)",
        )
    )

    checks.append(
        AutotestCheck(
            name="critical_path",
            passed=critical_path.measured_bytes <= max_critical_bytes,
            detail=f"{critical_path.measured_bytes} bytes (limit {max_critical_bytes})",
        )
    )

    passed = all(item.passed for item in checks)
    report: dict[str, Any] = {
        "passed": passed,
        "kind": "static",
        "playwright": False,
        "generated_at": datetime.now(UTC).isoformat(),
        "checks": [item.as_dict() for item in checks],
        "notes": [
            "Static bundle checks only; a browser handshake report is merged "
            "separately by the isolated browser runner when enabled.",
        ],
    }
    return AutotestResult(passed=passed, report=report, checks=checks)
