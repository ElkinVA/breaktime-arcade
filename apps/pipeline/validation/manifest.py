"""Manifest discovery and JSON Schema validation (BA-GAME-2.2 §5)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from apps.core.contracts import SCHEMA_DIR
from apps.pipeline.validation.codes import (
    SEVERITY_BLOCKER,
    V_CRITICAL_MISSING,
    V_ENCODING,
    V_ENTRY_INVALID,
    V_EVENT_SCHEMA,
    V_EXTERNAL_ORIGIN,
    V_ID_FORMAT,
    V_LIMITS_RANGE,
    V_MANIFEST_MISSING,
    V_MANIFEST_SCHEMA,
    V_SCORE_BOUNDS,
    V_STORAGE_LOCAL,
    Diagnostic,
)
from apps.pipeline.validation.report import ValidationReport
from apps.pipeline.validation.text import has_bom, has_crlf, read_text, relative

MANIFEST_NAME = "manifest.json"
REQUIRED_CRITICAL = (
    "index.html",
    "css/style.css",
    "js/ba-sdk.js",
    "js/rng.js",
    "js/game.js",
)


@dataclass(slots=True)
class ManifestResult:
    root: Path
    manifest: dict[str, Any] | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.manifest is not None and not any(
            item.severity == SEVERITY_BLOCKER for item in self.diagnostics
        )


def locate_package_root(extracted_root: Path) -> Path | None:
    """Return the directory that contains ``manifest.json``.

    The archive contract allows files either at the root or inside a single
    top-level directory (§3). Anything else is ambiguous and rejected.
    """
    if (extracted_root / MANIFEST_NAME).is_file():
        candidates = [extracted_root]
    else:
        candidates = [
            path
            for path in extracted_root.iterdir()
            if path.is_dir() and not path.is_symlink() and (path / MANIFEST_NAME).is_file()
        ]
    if len(candidates) == 1:
        return candidates[0]
    return None


def _schema_errors(instance: object) -> list[str]:
    schema: dict[str, Any] = json.loads((SCHEMA_DIR / "manifest.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors: list[str] = []
    for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path)):
        location = "/".join(str(part) for part in error.path) or "(root)"
        errors.append(f"{location}: {error.message}")
    return errors


def _semantic_checks(
    report: ValidationReport,
    manifest: dict[str, Any],
) -> None:
    languages = manifest.get("supportedLanguages")
    default_language = manifest.get("defaultLanguage")
    if (
        isinstance(languages, list)
        and isinstance(default_language, str)
        and default_language not in languages
    ):
        report.add(
            V_MANIFEST_SCHEMA,
            "defaultLanguage отсутствует в supportedLanguages",
            file=MANIFEST_NAME,
            hint="Добавьте язык по умолчанию в supportedLanguages.",
        )

    if manifest.get("entry") != "index.html":
        report.add(V_ENTRY_INVALID, "Точка входа должна быть index.html", file=MANIFEST_NAME)

    capabilities = manifest.get("capabilities")
    if isinstance(capabilities, dict):
        if capabilities.get("storage") != "sdk":
            report.add(
                V_STORAGE_LOCAL,
                'capabilities.storage должен быть "sdk"',
                file=MANIFEST_NAME,
            )
        origins = capabilities.get("externalOrigins")
        if isinstance(origins, list) and origins:
            report.add(
                V_EXTERNAL_ORIGIN,
                "Внешние origin запрещены",
                file=MANIFEST_NAME,
                meta={"origins": origins},
            )

    score = manifest.get("score")
    if isinstance(score, dict):
        minimum = score.get("minValue")
        maximum = score.get("maxValue")
        if (
            isinstance(minimum, (int, float))
            and isinstance(maximum, (int, float))
            and minimum > maximum
        ):
            report.add(
                V_SCORE_BOUNDS,
                "score.minValue больше score.maxValue",
                file=MANIFEST_NAME,
            )

    limits = manifest.get("limits")
    if isinstance(limits, dict):
        minimum = limits.get("minPlaytimeSeconds")
        maximum = limits.get("maxSessionSeconds")
        if isinstance(minimum, int) and isinstance(maximum, int) and minimum > maximum:
            report.add(
                V_LIMITS_RANGE,
                "minPlaytimeSeconds больше maxSessionSeconds",
                file=MANIFEST_NAME,
            )

    leaderboard = manifest.get("leaderboard")
    if (
        isinstance(leaderboard, dict)
        and leaderboard.get("claimedVerification") == "replay_verified"
        and not isinstance(manifest.get("verification"), dict)
    ):
        report.add(
            V_EVENT_SCHEMA,
            "replay_verified требует блок verification",
            file=MANIFEST_NAME,
        )

    assets = manifest.get("assets")
    if isinstance(assets, dict):
        critical = assets.get("critical")
        if isinstance(critical, list):
            missing = [item for item in REQUIRED_CRITICAL if item not in critical]
            if missing:
                report.add(
                    V_CRITICAL_MISSING,
                    "Критический путь не содержит обязательных файлов",
                    file=MANIFEST_NAME,
                    meta={"missing": missing},
                )
        if isinstance(default_language, str):
            locale = f"locales/{default_language}.json"
            if isinstance(critical, list) and locale not in critical:
                report.add(
                    V_CRITICAL_MISSING,
                    "Критический путь не содержит локаль по умолчанию",
                    file=MANIFEST_NAME,
                    meta={"missing": [locale]},
                )


def validate_manifest(root: Path) -> ManifestResult:
    result = ManifestResult(root=root)
    path = root / MANIFEST_NAME
    report = ValidationReport()
    if not path.is_file():
        report.add(V_MANIFEST_MISSING, "manifest.json отсутствует", file=MANIFEST_NAME)
        result.diagnostics = report.diagnostics
        return result
    if has_bom(path):
        report.add(V_ENCODING, "manifest.json содержит UTF-8 BOM", file=MANIFEST_NAME)
        result.diagnostics = report.diagnostics
        return result
    if has_crlf(path):
        report.add(V_ENCODING, "manifest.json содержит CRLF", file=MANIFEST_NAME)
        result.diagnostics = report.diagnostics
        return result
    try:
        manifest = json.loads(read_text(path))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        report.add(
            V_MANIFEST_SCHEMA,
            "manifest.json не является корректным JSON",
            file=MANIFEST_NAME,
            meta={"error": str(exc)},
        )
        result.diagnostics = report.diagnostics
        return result
    if not isinstance(manifest, dict):
        report.add(V_MANIFEST_SCHEMA, "manifest.json должен быть объектом", file=MANIFEST_NAME)
        result.diagnostics = report.diagnostics
        return result

    manifest_id = manifest.get("id")
    if isinstance(manifest_id, str) and not _valid_id(manifest_id):
        report.add(
            V_ID_FORMAT,
            "manifest.id не соответствует формату",
            file=MANIFEST_NAME,
            meta={"id": manifest_id},
        )

    for error in _schema_errors(manifest):
        report.add(V_MANIFEST_SCHEMA, error, file=MANIFEST_NAME)
    _semantic_checks(report, manifest)
    result.manifest = manifest
    result.diagnostics = report.diagnostics
    return result


def _valid_id(value: str) -> bool:
    if not 3 <= len(value) <= 40:
        return False
    if not value[0].islower() or not value[0].isalpha():
        return False
    if not (value[-1].islower() or value[-1].isdigit()):
        return False
    return all(char.islower() or char.isdigit() or char == "_" for char in value)


def manifest_diagnostics(
    report: ValidationReport,
    result: ManifestResult,
    *,
    root: Path,
) -> None:
    """Copy manifest diagnostics into a shared report with relative paths."""
    for item in result.diagnostics:
        if item.file:
            item.file = relative(root, root / item.file)
        report.diagnostics.append(item)
