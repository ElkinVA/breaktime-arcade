"""Package and contract checks for the Who's Undercover? Live cartridge."""

from __future__ import annotations

import importlib.util
import json
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Any

from apps.pipeline.services.critical_path import measure_critical_path
from apps.pipeline.validation.budgets import budget_diagnostics
from apps.pipeline.validation.catalog import validate_catalog
from apps.pipeline.validation.locales import validate_locales
from apps.pipeline.validation.manifest import validate_manifest
from apps.pipeline.validation.security_scan import scan_root
from apps.pipeline.validation.structure import preflight_zip
from apps.pipeline.validation.text import has_bom, has_crlf, iter_text_files

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "games-src" / "whos_undercover_live"
LANGUAGES = ["en", "ru"]


def _load_pack() -> ModuleType:
    path = PACKAGE / "pack.py"
    spec = importlib.util.spec_from_file_location("whos_undercover_live_pack", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest() -> dict[str, Any]:
    result = validate_manifest(PACKAGE)
    assert result.ok, [item.as_dict() for item in result.diagnostics]
    assert result.manifest is not None
    return result.manifest


def test_manifest_declares_the_live_room_sdk() -> None:
    manifest = _manifest()
    assert manifest["id"] == "whos_undercover_live"
    assert manifest["version"] == "1.0.0"
    assert manifest["sdkVersion"] == "^1.2"
    assert manifest["supportedLanguages"] == LANGUAGES
    assert manifest["defaultLanguage"] == "en"
    assert manifest["capabilities"] == {
        "wasm": False,
        "pointerLock": False,
        "storage": "sdk",
        "externalOrigins": [],
    }
    assert manifest["leaderboard"]["enabled"] is False


def test_live_entry_and_critical_path_budget() -> None:
    manifest = _manifest()
    index = (PACKAGE / "index.html").read_text(encoding="utf-8")
    assert "js/ba-sdk.js" in index
    assert "js/live.js" in index
    assert "css/live.css" in index

    critical = manifest["assets"]["critical"]
    assert "js/live.js" in critical
    assert "css/live.css" in critical
    measured = measure_critical_path(PACKAGE, critical, manifest["defaultLanguage"])
    assert measured.missing == []
    assert manifest["assets"]["criticalPathBytes"] == measured.measured_bytes
    diagnostics = budget_diagnostics(
        measured,
        manifest["assets"]["criticalPathBytes"],
        warn_bytes=2_097_152,
        max_bytes=4_194_304,
    )
    assert diagnostics == []


def test_package_structure_encoding_and_zip_preflight(tmp_path: Path) -> None:
    pack = _load_pack()
    files = pack.iter_package_files()
    pack.validate_sources(files)
    names = {path.relative_to(PACKAGE).as_posix() for path in files}
    assert "js/live.js" in names
    assert "css/live.css" in names
    assert "locales/en.json" in names
    assert "locales/ru.json" in names
    assert "pack.py" not in names
    for path in iter_text_files(PACKAGE):
        if path.name == "pack.py":
            continue
        assert not has_bom(path), path
        assert not has_crlf(path), path

    first = pack.build_zip(tmp_path / "first.zip")
    second = pack.build_zip(tmp_path / "second.zip")
    assert first.read_bytes() == second.read_bytes()
    assert pack.verify_zip(first) == []
    report = preflight_zip(first.read_bytes())
    assert report.ok, [item.as_dict() for item in report.diagnostics]
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == sorted(archive.namelist())
        assert "js/live.js" in archive.namelist()
        assert all(not name.endswith("/") for name in archive.namelist())


def test_security_scan_and_live_client_uses_the_sdk_room_transport() -> None:
    result = scan_root(PACKAGE)
    assert not result.diagnostics, [item.as_dict() for item in result.diagnostics]
    live = (PACKAGE / "js" / "live.js").read_text(encoding="utf-8")
    for forbidden in (
        "localStorage",
        "sessionStorage",
        "indexedDB",
        "document.cookie",
        "postMessage",
        "eval(",
        "new Function(",
        "navigator.clipboard",
        "http://",
        "https://",
        "innerHTML",
    ):
        assert forbidden not in live, forbidden
    for transport in ("room.create", "room.join", "room.state", "room.command", "room.leave"):
        assert transport in live, transport
    assert "textContent" in live


def test_catalog_and_locales_cover_both_languages() -> None:
    catalog = validate_catalog(PACKAGE, LANGUAGES, 2)
    assert not catalog.diagnostics, [item.as_dict() for item in catalog.diagnostics]
    assert set(catalog.entries) == set(LANGUAGES)
    assert catalog.entries["en"].data["name"] == "Who's Undercover? Live"
    assert "Live" in catalog.entries["ru"].data["name"]

    locales = validate_locales(PACKAGE, LANGUAGES)
    assert not locales.diagnostics, [item.as_dict() for item in locales.diagnostics]
    assert set(locales.locales) == set(LANGUAGES)

    manifests = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
    assert manifests["supportedLanguages"] == LANGUAGES
