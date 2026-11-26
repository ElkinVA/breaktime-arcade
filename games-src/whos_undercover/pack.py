#!/usr/bin/env python3
# ruff: noqa: T201
"""Build a reproducible Who's Undercover? cartridge ZIP (stdlib only).

The same source tree always produces byte-identical archives: entries are
sorted, timestamps are fixed, permissions are normalized and no host-specific
metadata is written. The ZIP is validated for the package structure from
BA-GAME-2.2 §3 before it is returned.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST_DIR = ROOT / "dist"
EXCLUDED_NAMES = {
    "pack.py",
    ".gitkeep",
    ".DS_Store",
    "__pycache__",
    ".pytest_cache",
}
EXCLUDED_PARTS = {"__pycache__", ".git", "node_modules", "dist", "tools"}
ALLOWED_EXTENSIONS = {
    ".html",
    ".css",
    ".js",
    ".mjs",
    ".json",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".avif",
    ".gif",
    ".svg",
    ".woff2",
    ".mp3",
    ".ogg",
    ".wav",
    ".wasm",
    ".txt",
    ".md",
}
TEXT_EXTENSIONS = {".html", ".css", ".js", ".mjs", ".json", ".svg", ".txt", ".md"}
REQUIRED_FILES = {
    "index.html",
    "manifest.json",
    "README.md",
    "SELF-CHECK.md",
    "css/style.css",
    "js/ba-sdk.js",
    "js/core.js",
    "js/rng.js",
    "js/game.js",
    "locales/en.json",
    "catalog/en.json",
    "assets/cover.webp",
    "assets/screen-1.webp",
    "assets/screen-2.webp",
}
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,38}[a-z0-9]$")
FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)


class PackageError(RuntimeError):
    """Raised when the source tree cannot form a valid cartridge."""


def read_manifest() -> dict[str, object]:
    path = ROOT / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise PackageError("manifest.json must be a JSON object")
    package_id = manifest.get("id")
    version = manifest.get("version")
    if not isinstance(package_id, str) or not ID_PATTERN.match(package_id):
        raise PackageError("manifest.id does not match the BA-GAME-2.2 pattern")
    if not isinstance(version, str) or not re.match(
        r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$",
        version,
    ):
        raise PackageError("manifest.version must be semver")
    return manifest


def iter_package_files() -> list[Path]:
    files: list[Path] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.name in EXCLUDED_NAMES or path.suffix.lower() == ".zip":
            continue
        if path.name.endswith(".tmp"):
            continue
        if path.suffix.lower() not in ALLOWED_EXTENSIONS:
            raise PackageError(f"unsupported package extension: {relative.as_posix()}")
        files.append(path)
    return files


def validate_sources(files: list[Path]) -> None:
    names = {path.relative_to(ROOT).as_posix() for path in files}
    missing = sorted(REQUIRED_FILES - names)
    if missing:
        raise PackageError("required package files are missing: " + ", ".join(missing))
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        data = path.read_bytes()
        if not data:
            raise PackageError(f"empty package file: {relative}")
        if path.suffix.lower() in TEXT_EXTENSIONS:
            if data.startswith(b"\xef\xbb\xbf"):
                raise PackageError(f"UTF-8 BOM is not allowed: {relative}")
            if b"\r\n" in data:
                raise PackageError(f"CRLF is not allowed: {relative}")
            try:
                data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise PackageError(f"invalid UTF-8: {relative}") from exc
        if path.suffix.lower() == ".json":
            try:
                json.loads(data.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise PackageError(f"invalid JSON: {relative}") from exc


def zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(filename=name, date_time=FIXED_DATE_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def build_zip(output: Path | None = None) -> Path:
    manifest = read_manifest()
    files = iter_package_files()
    validate_sources(files)
    if output is None:
        output = DIST_DIR / f"{manifest['id']}-{manifest['version']}.zip"
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + ".tmp")
    try:
        with zipfile.ZipFile(
            temp, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=False
        ) as archive:
            for path in files:
                name = path.relative_to(ROOT).as_posix()
                archive.writestr(zip_info(name), path.read_bytes(), compresslevel=9)
        temp.replace(output)
    finally:
        if temp.exists():
            temp.unlink()
    return output


def verify_zip(path: Path) -> list[str]:
    problems: list[str] = []
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if names != sorted(names):
            problems.append("entries are not sorted")
        if len(names) != len(set(names)):
            problems.append("duplicate entries")
        required = REQUIRED_FILES
        for name in required:
            if name not in names:
                problems.append(f"missing entry: {name}")
        for info in archive.infolist():
            if info.filename.endswith("/"):
                problems.append(f"unexpected directory entry: {info.filename}")
            if info.date_time != FIXED_DATE_TIME:
                problems.append(f"non-reproducible timestamp: {info.filename}")
            if info.external_attr != 0o100644 << 16:
                problems.append(f"non-normalized permissions: {info.filename}")
        bad = archive.testzip()
        if bad is not None:
            problems.append(f"corrupt entry: {bad}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Archer cartridge ZIP")
    parser.add_argument("--output", type=Path, help="output ZIP path")
    args = parser.parse_args(argv)
    try:
        output = build_zip(args.output)
    except (OSError, PackageError) as exc:
        print(f"pack: {exc}", file=sys.stderr)
        return 1
    problems = verify_zip(output)
    if problems:
        for problem in problems:
            print(f"pack: {problem}", file=sys.stderr)
        return 1
    print(str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
