"""Browser/E2E сценарий регистрации, входа и кабинета (§2.10).

Запуск требует живой dev-стек и явного включения:
    BA_E2E=1 BA_E2E_BASE_URL=https://portal.test:8443 \
      .venv/bin/pytest tests/e2e -m e2e

Тест создаёт уникального пользователя в dev-БД и не удаляет его
автоматически: dev-данные не являются production, а cleanup через внешний
браузерный процесс не должен маскироваться под бизнес-операцию.
"""

from __future__ import annotations

import os
import uuid

import pytest
from playwright.sync_api import Browser, Page, sync_playwright

BASE_URL = os.environ.get("BA_E2E_BASE_URL", "https://portal.test:8443").rstrip("/")
PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "new correct horse battery"

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
        viewport={"width": 1280, "height": 900},
    )
    instance = context.new_page()
    yield instance
    context.close()


def _identity() -> tuple[str, str, str]:
    suffix = uuid.uuid4().hex[:10]
    return f"e2e{suffix}", f"E2E{suffix}", f"e2e-{suffix}@example.test"


def _register(page: Page, login: str, nickname: str, email: str) -> None:
    page.goto(f"{BASE_URL}/en/auth/register/", wait_until="domcontentloaded")
    page.locator("[name=login]").fill(login)
    page.locator("[name=nickname]").fill(nickname)
    page.locator("[name=password1]").fill(PASSWORD)
    page.locator("[name=password2]").fill(PASSWORD)
    page.locator("[name=email]").fill(email)
    page.locator("[name=age_confirmed]").check()
    page.locator("[name=terms_accepted]").check()
    page.locator("[name=privacy_accepted]").check()
    page.locator("form button[type=submit]").click()
    page.wait_for_url("**/en/account/", wait_until="domcontentloaded")


def _login(page: Page, login: str, password: str = PASSWORD) -> None:
    page.goto(f"{BASE_URL}/en/auth/login/", wait_until="domcontentloaded")
    page.locator("[name=username]").fill(login)
    page.locator("[name=password]").fill(password)
    page.locator("form button[type=submit]").click()
    page.wait_for_url("**/en/account/", wait_until="domcontentloaded")


def test_registration_profile_password_and_deletion_window(page: Page) -> None:
    login, nickname, email = _identity()
    _register(page, login, nickname, email)

    assert page.locator("h1").inner_text().strip() == nickname
    assert email in page.content()
    assert "not verified" in page.content()

    export = page.request.get(f"{BASE_URL}/en/account/export/")
    assert export.status == 200
    assert export.json()["login"] == login

    page.get_by_role("banner").get_by_role("button", name="Log out").click()
    page.wait_for_url(f"{BASE_URL}/en/", wait_until="domcontentloaded")

    _login(page, login)
    page.get_by_role("link", name="Change password").click()
    page.locator("[name=old_password]").fill(PASSWORD)
    page.locator("[name=new_password1]").fill(NEW_PASSWORD)
    page.locator("[name=new_password2]").fill(NEW_PASSWORD)
    page.get_by_role("button", name="Save password").click()
    page.wait_for_url("**/en/account/", wait_until="domcontentloaded")

    page.get_by_role("banner").get_by_role("button", name="Log out").click()
    page.wait_for_url(f"{BASE_URL}/en/", wait_until="domcontentloaded")
    _login(page, login, NEW_PASSWORD)

    page.get_by_role("link", name="Delete account").click()
    page.locator("[name=password]").fill(NEW_PASSWORD)
    page.locator("[name=confirmation]").fill("DELETE")
    page.get_by_role("button", name="Request deletion").click()
    page.wait_for_url("**/en/account/", wait_until="domcontentloaded")
    assert "Deletion requested" in page.content()

    page.get_by_role("button", name="Cancel deletion").click()
    page.wait_for_url("**/en/account/", wait_until="domcontentloaded")
    assert "Deletion requested" not in page.content()


def test_registration_form_requires_consent(page: Page) -> None:
    login, nickname, email = _identity()
    page.goto(f"{BASE_URL}/en/auth/register/", wait_until="domcontentloaded")
    page.locator("[name=login]").fill(login)
    page.locator("[name=nickname]").fill(nickname)
    page.locator("[name=password1]").fill(PASSWORD)
    page.locator("[name=password2]").fill(PASSWORD)
    page.locator("[name=email]").fill(email)
    page.locator("form button[type=submit]").click()

    assert page.url.endswith("/en/auth/register/")
    assert page.locator("[name=terms_accepted]").count() == 1
