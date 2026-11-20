"""Browser/E2E smoke для публичной языковой оболочки.

Запуск требует живой dev-стек и явного включения:
    BA_E2E=1 BA_E2E_BASE_URL=https://portal.test:8443 \
      .venv/bin/pytest tests/e2e -m e2e

По умолчанию модуль пропускается, чтобы обычный unit/integration прогон
не зависел от запущенного браузера и TLS-сертификата.
"""

from __future__ import annotations

import os

import pytest
from playwright.sync_api import Browser, Page, sync_playwright

BASE_URL = os.environ.get("BA_E2E_BASE_URL", "https://portal.test:8443").rstrip("/")
LANGUAGES = ("en", "de", "nl", "ru", "fr", "es")

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
        viewport={"width": 1280, "height": 720},
    )
    instance = context.new_page()
    yield instance
    context.close()


@pytest.mark.parametrize("language", LANGUAGES)
def test_language_pages_render(page: Page, language: str) -> None:
    response = page.goto(f"{BASE_URL}/{language}/", wait_until="domcontentloaded")

    assert response is not None
    assert response.status == 200
    assert page.locator("html").get_attribute("lang") == language
    assert response.header_value("content-language") == language
    assert page.locator("h1").inner_text().strip()


def test_root_redirects_using_accept_language(browser: Browser) -> None:
    context = browser.new_context(
        ignore_https_errors=True,
        extra_http_headers={"Accept-Language": "de"},
    )
    page = context.new_page()
    try:
        response = page.goto(f"{BASE_URL}/", wait_until="domcontentloaded")
        assert response is not None
        assert response.status == 200
        assert page.url.endswith("/de/")
        assert page.locator("html").get_attribute("lang") == "de"
    finally:
        context.close()


def test_unknown_language_prefix_is_404(page: Page) -> None:
    response = page.goto(f"{BASE_URL}/xx/games/", wait_until="domcontentloaded")

    assert response is not None
    assert response.status == 404
    assert "lang-menu" not in page.content()


def test_language_switcher_has_only_local_active_links(page: Page) -> None:
    page.goto(f"{BASE_URL}/de/", wait_until="domcontentloaded")

    links = page.locator("#lang-menu a")
    hrefs = [link.get_attribute("href") for link in links.all()]

    assert len(hrefs) == len(LANGUAGES)
    assert all(href and href.startswith("/") for href in hrefs)
    assert all("//" not in href for href in hrefs if href)


def test_mobile_view_has_no_horizontal_overflow(page: Page) -> None:
    page.set_viewport_size({"width": 360, "height": 640})
    page.goto(f"{BASE_URL}/de/", wait_until="domcontentloaded")

    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


def test_healthz_is_available(page: Page) -> None:
    response = page.goto(f"{BASE_URL}/healthz", wait_until="domcontentloaded")

    assert response is not None
    assert response.status == 200
    assert '"status": "ok"' in page.content().replace("\n", "")
