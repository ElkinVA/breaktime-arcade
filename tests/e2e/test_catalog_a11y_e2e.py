"""Browser checks for catalog control keyboard focus, labels and 360 px layout.

Requires a live dev stack (``BA_E2E=1``), like the other e2e modules.
"""

from __future__ import annotations

import os

import pytest
from playwright.sync_api import Browser, Page, sync_playwright

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
        instance = playwright.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture
def page(browser: Browser) -> Page:
    context = browser.new_context(
        ignore_https_errors=True,
        viewport={"width": 360, "height": 640},
    )
    instance = context.new_page()
    yield instance
    context.close()


def test_catalog_controls_fit_360px_without_horizontal_scroll(page: Page) -> None:
    response = page.goto(f"{BASE_URL}/de/games/", wait_until="domcontentloaded")

    assert response is not None
    assert response.status == 200
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    assert page.locator("#catalog-search").is_visible()


def test_catalog_controls_have_accessible_labels(page: Page) -> None:
    page.goto(f"{BASE_URL}/de/games/", wait_until="domcontentloaded")

    for selector in (
        "#catalog-search",
        "#catalog-genre",
        "#catalog-duration",
        "#catalog-sort",
        "#catalog-mobile",
    ):
        count = page.eval_on_selector(
            selector,
            "el => (el.labels ? el.labels.length : 0) + (el.getAttribute('aria-label') ? 1 : 0)",
        )
        assert count >= 1, selector


def test_catalog_controls_show_keyboard_focus_ring(page: Page) -> None:
    page.goto(f"{BASE_URL}/de/games/", wait_until="domcontentloaded")
    page.locator("#catalog-search").focus()
    # A real Tab/Shift+Tab pair makes Chromium apply :focus-visible.
    page.keyboard.press("Tab")
    page.keyboard.press("Shift+Tab")

    assert page.evaluate("document.activeElement && document.activeElement.id") == "catalog-search"
    outline_style = page.evaluate("getComputedStyle(document.activeElement).outlineStyle")
    outline_width = page.evaluate("getComputedStyle(document.activeElement).outlineWidth")
    assert outline_style != "none"
    assert outline_width not in ("", "0px")
