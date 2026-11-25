"""Headless browser smoke test for an imported runtime (§2.14.8, §4.3).

The static autotest proves bundle invariants only. This runner loads the
runtime in Chromium from the game origin, speaks the BA SDK hello/context
handshake through a minimal portal-side host, and records page errors. It is
intentionally a smoke test, not a gameplay/replay test: a game that cannot
start its SDK handshake must never reach production publish.
"""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4


class BrowserAutotestUnavailable(RuntimeError):
    """Playwright or its browser binary is not available."""


@dataclass(slots=True)
class BrowserAutotestResult:
    passed: bool
    report: dict[str, Any]
    checks: list[dict[str, Any]] = field(default_factory=list)


def runtime_origin(host_label: str, *, portal_origin: str, games_domain: str) -> str:
    parsed = urlparse(portal_origin)
    port = parsed.port
    suffix = "" if port in (None, 443) else f":{port}"
    host = host_label if host_label.endswith(f".{games_domain}") else f"{host_label}.{games_domain}"
    return f"https://{host}{suffix}"


def runtime_url(
    host_label: str, runtime_hash: str, *, portal_origin: str, games_domain: str
) -> str:
    base = runtime_origin(host_label, portal_origin=portal_origin, games_domain=games_domain)
    return f"{base}/v/{runtime_hash}/index.html"


def _context(*, game_id: str, game_version: str) -> dict[str, Any]:
    return {
        "sessionId": str(uuid4()),
        "gameId": game_id,
        "gameVersion": game_version,
        "mode": "autotest",
        "nickname": None,
        "language": "en",
        "fallbackLanguage": "en",
        "strings": {},
        "score": {},
        "limits": {},
        "trustLevel": "client_reported",
        "seed": uuid4().hex,
    }


def _resolver_rules(resolver: str, *, portal_origin: str, games_domain: str) -> str | None:
    if not resolver:
        return None
    try:
        ip = socket.gethostbyname(resolver)
    except OSError:
        return None
    portal = urlparse(portal_origin).hostname
    if not portal:
        return None
    return f"MAP {portal} {ip}, MAP *.{games_domain} {ip}"


def run_browser_autotest(
    *,
    host_label: str,
    runtime_hash: str,
    game_id: str,
    game_version: str,
    portal_origin: str,
    games_domain: str,
    timeout_seconds: int = 30,
    resolver: str = "",
    headless: bool = True,
) -> BrowserAutotestResult:
    """Load a runtime and verify the SDK handshake; never raises for a game error."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:  # pragma: no cover - deployment guard
        raise BrowserAutotestUnavailable("Playwright is not installed") from None

    checks: list[dict[str, Any]] = []
    page_errors: list[str] = []
    started = time.monotonic()
    url = runtime_url(
        host_label,
        runtime_hash,
        portal_origin=portal_origin,
        games_domain=games_domain,
    )
    context_payload = _context(game_id=game_id, game_version=game_version)
    request_id = str(uuid4())
    rules = _resolver_rules(resolver, portal_origin=portal_origin, games_domain=games_domain)
    args = [f"--host-resolver-rules={rules}"] if rules else []

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless, args=args)
            try:
                page = browser.new_page(ignore_https_errors=True)
                page.on("pageerror", lambda exc: page_errors.append(str(exc)))
                response = page.goto(
                    portal_origin.rstrip("/") + "/en/",
                    wait_until="domcontentloaded",
                    timeout=timeout_seconds * 1000,
                )
                checks.append(
                    {
                        "name": "portal_page",
                        "passed": bool(response and response.ok),
                        "detail": f"status={getattr(response, 'status', None)}",
                    }
                )
                page.evaluate(
                    """([runtime, sessionId, payload, requestId]) => {
                        document.body.innerHTML = "";
                        const iframe = document.createElement("iframe");
                        iframe.id = "autotest-frame";
                        iframe.setAttribute("sandbox", "allow-scripts allow-same-origin");
                        iframe.src = runtime + "#p=" + encodeURIComponent(location.origin)
                            + "&s=" + encodeURIComponent(sessionId);
                        iframe.style.width = "1024px";
                        iframe.style.height = "768px";
                        document.body.appendChild(iframe);
                        window.__baAutotest = { hello: false, errors: [] };
                        window.addEventListener("message", (event) => {
                            if (event.source !== iframe.contentWindow) return;
                            const data = event.data || {};
                            if (data.type === "ba:hello") {
                                window.__baAutotest.hello = true;
                                iframe.contentWindow.postMessage({
                                    source: "ba-host",
                                    protocol: 1,
                                    type: "ba:context",
                                    requestId,
                                    sessionId: payload.sessionId,
                                    payload,
                                }, event.origin);
                            }
                        });
                    }""",
                    [url, context_payload["sessionId"], context_payload, request_id],
                )
                hello = False
                try:
                    page.wait_for_function(
                        "() => window.__baAutotest && window.__baAutotest.hello === true",
                        timeout=timeout_seconds * 1000,
                    )
                    hello = True
                except Exception:  # noqa: BLE001 - reported as a check
                    hello = False
                checks.append(
                    {
                        "name": "sdk_handshake",
                        "passed": hello,
                        "detail": "ba:hello received" if hello else "timeout waiting for ba:hello",
                    }
                )
                checks.append(
                    {
                        "name": "page_errors",
                        "passed": not page_errors,
                        "detail": f"{len(page_errors)} page error(s)",
                    }
                )
                return BrowserAutotestResult(
                    passed=all(item["passed"] for item in checks),
                    report={
                        "passed": all(item["passed"] for item in checks),
                        "kind": "browser",
                        "playwright": True,
                        "browser": "chromium",
                        "generated_at": datetime.now(UTC).isoformat(),
                        "runtime_hash": runtime_hash,
                        "runtime_url": url,
                        "duration_ms": int((time.monotonic() - started) * 1000),
                        "checks": checks,
                        "errors": page_errors[:10],
                    },
                    checks=checks,
                )
            finally:
                browser.close()
    except BrowserAutotestUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 - a launch failure is a failed check
        return BrowserAutotestResult(
            passed=False,
            report={
                "passed": False,
                "kind": "browser",
                "playwright": False,
                "generated_at": datetime.now(UTC).isoformat(),
                "runtime_hash": runtime_hash,
                "runtime_url": url,
                "error": f"{type(exc).__name__}: {exc}"[:500],
                "checks": checks,
            },
            checks=checks,
        )


def merge_autotest_reports(static: dict[str, Any], browser: dict[str, Any]) -> dict[str, Any]:
    """Combine static and browser checks; browser provenance stays visible."""
    raw_static = static.get("checks")
    raw_browser = browser.get("checks")
    static_checks: list[Any] = raw_static if isinstance(raw_static, list) else []
    browser_checks: list[Any] = raw_browser if isinstance(raw_browser, list) else []
    passed = static.get("passed") is True and browser.get("passed") is True
    return {
        "passed": passed,
        "kind": "browser" if browser.get("playwright") else "static",
        "playwright": browser.get("playwright") is True,
        "generated_at": browser.get("generated_at", datetime.now(UTC).isoformat()),
        "runtime_hash": browser.get("runtime_hash", ""),
        "checks": [*static_checks, *browser_checks],
        "static": static,
        "browser": browser,
        "errors": browser.get("errors", []),
    }
