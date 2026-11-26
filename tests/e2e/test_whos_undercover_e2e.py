"""Browser E2E for the Who's Undercover? Pass & Play cartridge.

Requires the dev stack and the game imported/published by the dev seed.
"""

from __future__ import annotations

import os

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright

BASE_URL = os.environ.get("BA_E2E_BASE_URL", "https://portal.test:8443").rstrip("/")
GAME_URL = f"{BASE_URL}/en/games/whos-undercover/play/"

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
            args=["--host-resolver-rules=MAP whos-undercover.games.test 127.0.0.1"],
        )
        yield instance
        instance.close()


@pytest.fixture
def page(browser: Browser) -> Page:
    context = browser.new_context(
        ignore_https_errors=True,
        viewport={"width": 1280, "height": 900},
    )
    instance = context.new_page()
    yield instance
    context.close()


def _start_page(page: Page):
    page.goto(GAME_URL, wait_until="domcontentloaded")
    frame = page.frame_locator("#game-frame")
    expect(frame.locator("#setup-screen")).to_be_visible(timeout=15000)
    return frame


def test_setup_and_secret_card_fit_a_360px_phone(page: Page) -> None:
    page.set_viewport_size({"width": 360, "height": 740})
    frame = _start_page(page)
    expect(frame.locator("#start-game")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    assert frame.locator("#setup-screen").evaluate("el => el.scrollWidth <= el.clientWidth + 1")

    frame.locator("#start-game").click()
    frame.locator("#reveal-open").click()
    expect(frame.locator("#reveal-card")).to_be_visible()
    assert frame.locator("#reveal-card").evaluate("el => el.scrollWidth <= el.clientWidth + 1")


def test_russian_locale_reveals_a_role_and_projector_board(page: Page) -> None:
    page.goto(f"{BASE_URL}/ru/games/whos-undercover/play/", wait_until="domcontentloaded")
    frame = page.frame_locator("#game-frame")
    expect(frame.locator("#setup-screen")).to_be_visible(timeout=15000)
    expect(frame.locator("#setup-screen h1")).to_contain_text("Соберите стол")

    frame.locator("#start-game").click()
    frame.locator("#reveal-open").click()
    expect(frame.locator("#reveal-role")).to_be_visible()
    role = frame.locator("#reveal-role").inner_text()
    assert role in {"Мирный", "Под прикрытием", "Мистер Белый"}
    frame.locator("#reveal-hide").click()

    # Reveal the remaining cards, then check the public projector class.
    for _ in range(3):
        frame.locator("#reveal-open").click()
        frame.locator("#reveal-hide").click()
    expect(frame.locator("#board-screen")).to_be_visible()
    frame.locator("#projector-toggle").click()
    assert frame.locator("#app").evaluate("el => el.classList.contains('is-projector')")


def test_pass_and_play_round_keeps_secrets_and_reveals_winner(page: Page) -> None:
    frame = _start_page(page)
    undercover_name = None

    frame.locator("#start-game").click()
    expect(frame.locator("#reveal-screen")).to_be_visible()
    for _ in range(4):
        expect(frame.locator("#reveal-card")).to_be_hidden()
        frame.locator("#reveal-open").click()
        expect(frame.locator("#reveal-card")).to_be_visible()
        role = frame.locator("#reveal-role").inner_text()
        name = frame.locator("#reveal-player-label").inner_text()
        if role == "Undercover":
            undercover_name = name
        frame.locator("#reveal-hide").click()

    assert undercover_name is not None
    expect(frame.locator("#board-screen")).to_be_visible()
    expect(frame.locator("#speaker-name")).not_to_be_empty()
    for _ in range(4):
        frame.locator("#next-clue").click()
    expect(frame.locator("#start-vote")).to_be_visible()
    frame.locator("#start-vote").click()

    for _ in range(4):
        expect(frame.locator("#vote-handoff")).to_be_visible()
        frame.locator("#vote-open").click()
        expect(frame.locator("#vote-ballot")).to_be_visible()
        target = frame.locator("#vote-targets button", has_text=undercover_name)
        if target.is_disabled():
            target = frame.locator("#vote-targets button:not([disabled])").first
        target.click()
        frame.locator("#vote-confirm").click()

    expect(frame.locator("#gameover-screen")).to_be_visible(timeout=15000)
    expect(frame.locator("#winner-title")).to_have_text("Civilians win")
    expect(frame.locator("#final-roster")).to_contain_text("Undercover")
    expect(frame.locator("#play-again")).to_be_visible()
