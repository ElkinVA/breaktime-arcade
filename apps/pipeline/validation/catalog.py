"""Catalog file validation (BA-GAME-2.2 §11, §2.14.4)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from apps.core.contracts import SCHEMA_DIR
from apps.pipeline.validation.codes import (
    V_CATALOG_MISSING,
    V_CATALOG_SCHEMA,
    Diagnostic,
)
from apps.pipeline.validation.report import ValidationReport
from apps.pipeline.validation.text import read_text

CATALOG_DIR = "catalog"


@dataclass(slots=True)
class CatalogEntry:
    language: str
    data: dict[str, Any]
    path: str


@dataclass(slots=True)
class CatalogResult:
    entries: dict[str, CatalogEntry] = field(default_factory=dict)
    diagnostics: list[Diagnostic] = field(default_factory=list)


def _schema_errors(instance: object) -> list[str]:
    schema: dict[str, Any] = json.loads((SCHEMA_DIR / "catalog.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors: list[str] = []
    for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path)):
        location = "/".join(str(part) for part in error.path) or "(root)"
        errors.append(f"{location}: {error.message}")
    return errors


def validate_catalog(
    root: Path,
    supported_languages: list[str],
    screenshot_count: int,
) -> CatalogResult:
    result = CatalogResult()
    report = ValidationReport()
    for language in supported_languages:
        relative_path = f"{CATALOG_DIR}/{language}.json"
        path = root / relative_path
        if not path.is_file():
            report.add(
                V_CATALOG_MISSING,
                f"Каталожный файл для языка «{language}» отсутствует",
                file=relative_path,
            )
            continue
        try:
            data = json.loads(read_text(path))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            report.add(
                V_CATALOG_SCHEMA,
                "Каталожный файл не является корректным JSON",
                file=relative_path,
                meta={"error": str(exc)},
            )
            continue
        if not isinstance(data, dict):
            report.add(
                V_CATALOG_SCHEMA,
                "Каталожный файл должен быть объектом",
                file=relative_path,
            )
            continue
        for error in _schema_errors(data):
            report.add(V_CATALOG_SCHEMA, error, file=relative_path)
        alts = data.get("screenshotAlts")
        if isinstance(alts, list) and len(alts) != screenshot_count:
            report.add(
                V_CATALOG_SCHEMA,
                "Число screenshotAlts не совпадает с числом скриншотов",
                file=relative_path,
                meta={"expected": screenshot_count, "actual": len(alts)},
            )
        result.entries[language] = CatalogEntry(language=language, data=data, path=relative_path)
    result.diagnostics = report.diagnostics
    return result
