"""Content and package checks for the first real Neon Snake cartridge.

These are Python-only checks. Browser/iframe execution and a Node runtime are
deliberately out of scope here and are performed by the portal acceptance run
after merge.
"""

from __future__ import annotations

import importlib.util
import json
import re
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Any

from apps.core.contracts import validate_eventlog_semantics
from apps.pipeline.services.critical_path import measure_critical_path
from apps.pipeline.validation.assets import (
    COVER_MAX_BYTES,
    IMAGE_HEIGHT,
    IMAGE_WIDTH,
    SCREENSHOT_MAX_BYTES,
    validate_assets,
)
from apps.pipeline.validation.catalog import validate_catalog
from apps.pipeline.validation.locales import _flatten, validate_locales
from apps.pipeline.validation.manifest import validate_manifest
from apps.pipeline.validation.security_scan import scan_root
from apps.pipeline.validation.structure import preflight_zip
from apps.pipeline.validation.text import has_bom, has_crlf, iter_text_files

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "games-src" / "neon_snake"
OFFICIAL_SDK = ROOT / "sdk" / "1.1.0" / "ba-sdk.js"
LANGUAGES = ["en", "de", "nl", "ru", "fr", "es"]
REQUIRED_KEYS = {
    "game_title",
    "start",
    "pause",
    "resume",
    "restart",
    "game_over",
    "your_score",
    "best_score",
    "new_record",
    "play_again",
    "exit",
    "loading",
    "error_sdk",
    "error_network",
    "result_saving",
    "result_rejected",
    "result_retry",
    "session_expired",
    "guest_notice",
    "register_cta",
    "controls_hint",
    "orientation_hint",
    "sound_on",
    "sound_off",
    "rank",
    "top_scores",
}


