#!/usr/bin/env python3
# ruff: noqa: T201
"""Copy the test-only runtime probe into the gitignored nginx runtime volume."""

from __future__ import annotations

import os
from pathlib import Path

from publish_runtime import publish_runtime

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "games-src" / "probe"
RUNTIME_HASH = "a" * 64
RUNTIME_ROOT = Path(os.environ.get("BA_RUNTIME_ROOT", ROOT / "var" / "runtime"))
TARGET = RUNTIME_ROOT / "probe" / RUNTIME_HASH


def main() -> None:
    portal_origin = os.environ.get("PORTAL_ORIGIN", "https://portal.test:8443").rstrip("/")
    target = publish_runtime(
        source=SOURCE,
        target=TARGET,
        portal_origin=portal_origin,
    )
    print(f"probe published: {target}")


if __name__ == "__main__":
    main()
