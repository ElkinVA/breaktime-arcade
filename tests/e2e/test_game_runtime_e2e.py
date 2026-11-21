"""Cross-origin runtime handshake for the App F probe game.

Requires the dev stack and a runtime probe:

    make probe-seed
    BA_E2E=1 BA_E2E_BASE_URL=https://portal.test:8443 \
      .venv/bin/pytest tests/e2e/test_game_runtime_e2e.py -m e2e
"""

from __future__ import annotations

import os

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright

BASE_URL = os.environ.get("BA_E2E_BASE_URL", "https://portal.test:8443").rstrip("/")

pytestmark = pytest.mark.e2e

if os.environ.get("BA_E2E") != "1":
    pytest.skip(
        "BA_E2E не включён; задайте BA_E2E=1 и BA_E2E_BASE_URL",
        allow_module_level=True,
    )


@pytest.fixture(scope="module")
def browser() -> Browser:
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(
            headless=True,
            args=["--host-resolver-rules=MAP probe.games.test 127.0.0.1"],
        )
        yield instance
        instance.close()


@pytest.fixture
def page(browser: Browser) -> Page:
    context = browser.new_context(
        ignore_https_errors=True,
        viewport={"width": 1280, "height": 720},
    )
    instance = context.new_page()
    yield instance
    context.close()


def test_probe_handshake_and_storage_relay(page: Page) -> None:
    response = page.goto(f"{BASE_URL}/en/games/probe/play/", wait_until="domcontentloaded")
    assert response is not None
    assert response.status == 200

    frame = page.frame_locator("#game-frame")
    status = frame.locator("#probe-status")
    expect(status).to_have_attribute("data-state", "ready", timeout=15000)
    expect(frame.locator("#probe-context")).to_contain_text('"gameId": "probe"')
    assert page.frames[1].url.startswith("https://probe.games.test:8443/v/")

    frame.locator("#probe-storage").click()
    expect(status).to_have_attribute("data-state", "storage", timeout=10000)
    expect(status).to_contain_text('"n":1')

    frame.locator("#probe-bad").click()
    expect(status).to_have_attribute("data-state", "host-error", timeout=10000)
    expect(status).to_contain_text("E_MESSAGE_INVALID")


def test_probe_rejects_mismatched_portal_origin(page: Page) -> None:
    page.goto(f"{BASE_URL}/en/games/probe/play/", wait_until="domcontentloaded")
    runtime_url = page.locator("#game-frame").get_attribute("src")
    assert runtime_url is not None
    bad_url = runtime_url.replace(
        "p=https%3A%2F%2Fportal.test%3A8443",
        "p=https%3A%2F%2Fevil.test",
    )
    page.evaluate(
        """(src) => {
            const frame = document.createElement("iframe");
            frame.id = "bad-frame";
            frame.src = src;
            document.body.appendChild(frame);
        }""",
        bad_url,
    )
    bad_status = page.frame_locator("#bad-frame").locator("#probe-status")
    expect(bad_status).to_have_attribute("data-state", "error", timeout=15000)
    expect(bad_status).to_contain_text("BA_SDK_BAD_FRAGMENT")
