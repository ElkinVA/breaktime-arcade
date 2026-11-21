# ruff: noqa: E402, SIM105, T201
"""Securely store the Telegram bot token and owner id outside Git.

Run this yourself in a local terminal; the token is read with getpass and is
never printed, logged, or sent to Claude/Telegram chat.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from devcontrol.config import DEFAULT_CREDS, TOKEN_RE  # noqa: E402
from devcontrol.telegram import TelegramClient, TelegramError  # noqa: E402


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(path)
        path.chmod(0o600)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Store Telegram Dev Control credentials")
    parser.add_argument("--creds", type=Path, default=DEFAULT_CREDS)
    parser.add_argument("--owner-id", type=int, default=None)
    parser.add_argument("--force", action="store_true", help="overwrite existing file")
    parser.add_argument("--verify", action="store_true", help="call getMe before saving")
    parser.add_argument(
        "--proxy",
        default=None,
        help="HTTP/HTTPS proxy for api.telegram.org, e.g. http://127.0.0.1:7890",
    )
    parser.add_argument(
        "--enable-autonomous",
        action="store_true",
        help="explicitly enable autonomous Claude launch (runs as your user)",
    )
    args = parser.parse_args(argv)

    if args.creds.exists() and not args.force:
        print(f"{args.creds} already exists; use --force to replace it", file=sys.stderr)
        return 2

    token = getpass.getpass("Telegram bot token (input hidden): ").strip()
    if not TOKEN_RE.match(token):
        print("Token has an unexpected format; nothing was written", file=sys.stderr)
        return 2

    owner_id = args.owner_id
    if owner_id is None:
        raw = input("Telegram owner user ID (numeric): ").strip()
        try:
            owner_id = int(raw)
        except ValueError:
            print("Owner ID must be numeric; nothing was written", file=sys.stderr)
            return 2
    if owner_id <= 0:
        print("Owner ID must be positive; nothing was written", file=sys.stderr)
        return 2

    if args.verify:
        try:
            me = TelegramClient(token, timeout=15, proxy=args.proxy).get_me()
        except TelegramError as exc:
            if exc.status_code in {401, 403}:
                print(
                    f"Telegram rejected the token (HTTP {exc.status_code}); "
                    "credentials were not saved.",
                    file=sys.stderr,
                )
                return 2
            print(
                f"getMe unavailable ({exc}); credentials will be saved unverified. "
                "Fix network/proxy and re-run --verify later.",
                file=sys.stderr,
            )
        else:
            username = me.get("username") if isinstance(me, dict) else None
            print(f"Token verified for @{username or 'unknown'}")

    proxy_line = f"TELEGRAM_PROXY={args.proxy}\n" if args.proxy else ""
    text = (
        "# BA Dev Control credentials — keep this file 0600 and out of Git.\n"
        f"TELEGRAM_BOT_TOKEN={token}\n"
        f"TELEGRAM_OWNER_ID={owner_id}\n"
        f"DEVCONTROL_ALLOW_AUTONOMOUS={'1' if args.enable_autonomous else '0'}\n"
        f"{proxy_line}"
    )
    _write_private(args.creds, text)
    if args.enable_autonomous:
        print(
            "WARNING: autonomous launch is enabled. Claude runs as your user and "
            "inherits your docker access; use only after reviewing the threat model."
        )
    print(f"Saved {args.creds} (mode 0600). Restart ba-devcontrol to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
