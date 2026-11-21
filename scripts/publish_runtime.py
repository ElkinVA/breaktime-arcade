#!/usr/bin/env python3
# ruff: noqa: T201
"""Publish a static game runtime with the official SDK and origin pin.

Usage:
  publish_runtime.py --source games-src/probe --target var/runtime/probe/<hash> \
      --portal-origin https://portal.test:8443

The target is gitignored. The source's index.html receives a
`<meta name="ba-portal-origin">` pin so the SDK can reject an attacker-supplied
`#p=` fragment.
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SDK = ROOT / "sdk" / "1.1.0" / "ba-sdk.js"
META_RE = re.compile(
    r'<meta\s+name=["\']ba-portal-origin["\'][^>]*>',
    re.IGNORECASE,
)


def _origin(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("portal origin must be an absolute http(s) URL")
    return f"{parsed.scheme}://{parsed.netloc}"


def _inject_origin(index: str, origin: str) -> str:
    tag = f'<meta name="ba-portal-origin" content="{html.escape(origin, quote=True)}">'
    if META_RE.search(index):
        return META_RE.sub(tag, index, count=1)
    if "</head>" not in index:
        raise ValueError("runtime index.html has no </head>")
    return index.replace("</head>", f"  {tag}\n</head>", 1)


def publish_runtime(
    *,
    source: Path,
    target: Path,
    portal_origin: str,
    sdk: Path = DEFAULT_SDK,
) -> Path:
    source = source.resolve()
    target = target.resolve()
    if not (source / "index.html").is_file():
        raise ValueError(f"missing runtime index: {source / 'index.html'}")
    if not sdk.is_file():
        raise ValueError(f"missing SDK: {sdk}")
    origin = _origin(portal_origin)
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, dirs_exist_ok=True)
    (target / "js").mkdir(exist_ok=True)
    shutil.copy2(sdk, target / "js" / "ba-sdk.js")
    index_path = target / "index.html"
    index_path.write_text(
        _inject_origin(index_path.read_text(encoding="utf-8"), origin),
        encoding="utf-8",
    )
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--portal-origin", required=True)
    parser.add_argument("--sdk", type=Path, default=DEFAULT_SDK)
    args = parser.parse_args()
    target = publish_runtime(
        source=args.source,
        target=args.target,
        portal_origin=args.portal_origin,
        sdk=args.sdk,
    )
    print(f"runtime published: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
