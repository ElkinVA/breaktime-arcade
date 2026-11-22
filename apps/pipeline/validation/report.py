"""Structured validation report (§2.14.7).

A report is JSON-first (persisted as ``GameVersion.validation_report``) and has
a human-readable Markdown rendering for the CRM download button. Every entry
carries a stable technical code, a localized message, an optional file and a
repair hint.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from apps.pipeline.validation.codes import (
    SEVERITY_BLOCKER,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    Diagnostic,
)


@dataclass(slots=True)
class ValidationReport:
    """Accumulates diagnostics for a single package."""

    package_hash: str = ""
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def add(
        self,
        code: str,
        message: str,
        *,
        severity: str = SEVERITY_BLOCKER,
        hint: str = "",
        file: str = "",
        meta: dict[str, Any] | None = None,
    ) -> None:
        self.diagnostics.append(
            Diagnostic(
                code=code,
                severity=severity,
                message=message,
                hint=hint,
                file=file,
                meta=dict(meta or {}),
            )
        )

    def extend(self, diagnostics: list[Diagnostic]) -> None:
        self.diagnostics.extend(diagnostics)

    def count(self, severity: str) -> int:
        return sum(1 for item in self.diagnostics if item.severity == severity)

    @property
    def ok(self) -> bool:
        return self.count(SEVERITY_BLOCKER) == 0

    @property
    def blocker_count(self) -> int:
        return self.count(SEVERITY_BLOCKER)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "package_hash": self.package_hash,
            "summary": {
                SEVERITY_BLOCKER: self.count(SEVERITY_BLOCKER),
                SEVERITY_WARNING: self.count(SEVERITY_WARNING),
                SEVERITY_INFO: self.count(SEVERITY_INFO),
            },
            "diagnostics": [item.as_dict() for item in self.diagnostics],
        }

    def to_markdown(self) -> str:
        lines = [
            "# Отчёт валидации пакета",
            "",
            f"- package_hash: `{self.package_hash}`"
            if self.package_hash
            else "- package_hash: n/a",
            f"- blocker: {self.count(SEVERITY_BLOCKER)}",
            f"- warning: {self.count(SEVERITY_WARNING)}",
            f"- info: {self.count(SEVERITY_INFO)}",
            f"- итог: {'OK' if self.ok else 'REJECTED'}",
            "",
        ]
        if not self.diagnostics:
            lines.append("Замечаний нет.")
            return "\n".join(lines) + "\n"
        lines.extend(["| severity | code | file | message | hint |", "|---|---|---|---|---|"])
        for item in self.diagnostics:
            lines.append(
                "| {severity} | {code} | {file} | {message} | {hint} |".format(
                    severity=item.severity,
                    code=item.code,
                    file=item.file or "—",
                    message=item.message.replace("|", "\\|"),
                    hint=(item.hint or "—").replace("|", "\\|"),
                )
            )
        return "\n".join(lines) + "\n"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
