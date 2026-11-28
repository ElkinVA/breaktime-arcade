"""Browser journey from the home genre block to a genre landing page."""

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


def test_home_genre_link_opens_localized_genre_page(page: Page) -> None:
    response = page.goto(f"{BASE_URL}/en/", wait_until="domcontentloaded")

    assert response is not None
    assert response.status == 200
    block = page.locator('[data-testid="home-genres"]')
    expect(block).to_be_visible()
    link = block.locator('[data-testid="home-genre-link"]').first
    expect(link).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    href = link.get_attribute("href")
    assert href is not None and "/en/genres/" in href

    link.click()
    page.wait_for_url("**/en/genres/**", wait_until="domcontentloaded")
    assert page.locator("h1").is_visible()
    assert page.locator("#genre-sort").is_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