def _json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _load_pack() -> ModuleType:
    path = PACKAGE / "pack.py"
    spec = importlib.util.spec_from_file_location("neon_snake_pack", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_matches_contract_and_is_fully_declared() -> None:
    result = validate_manifest(PACKAGE)
    assert result.ok, [item.as_dict() for item in result.diagnostics]
    manifest = result.manifest
    assert manifest is not None
    assert manifest["id"] == "neon_snake"
    assert manifest["version"] == "1.0.0"
    assert manifest["sdkVersion"] == "^1.0"
    assert manifest["protocol"] == 1
    assert manifest["defaultLanguage"] == "en"
    assert manifest["supportedLanguages"] == LANGUAGES
    assert manifest["genre"] == "arcade"
    assert manifest["capabilities"] == {
        "wasm": False,
        "pointerLock": False,
        "storage": "sdk",
        "externalOrigins": [],
    }
    score = manifest["score"]
    assert score["maxValue"] == 100000
    assert score["schemaVersion"] == 1
    assert manifest["limits"]["minPlaytimeSeconds"] >= 5
    assert manifest["limits"]["maxSessionSeconds"] <= 7200
    assert manifest["leaderboard"]["claimedVerification"] == "heuristic_validated"
    event_kinds = manifest["verification"]["eventKinds"]
    assert event_kinds == ["start", "eat", "turn", "level", "collide", "end"]
    assert len(event_kinds) <= 32


def test_sdk_is_the_official_build_byte_for_byte() -> None:
    packaged = (PACKAGE / "js" / "ba-sdk.js").read_bytes()
    official = OFFICIAL_SDK.read_bytes()
    assert packaged == official
    assert b"BreaktimeArcade" in packaged
    assert b"submitResult" in packaged
    assert b"newSession" in packaged


def test_package_structure_encoding_and_zip_preflight(tmp_path: Path) -> None:
    pack = _load_pack()
    files = pack.iter_package_files()
    pack.validate_sources(files)
    names = {path.relative_to(PACKAGE).as_posix() for path in files}
    required = {
        "manifest.json",
        "index.html",
        "css/style.css",
        "js/ba-sdk.js",
        "js/rng.js",
        "js/game.js",
        "locales/en.json",
        "locales/de.json",
        "locales/nl.json",
        "locales/ru.json",
        "locales/fr.json",
        "locales/es.json",
        "catalog/en.json",
        "catalog/de.json",
        "catalog/nl.json",
        "catalog/ru.json",
        "catalog/fr.json",
        "catalog/es.json",
        "assets/cover.webp",
        "assets/screen-1.webp",
        "assets/screen-2.webp",
        "README.md",
        "SELF-CHECK.md",
    }
    assert required <= names
    assert "pack.py" not in names
    assert "dist/neon_snake-1.0.0.zip" not in names
    for path in iter_text_files(PACKAGE):
        if path.name == "pack.py" or path.parts[-2] == "tools":
            continue
        assert not has_bom(path), path
        assert not has_crlf(path), path
    first = pack.build_zip(tmp_path / "first.zip")
    second = pack.build_zip(tmp_path / "second.zip")
    assert first.read_bytes() == second.read_bytes()
    assert first.stat().st_size <= 8 * 1024 * 1024
    assert sum(path.stat().st_size for path in files) <= 25 * 1024 * 1024
    assert pack.verify_zip(first) == []
    report = preflight_zip(first.read_bytes())
    assert report.ok, [item.as_dict() for item in report.diagnostics]
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == sorted(archive.namelist())
        assert "pack.py" not in archive.namelist()
        assert all(not name.endswith("/") for name in archive.namelist())


def test_security_scan_and_forbidden_runtime_apis() -> None:
    result = scan_root(PACKAGE)
    assert not result.diagnostics, [item.as_dict() for item in result.diagnostics]
    rng = (PACKAGE / "js" / "rng.js").read_text(encoding="utf-8")
    game = (PACKAGE / "js" / "game.js").read_text(encoding="utf-8")
    for source in (rng, game):
        assert "Math.random" not in source
        assert "localStorage" not in source
        assert "sessionStorage" not in source
        assert "indexedDB" not in source
        assert "document.cookie" not in source
        assert "postMessage" not in source
        assert "eval(" not in source
        assert "new Function(" not in source
        assert "parent.location" not in source
        assert "parent.document" not in source
        assert "window.top" not in source
    assert "fire-and-forget" not in game
    assert "https://" not in game
    assert "http://" not in game


def test_locales_have_parity_and_required_ui_strings() -> None:
    result = validate_locales(PACKAGE, LANGUAGES)
    assert not result.diagnostics, [item.as_dict() for item in result.diagnostics]
    assert set(result.locales) == set(LANGUAGES)
    english = _flatten(result.locales["en"])
    assert set(english) >= REQUIRED_KEYS
    for language, data in result.locales.items():
        flat = _flatten(data)
        assert set(flat) == set(english), language
        assert all(isinstance(value, str) and value.strip() for value in flat.values()), language
    assert "plural," in english["lives"]
    assert "plural," in _flatten(result.locales["ru"])["lives"]


def test_catalog_has_all_languages_and_screenshot_alts() -> None:
    result = validate_catalog(PACKAGE, LANGUAGES, 2)
    assert not result.diagnostics, [item.as_dict() for item in result.diagnostics]
    assert set(result.entries) == set(LANGUAGES)
    for language, entry in result.entries.items():
        data = entry.data
        assert len(data["description"]) >= 300, language
        assert len(data["shortDescription"]) <= 120
        assert len(data["screenshotAlts"]) == 2
        assert data["name"] == "Neon Snake"
        assert data["seoTitle"].strip()
        assert data["seoDescription"].strip()
        assert data["coverAlt"].strip()


def test_assets_match_dimensions_and_budgets() -> None:
    manifest = _json(PACKAGE / "manifest.json")
    result = validate_assets(PACKAGE, manifest)
    assert not result.diagnostics, [item.as_dict() for item in result.diagnostics]
    assert result.cover is not None
    assert result.cover.width == IMAGE_WIDTH
    assert result.cover.height == IMAGE_HEIGHT
    assert result.cover.bytes <= COVER_MAX_BYTES
    assert len(result.screenshots) == 2
    for shot in result.screenshots:
        assert shot.width == IMAGE_WIDTH
        assert shot.height == IMAGE_HEIGHT
        assert shot.bytes <= SCREENSHOT_MAX_BYTES


def test_critical_path_budget_and_declared_size() -> None:
    manifest = _json(PACKAGE / "manifest.json")
    assets = manifest["assets"]
    critical = assets["critical"]
    assert isinstance(critical, list)
    for required in (
        "index.html",
        "css/style.css",
        "js/ba-sdk.js",
        "js/rng.js",
        "js/game.js",
        "locales/en.json",
    ):
        assert required in critical
    measured = measure_critical_path(PACKAGE, critical, "en")
    assert measured.missing == []
    assert measured.measured_bytes <= 2 * 1024 * 1024
    declared = assets["criticalPathBytes"]
    assert isinstance(declared, int)
    assert abs(measured.measured_bytes - declared) / max(declared, 1) <= 0.10, (
        measured.measured_bytes,
        declared,
    )


def test_event_log_bounds_and_seed_contract() -> None:
    manifest = _json(PACKAGE / "manifest.json")
    kinds = manifest["verification"]["eventKinds"]
    game = (PACKAGE / "js" / "game.js").read_text(encoding="utf-8")
    assert re.search(r"const MAX_EVENTS = 20000;", game)
    assert re.search(r"const MAX_EVENT_BYTES = 1500000;", game)
    assert "state.eventLog.events.length >= MAX_EVENTS" in game
    assert "state.eventBytes >= MAX_EVENT_BYTES" in game
    events = [{"t": index * 10, "k": kind, "d": {"i": index}} for index, kind in enumerate(kinds)]
    sample = {"v": 1, "seed": "deterministic-seed", "events": events}
    errors = validate_eventlog_semantics(sample, kinds, duration_ms=2000)
    assert errors == []
    assert "seed: state.seed" in game
    assert "eventLog: state.eventLog" in game


def test_seed_determinism_is_wired_to_the_platform_seed() -> None:
    game = (PACKAGE / "js" / "game.js").read_text(encoding="utf-8")
    rng = (PACKAGE / "js" / "rng.js").read_text(encoding="utf-8")
    assert "mulberry32" in rng
    assert "Math.imul" in rng
    assert "hashSeed" in rng
    assert "NeonRng.create(state.seed)" in game
    assert "state.seed = typeof context.seed" in game
    assert "state.seed = context.seed" in game
    assert "state.eventLog = { v: 1, seed: state.seed, events: [] }" in game
    assert (
        'const AVAILABLE_LANGUAGES = Object.freeze(["en", "de", "nl", "ru", "fr", "es"]);' in game
    )
    assert "AVAILABLE_LANGUAGES.indexOf(code) === -1" in game
    assert "freeze" in rng
    assert "Math.random" not in game and "Math.random" not in rng


def test_paused_time_is_excluded_and_autotest_budget_is_declared() -> None:
    game = (PACKAGE / "js" / "game.js").read_text(encoding="utf-8")
    assert re.search(r"const AUTOTEST_STEP_MS = 40;", game)
    assert re.search(r"const AUTOTEST_LIMIT_TICKS = 400;", game)
    assert 40 * 400 <= 25_000
    assert "state.clockMs += state.stepMs" in game
    assert "state.paused" in game
    assert "autotest:finish" in game
    assert "autotest_limit" in game


def test_controls_pause_resume_guest_and_autotest_paths_are_wired() -> None:
    game = (PACKAGE / "js" / "game.js").read_text(encoding="utf-8")
    for fragment in (
        'document.addEventListener("keydown", onKeyDown)',
        'dom.canvas.addEventListener("pointerdown", onCanvasPointerDown)',
        'dom["touch-controls"].querySelectorAll("[data-direction]")',
        'state.ba.on("pause"',
        'state.ba.on("resume"',
        'state.ba.on("visibility"',
        '"autotest:finish"',
        "state.ba.newSession()",
        "state.ba.exit()",
        'result.status === "guest"',
        'state.mode === "preview"',
        'setHidden(dom["new-record"], result.isRecord !== true)',
        'setNode(dom["retry-submit-button"], "result_retry")',
        "state.retryAllowed",
        "state.autoWatchdog",
        "if (state.snake.length === 0)",
    ):
        assert fragment in game
    assert "E_GUEST_FORBIDDEN" in game
    assert 'code === "E_GUEST_FORBIDDEN"' in game
    assert "result_retry" in _json(PACKAGE / "locales" / "en.json")


def test_manifest_has_no_unknown_language_or_locale_gaps() -> None:
    manifest = _json(PACKAGE / "manifest.json")
    languages = manifest["supportedLanguages"]
    assert isinstance(languages, list)
    for language in languages:
        assert isinstance(language, str)
        assert (PACKAGE / "locales" / f"{language}.json").is_file()
        assert (PACKAGE / "catalog" / f"{language}.json").is_file()
    assert len(languages) == len(set(languages))
