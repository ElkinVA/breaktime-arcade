"""Browser autotest report merging, URL construction and service contract."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from apps.pipeline.services import browser_client, browser_service
from apps.pipeline.services.browser_autotest import (
    _resolver_rules,
    merge_autotest_reports,
    runtime_url,
)

HASH = "a" * 64
PAYLOAD = {
    "host_label": "test-game",
    "runtime_hash": HASH,
    "game_id": "test-game",
    "game_version": "1.0.0",
    "portal_origin": "https://portal.test:8443",
    "games_domain": "games.test",
    "timeout_seconds": 15,
}


def test_runtime_url_uses_the_game_origin() -> None:
    assert (
        runtime_url(
            "test-game",
            "a" * 64,
            portal_origin="https://portal.test:8443",
            games_domain="games.test",
        )
        == f"https://test-game.games.test:8443/v/{'a' * 64}/index.html"
    )


def test_merge_requires_both_static_and_browser_checks() -> None:
    static = {
        "passed": True,
        "kind": "static",
        "checks": [{"name": "entry", "passed": True}],
    }
    browser = {
        "passed": True,
        "playwright": True,
        "kind": "browser",
        "runtime_hash": "b" * 64,
        "checks": [{"name": "sdk_handshake", "passed": True}],
    }

    merged = merge_autotest_reports(static, browser)

    assert merged["passed"] is True
    assert merged["playwright"] is True
    assert merged["kind"] == "browser"
    assert [item["name"] for item in merged["checks"]] == ["entry", "sdk_handshake"]


def test_merge_fails_without_browser_proof() -> None:
    static = {"passed": True, "kind": "static", "checks": []}
    unavailable = {"passed": False, "playwright": False, "checks": []}

    merged = merge_autotest_reports(static, unavailable)

    assert merged["passed"] is False
    assert merged["playwright"] is False
    assert merged["kind"] == "static"


def test_merge_keeps_attempted_browser_failure_visible() -> None:
    static = {"passed": True, "kind": "static", "checks": []}
    attempted = {
        "passed": False,
        "playwright": False,
        "attempted": True,
        "kind": "browser",
        "error": "service down",
        "checks": [],
    }

    merged = merge_autotest_reports(static, attempted)

    assert merged["passed"] is False
    assert merged["kind"] == "browser"
    assert merged["browser"]["error"] == "service down"


def test_resolver_rules_map_portal_and_game_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("socket.gethostbyname", lambda host: "127.0.0.1")

    rules = _resolver_rules(
        "nginx",
        portal_origin="https://portal.test:8443",
        games_domain="games.test",
    )

    assert rules == "MAP portal.test 127.0.0.1, MAP *.games.test 127.0.0.1"


def test_service_rejects_unsafe_payload_before_running() -> None:
    payload = dict(PAYLOAD, runtime_hash="not-a-hash")

    status, report = browser_service.run_payload(payload)

    assert status == 400
    assert report["passed"] is False
    assert report["attempted"] is False


def test_service_runs_the_browser_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_runner(**kwargs: Any) -> SimpleNamespace:
        seen.update(kwargs)
        return SimpleNamespace(
            passed=True,
            report={"passed": True, "kind": "browser", "playwright": True, "checks": []},
        )

    monkeypatch.setattr(browser_service, "run_browser_autotest", fake_runner)

    status, report = browser_service.run_payload(
        dict(PAYLOAD), resolver="nginx", insecure_tls=True, headless=True
    )

    assert status == 200
    assert report["passed"] is True
    assert seen["host_label"] == "test-game"
    assert seen["allow_insecure_tls"] is True
    assert seen["timeout_seconds"] == 15


def test_service_clamps_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_runner(**kwargs: Any) -> SimpleNamespace:
        seen.update(kwargs)
        return SimpleNamespace(
            passed=True,
            report={"passed": True, "kind": "browser", "playwright": True, "checks": []},
        )

    monkeypatch.setattr(browser_service, "run_browser_autotest", fake_runner)

    status, _ = browser_service.run_payload(dict(PAYLOAD, timeout_seconds=9999))
    assert status == 200
    assert seen["timeout_seconds"] == 60

    status, report = browser_service.run_payload(dict(PAYLOAD, timeout_seconds="30"))
    assert status == 400
    assert report["attempted"] is False


def test_client_fails_closed_without_service_url(settings: Any) -> None:
    settings.BROWSER_AUTOTEST_URL = ""

    result = browser_client.run_browser_autotest(
        host_label="test-game",
        runtime_hash=HASH,
        game_id="test-game",
        game_version="1.0.0",
        portal_origin="https://portal.test:8443",
        games_domain="games.test",
    )

    assert result.passed is False
    assert result.report["playwright"] is False
    assert "not configured" in result.report["error"]


def test_client_parses_service_report(monkeypatch: pytest.MonkeyPatch, settings: Any) -> None:
    settings.BROWSER_AUTOTEST_URL = "http://browser-autotest:8100/run"
    body = {
        "passed": True,
        "kind": "browser",
        "playwright": True,
        "checks": [{"name": "sdk_handshake", "passed": True}],
    }

    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, limit: int) -> bytes:
            del limit
            return json.dumps(body).encode()

    seen: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: int) -> Response:
        seen["url"] = request.full_url
        seen["payload"] = json.loads(request.data)
        seen["timeout"] = timeout
        return Response()

    monkeypatch.setattr(browser_client.urllib.request, "urlopen", fake_urlopen)

    result = browser_client.run_browser_autotest(
        host_label="test-game",
        runtime_hash=HASH,
        game_id="test-game",
        game_version="1.0.0",
        portal_origin="https://portal.test:8443",
        games_domain="games.test",
        timeout_seconds=12,
    )

    assert result.passed is True
    assert result.report["playwright"] is True
    assert seen["url"] == "http://browser-autotest:8100/run"
    assert seen["timeout"] == 22
    assert seen["payload"]["runtime_hash"] == HASH
    assert "resolver" not in seen["payload"]


def test_client_transport_error_is_a_failed_report(
    monkeypatch: pytest.MonkeyPatch, settings: Any
) -> None:
    settings.BROWSER_AUTOTEST_URL = "http://browser-autotest:8100/run"

    def fake_urlopen(request: Any, timeout: int) -> Any:
        del request, timeout
        raise OSError("connection refused")

    monkeypatch.setattr(browser_client.urllib.request, "urlopen", fake_urlopen)

    result = browser_client.run_browser_autotest(
        host_label="test-game",
        runtime_hash=HASH,
        game_id="test-game",
        game_version="1.0.0",
        portal_origin="https://portal.test:8443",
        games_domain="games.test",
    )

    assert result.passed is False
    assert result.report["attempted"] is True
    assert "connection refused" in result.report["error"]


def test_browser_service_has_no_secret_env_or_edge_network() -> None:
    root = Path(__file__).resolve().parents[2]
    compose = (root / "compose.yml").read_text(encoding="utf-8")
    start = compose.index("  browser-autotest:\n")
    end = compose.index("  beat:\n", start)
    block = compose[start:end]

    assert "env_file" not in block
    assert "networks: [autotestnet]" in block
    assert "read_only: true" in block
    assert "BROWSER_AUTOTEST_URL" not in block
