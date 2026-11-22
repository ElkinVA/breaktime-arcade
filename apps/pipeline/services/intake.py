"""Package intake: preflight and immutable storage (§2.14.1, §2.14.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from apps.pipeline.services.artifacts import (
    ArtifactError,
    ensure_root,
    package_path,
    store_immutable,
)
from apps.pipeline.validation.codes import Diagnostic
from apps.pipeline.validation.report import ValidationReport
from apps.pipeline.validation.structure import preflight_zip


@dataclass(slots=True)
class IntakeResult:
    package_hash: str = ""
    size_bytes: int = 0
    stored_path: Path | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(item.severity == "blocker" for item in self.diagnostics)


def intake_zip(data: bytes, *, storage_root: Path) -> IntakeResult:
    """Run metadata-only preflight and persist the original ZIP unchanged."""
    report = preflight_zip(data)
    result = IntakeResult(
        package_hash=report.package_hash,
        size_bytes=len(data),
        diagnostics=list(report.diagnostics),
    )
    if not report.ok:
        return result
    root = ensure_root(storage_root)
    target = package_path(root, report.package_hash)
    try:
        store_immutable(target, data)
    except ArtifactError as exc:
        result.diagnostics.append(
            Diagnostic(code=exc.code, severity="blocker", message=exc.message)
        )
        return result
    result.stored_path = target
    return result


def report_for(intake: IntakeResult) -> ValidationReport:
    report = ValidationReport(package_hash=intake.package_hash)
    report.extend(intake.diagnostics)
    return report
