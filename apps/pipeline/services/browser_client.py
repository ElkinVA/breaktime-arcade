"""Client for the isolated browser-autotest service.

Untrusted game JavaScript must never run inside the Django web container: that
process holds database, mail and signing secrets and can reach internal
services. The importer therefore asks a dedicated secretless container over an
internal-only network to load the runtime and return a browser report.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any
from uuid import uuid4

from django.conf import settings

from apps.pipeline.services.browser_autotest import BrowserAutotestResult

_MAX_RESPONSE_BYTES = 1_000_000


def _failed_report(error: str) -> dict[str, Any]:
    return {
        "passed": False,
        "kind": "browser",
        "playwright": False,
        "browser": "chromium",
        "attempted": True,
        "error": error[:500],
        "checks": [],
    }


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
    """Run the remote browser check; transport failures are failed reports.

    ``resolver`` and ``headless`` stay in the signature for the importer's
    existing call shape; the service owns those execution details.
    """
    del resolver, headless
    url = getattr(settings, "BROWSER_AUTOTEST_URL", "")
    if not url:
        report = _failed_report("browser autotest service URL is not configured")
        return BrowserAutotestResult(passed=False, report=report, checks=[])

    payload = {
        "host_label": host_label,
        "runtime_hash": runtime_hash,
        "game_id": game_id,
        "game_version": game_version,
        "portal_origin": portal_origin,
        "games_domain": games_domain,
        "timeout_seconds": timeout_seconds,
        "request_id": str(uuid4()),
    }
    request = urllib.request.Request(  # noqa: S310 - URL comes from deployment settings
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(  # noqa: S310 - URL comes from deployment settings
            request, timeout=timeout_seconds + 10
        ) as response:
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        report = _failed_report(f"{type(exc).__name__}: {exc}")
        return BrowserAutotestResult(passed=False, report=report, checks=[])

    if len(raw) > _MAX_RESPONSE_BYTES:
        report = _failed_report("browser autotest response is too large")
        return BrowserAutotestResult(passed=False, report=report, checks=[])
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        report = _failed_report(f"{type(exc).__name__}: invalid JSON response")
        return BrowserAutotestResult(passed=False, report=report, checks=[])
    if not isinstance(data, dict):
        report = _failed_report("browser autotest response is not an object")
        return BrowserAutotestResult(passed=False, report=report, checks=[])
    checks = data.get("checks")
    return BrowserAutotestResult(
        passed=data.get("passed") is True,
        report=data,
        checks=checks if isinstance(checks, list) else [],
    )
