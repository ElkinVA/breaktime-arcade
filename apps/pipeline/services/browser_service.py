"""Secretless HTTP service that runs the browser publish gate.

The service is attached to an internal-only network shared with nginx and the
web container. It has no ``.env`` file, no database/Redis credentials and no
edge/egress network. A compromised Chromium renderer cannot reach the portal's
internal services or read platform secrets.
"""

from __future__ import annotations

import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import BoundedSemaphore
from typing import Any

from apps.pipeline.services.browser_autotest import (
    BrowserAutotestUnavailable,
    run_browser_autotest,
)

_LOGGER = logging.getLogger("browser.autotest")

_MAX_BODY_BYTES = 64 * 1024
_MAX_TIMEOUT_SECONDS = 60
_MIN_TIMEOUT_SECONDS = 5
_REQUIRED_FIELDS = (
    "host_label",
    "runtime_hash",
    "game_id",
    "game_version",
    "portal_origin",
    "games_domain",
)
_SLOTS = BoundedSemaphore(int(os.environ.get("BROWSER_AUTOTEST_CONCURRENCY", "1")))


def _text(payload: dict[str, Any], key: str, limit: int = 255) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value or len(value) > limit:
        raise ValueError(f"{key} must be a non-empty string up to {limit} characters")
    return value


def _validate(payload: dict[str, Any]) -> dict[str, Any]:
    for key in _REQUIRED_FIELDS:
        if key not in payload:
            raise ValueError(f"{key} is required")
    host_label = _text(payload, "host_label", 128)
    runtime_hash = _text(payload, "runtime_hash", 128)
    game_id = _text(payload, "game_id", 128)
    game_version = _text(payload, "game_version", 64)
    portal_origin = _text(payload, "portal_origin", 255)
    games_domain = _text(payload, "games_domain", 255)
    if not all(char in "0123456789abcdef" for char in runtime_hash) or len(runtime_hash) != 64:
        raise ValueError("runtime_hash must be 64 lowercase hexadecimal characters")
    if any(token in host_label for token in ("/", ":", "\\")):
        raise ValueError("host_label must be a bare label")
    if any(token in games_domain for token in ("/", ":", "\\")):
        raise ValueError("games_domain must be a bare domain")
    if not portal_origin.startswith("https://"):
        raise ValueError("portal_origin must use https")
    raw_timeout = payload.get("timeout_seconds", 30)
    if not isinstance(raw_timeout, int) or isinstance(raw_timeout, bool):
        raise ValueError("timeout_seconds must be an integer")
    timeout_seconds = max(_MIN_TIMEOUT_SECONDS, min(_MAX_TIMEOUT_SECONDS, raw_timeout))
    return {
        "host_label": host_label,
        "runtime_hash": runtime_hash,
        "game_id": game_id,
        "game_version": game_version,
        "portal_origin": portal_origin.rstrip("/"),
        "games_domain": games_domain,
        "timeout_seconds": timeout_seconds,
    }


def run_payload(
    payload: dict[str, Any],
    *,
    resolver: str = "",
    insecure_tls: bool = False,
    headless: bool = True,
) -> tuple[int, dict[str, Any]]:
    """Validate one request and return ``(http_status, report)``."""
    try:
        fields = _validate(payload)
    except ValueError as exc:
        return 400, {
            "passed": False,
            "kind": "browser",
            "playwright": False,
            "browser": "chromium",
            "attempted": False,
            "error": str(exc),
            "checks": [],
        }
    if not _SLOTS.acquire(blocking=False):
        return 429, {
            "passed": False,
            "kind": "browser",
            "playwright": False,
            "browser": "chromium",
            "attempted": True,
            "error": "browser autotest is busy",
            "checks": [],
        }
    try:
        try:
            result = run_browser_autotest(
                **fields,
                resolver=resolver,
                headless=headless,
                allow_insecure_tls=insecure_tls,
            )
        except BrowserAutotestUnavailable as exc:
            return 503, {
                "passed": False,
                "kind": "browser",
                "playwright": False,
                "browser": "chromium",
                "attempted": True,
                "error": str(exc)[:500],
                "checks": [],
            }
        return 200, result.report
    finally:
        _SLOTS.release()


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class _Handler(BaseHTTPRequestHandler):
    server_version = "ba-browser-autotest"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        if self.path == "/healthz":
            self._send(200, {"status": "ok"})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        if self.path != "/run":
            self._send(404, {"error": "not found"})
            return
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            self._send(415, {"error": "application/json required"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send(400, {"error": "invalid content length"})
            return
        if length <= 0 or length > _MAX_BODY_BYTES:
            self._send(413, {"error": "invalid body size"})
            return
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError, UnicodeDecodeError:
            self._send(400, {"error": "invalid JSON"})
            return
        if not isinstance(payload, dict):
            self._send(400, {"error": "body must be an object"})
            return
        status, report = run_payload(
            payload,
            resolver=os.environ.get("BROWSER_AUTOTEST_RESOLVER", ""),
            insecure_tls=_env_bool("BROWSER_AUTOTEST_INSECURE_TLS", False),
            headless=_env_bool("BROWSER_AUTOTEST_HEADLESS", True),
        )
        self._send(status, report)

    def log_message(self, format: str, *args: Any) -> None:
        # Keep request logging structured and free of request bodies.
        _LOGGER.info(format, *args)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='{"level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
    )
    host = os.environ.get("BROWSER_AUTOTEST_BIND", "0.0.0.0")  # noqa: S104 - container-only network
    port = int(os.environ.get("BROWSER_AUTOTEST_PORT", "8100"))
    server = ThreadingHTTPServer((host, port), _Handler)
    server.daemon_threads = True
    server.serve_forever()


if __name__ == "__main__":
    main()
