"""Browser/E2E сценарий регистрации, входа и кабинета (§2.10).

Запуск требует живой dev-стек и явного включения:
    BA_E2E=1 BA_E2E_BASE_URL=https://portal.test:8443 \
      .venv/bin/pytest tests/e2e -m e2e

Тест создаёт уникального пользователя в dev-БД и не удаляет его
автоматически: dev-данные не являются production, а cleanup через внешний
браузерный процесс не должен маскироваться под бизнес-операцию.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pyotp
import pytest
from playwright.sync_api import Browser, Page, sync_playwright

BASE_URL = os.environ.get("BA_E2E_BASE_URL", "https://portal.test:8443").rstrip("/")
PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "new correct horse battery"
STAFF_PASSWORD = "staff correct horse battery"
ROOT = Path(__file__).resolve().parents[2]

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


def _ensure_staff_user(login: str, password: str) -> None:
    """Create a disposable staff account for the browser 2FA scenarios.

    The 2FA setup UI is intentionally staff-only. This is a test-only fixture in
    the live dev database; it does not touch production data or the model
    sandbox. The normal account scenarios still use browser registration.
    """
    shell_code = (
        "from apps.accounts.models import User\n"
        "from apps.accounts.services.registration import ensure_profile, register_user\n"
        f"login = {login!r}\n"
        f"password = {password!r}\n"
        "user = User.objects.filter(login=login).first()\n"
        "if user is None:\n"
        "    user = register_user(\n"
        "        login=login,\n"
        "        password=password,\n"
        "        nickname=login,\n"
        "        age_confirmed=True,\n"
        "        terms_accepted=True,\n"
        "        privacy_accepted=True,\n"
        "    )\n"
        "user.is_staff = True\n"
        "user.is_active = True\n"
        "user.set_password(password)\n"
        "user.save()\n"
        "ensure_profile(user)\n"
    )
    docker = shutil.which("docker")
    assert docker is not None, "docker is required for the staff 2FA fixture"
    subprocess.run(  # noqa: S603 - fixed local dev stack fixture
        [
            docker,
            "compose",
            "-f",
            "compose.yml",
            "-f",
            "compose.dev-lite.yml",
            "exec",
            "-T",
            "web",
            "python",
            "manage.py",
            "shell",
            "-c",
            shell_code,
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


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


def test_export_download_and_password_change(page: Page) -> None:
    login, nickname, email = _identity()
    _register(page, login, nickname, email)

    with page.expect_download() as download_info:
        page.get_by_role("link", name="Export data").click()
    download = download_info.value
    path = download.path()
    assert path is not None
    exported = json.loads(Path(path).read_text(encoding="utf-8"))
    assert exported["login"] == login

    page.get_by_role("link", name="Change password").click()
    page.locator("[name=old_password]").fill(PASSWORD)
    page.locator("[name=new_password1]").fill(NEW_PASSWORD)
    page.locator("[name=new_password2]").fill(NEW_PASSWORD)
    page.get_by_role("button", name="Save password").click()
    page.wait_for_url("**/en/account/", wait_until="domcontentloaded")

    page.get_by_role("banner").get_by_role("button", name="Log out").click()
    page.wait_for_url(f"{BASE_URL}/en/", wait_until="domcontentloaded")
    _login(page, login, NEW_PASSWORD)
    assert page.url.endswith("/en/account/")


def test_deletion_request_sets_flag_and_cancel(page: Page) -> None:
    login, nickname, email = _identity()
    _register(page, login, nickname, email)

    page.get_by_role("link", name="Delete account").click()
    page.locator("[name=password]").fill(PASSWORD)
    page.locator("[name=confirmation]").fill("DELETE")
    page.get_by_role("button", name="Request deletion").click()
    page.wait_for_url("**/en/account/", wait_until="domcontentloaded")
    assert "Deletion requested" in page.content()

    page.get_by_role("button", name="Cancel deletion").click()
    page.wait_for_url("**/en/account/", wait_until="domcontentloaded")
    assert "Deletion requested" not in page.content()


def test_staff_two_factor_enrollment_and_disable(page: Page) -> None:
    suffix = uuid.uuid4().hex[:10]
    login = f"e2estaff{suffix}"
    _ensure_staff_user(login, STAFF_PASSWORD)

    page.goto(f"{BASE_URL}/en/auth/login/", wait_until="domcontentloaded")
    page.locator("[name=username]").fill(login)
    page.locator("[name=password]").fill(STAFF_PASSWORD)
    page.locator("form button[type=submit]").click()
    page.wait_for_url("**/en/auth/2fa/setup/", wait_until="domcontentloaded")
    secret = page.locator("p:has-text('Secret:') code").inner_text()
    page.locator("[name=code]").fill(pyotp.TOTP(secret).now())
    page.get_by_role("button", name="Enable 2FA").click()
    page.get_by_text("Two-factor authentication is enabled.").wait_for(
        state="visible", timeout=10000
    )

    page.get_by_role("banner").get_by_role("button", name="Log out").click()
    page.wait_for_url(f"{BASE_URL}/en/", wait_until="domcontentloaded")

    page.goto(f"{BASE_URL}/en/auth/login/", wait_until="domcontentloaded")
    page.locator("[name=username]").fill(login)
    page.locator("[name=password]").fill(STAFF_PASSWORD)
    page.locator("form button[type=submit]").click()
    page.wait_for_url("**/en/auth/2fa/", wait_until="domcontentloaded")
    time.sleep(31)
    page.locator("[name=code]").fill(pyotp.TOTP(secret).now())
    page.get_by_role("button", name="Verify").click()
    page.wait_for_url("**/en/account/", wait_until="domcontentloaded")

    page.get_by_role("link", name="Disable 2FA").click()
    page.locator("[name=password]").fill(STAFF_PASSWORD)
    time.sleep(31)
    page.locator("[name=code]").fill(pyotp.TOTP(secret).now())
    page.get_by_role("button", name="Disable 2FA").click()
    page.wait_for_url("**/en/auth/login/", wait_until="domcontentloaded")

    page.goto(f"{BASE_URL}/en/auth/login/", wait_until="domcontentloaded")
    page.locator("[name=username]").fill(login)
    page.locator("[name=password]").fill(STAFF_PASSWORD)
    page.locator("form button[type=submit]").click()
    page.wait_for_url("**/en/auth/2fa/setup/", wait_until="domcontentloaded")
    assert "/en/auth/2fa/verify/" not in page.url
