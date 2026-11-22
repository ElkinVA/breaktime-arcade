"""Critical-path budget diagnostics (§2.14.2, §2.14.3)."""

from __future__ import annotations

from apps.pipeline.services.critical_path import CriticalPathResult
from apps.pipeline.validation.codes import (
    SEVERITY_BLOCKER,
    SEVERITY_WARNING,
    V_CRITICAL_MISSING,
    V_CRITICAL_TOO_LARGE,
    W_CRITICAL_DECLARED_MISMATCH,
    W_CRITICAL_OVER_2MB,
    Diagnostic,
)

DECLARED_MISMATCH_RATIO = 0.10


def budget_diagnostics(
    result: CriticalPathResult,
    declared_bytes: int | None,
    *,
    warn_bytes: int,
    max_bytes: int,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if result.missing:
        diagnostics.append(
            Diagnostic(
                code=V_CRITICAL_MISSING,
                severity=SEVERITY_BLOCKER,
                message="Обязательные файлы критического пути отсутствуют",
                hint=(
                    "Добавьте обязательные файлы: index.html, css/style.css, js/ba-sdk.js, "
                    "js/game.js, js/rng.js, локаль по умолчанию."
                ),
                file=result.missing[0],
                meta={"missing": result.missing},
            )
        )
    if result.measured_bytes > max_bytes:
        diagnostics.append(
            Diagnostic(
                code=V_CRITICAL_TOO_LARGE,
                severity=SEVERITY_BLOCKER,
                message="Критический путь превышает 4 МБ gzip",
                file="manifest.json",
                meta={"measured": result.measured_bytes, "limit": max_bytes},
            )
        )
    elif result.measured_bytes > warn_bytes:
        diagnostics.append(
            Diagnostic(
                code=W_CRITICAL_OVER_2MB,
                severity=SEVERITY_WARNING,
                message="Критический путь превышает 2 МБ gzip",
                file="manifest.json",
                meta={"measured": result.measured_bytes, "limit": warn_bytes},
            )
        )
    if declared_bytes is not None and declared_bytes > 0:
        discrepancy = abs(result.measured_bytes - declared_bytes) / declared_bytes
        if discrepancy > DECLARED_MISMATCH_RATIO:
            diagnostics.append(
                Diagnostic(
                    code=W_CRITICAL_DECLARED_MISMATCH,
                    severity=SEVERITY_WARNING,
                    message=(
                        "Фактический критический путь расходится с заявленным более чем на 10 %"
                    ),
                    file="manifest.json",
                    meta={
                        "declared": declared_bytes,
                        "measured": result.measured_bytes,
                        "discrepancy": round(discrepancy, 4),
                    },
                )
            )
    return diagnostics
