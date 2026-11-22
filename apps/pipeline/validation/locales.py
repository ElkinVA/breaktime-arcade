"""Locale file presence and key parity (§2.14.2, §2.15)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from apps.pipeline.validation.codes import (
    V_LOCALE_MISSING,
    V_LOCALE_PARITY,
    Diagnostic,
)
from apps.pipeline.validation.report import ValidationReport
from apps.pipeline.validation.text import read_text

LOCALES_DIR = "locales"
FALLBACK_LANGUAGE = "en"
_PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")


@dataclass(slots=True)
class LocaleResult:
    locales: dict[str, dict[str, Any]] = field(default_factory=dict)
    diagnostics: list[Diagnostic] = field(default_factory=list)


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            flat.update(_flatten(item, name))
    else:
        flat[prefix] = value
    return flat


def _placeholders(value: Any) -> set[str]:
    if not isinstance(value, str):
        return set()
    return set(_PLACEHOLDER_RE.findall(value))


def validate_locales(root: Path, supported_languages: list[str]) -> LocaleResult:
    result = LocaleResult()
    report = ValidationReport()
    languages = list(dict.fromkeys([*supported_languages, FALLBACK_LANGUAGE]))
    for language in languages:
        relative_path = f"{LOCALES_DIR}/{language}.json"
        path = root / relative_path
        if not path.is_file():
            report.add(
                V_LOCALE_MISSING,
                f"Файл локали «{language}» отсутствует",
                file=relative_path,
            )
            continue
        try:
            data = json.loads(read_text(path))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            report.add(
                V_LOCALE_MISSING,
                "Файл локали не является корректным JSON",
                file=relative_path,
                meta={"error": str(exc)},
            )
            continue
        if not isinstance(data, dict):
            report.add(
                V_LOCALE_MISSING,
                "Файл локали должен быть объектом",
                file=relative_path,
            )
            continue
        result.locales[language] = data

    fallback = result.locales.get(FALLBACK_LANGUAGE)
    if fallback is not None:
        fallback_flat = _flatten(fallback)
        for language, data in result.locales.items():
            if language == FALLBACK_LANGUAGE:
                continue
            flat = _flatten(data)
            missing = sorted(set(fallback_flat) - set(flat))
            if missing:
                report.add(
                    V_LOCALE_PARITY,
                    f"В локали «{language}» отсутствуют ключи",
                    file=f"{LOCALES_DIR}/{language}.json",
                    hint="Добавьте недостающие ключи во все заявленные локали.",
                    meta={"missing": missing},
                )
            for key, value in flat.items():
                expected = _placeholders(fallback_flat.get(key))
                actual = _placeholders(value)
                if expected != actual:
                    report.add(
                        V_LOCALE_PARITY,
                        f"Набор плейсхолдеров ключа «{key}» не совпадает с en",
                        file=f"{LOCALES_DIR}/{language}.json",
                        meta={"expected": sorted(expected), "actual": sorted(actual)},
                    )
    result.diagnostics = report.diagnostics
    return result
