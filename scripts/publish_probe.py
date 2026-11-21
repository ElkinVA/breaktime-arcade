#!/usr/bin/env python3
# ruff: noqa: T201
"""Copy the test-only runtime probe into the gitignored nginx runtime volume."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "games-src" / "probe"
SDK = ROOT / "sdk" / "1.1.0" / "ba-sdk.js"
RUNTIME_HASH = "a" * 64
RUNTIME_ROOT = Path(os.environ.get("BA_RUNTIME_ROOT", ROOT / "var" / "runtime"))
TARGET = RUNTIME_ROOT / "probe" / RUNTIME_HASH


def main() -> None:
    if not (SOURCE / "index.html").is_file():
        raise SystemExit("probe source is missing")
    TARGET.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SOURCE, TARGET, dirs_exist_ok=True)
    (TARGET / "js").mkdir(exist_ok=True)
    shutil.copy2(SDK, TARGET / "js" / "ba-sdk.js")
    portal_origin = os.environ.get("PORTAL_ORIGIN", "https://portal.test:8443").rstrip("/")
    (TARGET / "js" / "config.js").write_text(
        f"window.BA_PORTAL_ORIGIN = {json.dumps(portal_origin)};\n",
        encoding="utf-8",
    )
    print(f"probe published: {TARGET}")


if __name__ == "__main__":
    main()
