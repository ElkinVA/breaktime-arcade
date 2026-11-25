"""Cross-origin runtime handshake for the App F probe game.

Requires the dev stack and a runtime probe:

    make probe-seed
    BA_E2E=1 BA_E2E_BASE_URL=https://portal.test:8443 \
      .venv/bin/pytest tests/e2e/test_game_runtime_e2e.py -m e2e
"""

from __future__ import annotations

import os
import re
import uuid

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


def test_probe_guest_submit_is_forbidden_and_leaderboard_survives(page: Page) -> None:
    page.goto(f"{BASE_URL}/en/games/probe/play/", wait_until="domcontentloaded")

    frame = page.frame_locator("#game-frame")
    status = frame.locator("#probe-status")
    expect(status).to_have_attribute("data-state", "ready", timeout=15000)

    frame.locator("#probe-submit").click()
    expect(status).to_have_attribute("data-state", "submitted", timeout=10000)
    expect(status).to_contain_text("E_GUEST_FORBIDDEN")

    frame.locator("#probe-leaderboard").click()
    expect(status).to_have_attribute("data-state", "leaderboard", timeout=10000)
    expect(status).to_contain_text('"entries"')


def test_probe_exit_keeps_the_portal_usable(page: Page) -> None:
    page.goto(f"{BASE_URL}/en/games/probe/play/", wait_until="domcontentloaded")

    frame = page.frame_locator("#game-frame")
    status = frame.locator("#probe-status")
    expect(status).to_have_attribute("data-state", "ready", timeout=15000)

    frame.locator("#probe-exit").click()
    expect(status).to_have_attribute("data-state", "exited", timeout=10000)
    expect(page.locator("#player-status")).to_be_hidden()


def test_authenticated_player_submits_leaderboard_and_returns(page: Page) -> None:
    suffix = uuid.uuid4().hex[:10]
    login = f"probe{suffix}"
    nickname = f"Probe{suffix}"
    page.goto(f"{BASE_URL}/en/auth/register/", wait_until="domcontentloaded")
    page.locator("[name=login]").fill(login)
    page.locator("[name=nickname]").fill(nickname)
    page.locator("[name=password1]").fill("correct horse battery staple")
    page.locator("[name=password2]").fill("correct horse battery staple")
    page.locator("[name=age_confirmed]").check()
    page.locator("[name=terms_accepted]").check()
    page.locator("[name=privacy_accepted]").check()
    page.locator("form button[type=submit]").click()
    page.wait_for_url("**/en/account/", wait_until="domcontentloaded")

    page.goto(f"{BASE_URL}/en/games/probe/play/", wait_until="domcontentloaded")
    frame = page.frame_locator("#game-frame")
    status = frame.locator("#probe-status")
    expect(status).to_have_attribute("data-state", "ready", timeout=15000)

    # The probe declares the minimum playtime as durationMs; wait it out so
    # the server's duration-vs-session-elapsed check can pass.
    page.wait_for_timeout(11000)
    frame.locator("#probe-submit").click()
    expect(status).to_have_attribute("data-state", "submitted", timeout=15000)
    expect(status).to_contain_text('"status":"saved"')
    expect(status).to_contain_text('"isPersonalBest":true')

    frame.locator("#probe-leaderboard").click()
    expect(status).to_have_attribute("data-state", "leaderboard", timeout=10000)
    expect(status).to_contain_text(nickname)

    page.get_by_role("link", name="← probe").click()
    page.wait_for_url("**/en/games/probe/", wait_until="domcontentloaded")


def test_probe_rejects_mismatched_portal_origin(page: Page) -> None:
    page.goto(f"{BASE_URL}/en/games/probe/play/", wait_until="domcontentloaded")
    frame_locator = page.locator("#game-frame")
    # Session creation is asynchronous now; wait for the player to set src.
    expect(frame_locator).to_have_attribute(
        "src", re.compile(r"^https://probe\.games\.test"), timeout=15000
    )
    runtime_url = frame_locator.get_attribute("src")
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
