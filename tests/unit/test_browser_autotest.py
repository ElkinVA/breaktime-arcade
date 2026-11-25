"""Browser autotest report merging and URL construction."""

from __future__ import annotations

from apps.pipeline.services.browser_autotest import merge_autotest_reports, runtime_url


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
