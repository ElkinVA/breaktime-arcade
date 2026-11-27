"""Browser/E2E сценарии CRM для персонала (§2.16).

Запуск требует живой dev-стек и явного включения:
    BA_E2E=1 BA_E2E_BASE_URL=https://portal.test:8443 \
      .venv/bin/pytest tests/e2e/test_crm_e2e.py -m e2e

Фикстура создаёт одноразового сотрудника с ролью owner, обычного
пользователя без роли, одну игру с версией, реальные файлы пакета/runtime и
одну жалобу через ``manage.py shell`` в контейнере ``web``. Данные
уникальны для запуска и не являются production-данными; очистка не
выполняется, как и в остальных браузерных сценариях.
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
from playwright.sync_api import Browser, Download, Page, Response, expect, sync_playwright

BASE_URL = os.environ.get("BA_E2E_BASE_URL", "https://portal.test:8443").rstrip("/")
PASSWORD = "crm correct horse battery"
TOTP_INTERVAL_SECONDS = 30
ROOT = Path(__file__).resolve().parents[2]
SEED_MARKER = "CRM_E2E_SEED="

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


def _totp_value(secret: str, *, after: int | None = None) -> tuple[str, int]:
    """Return a TOTP code and its counter, optionally strictly newer than ``after``.

    The staff 2FA verifier rejects a TOTP counter that was already consumed, so
    login and step-up need distinct windows. Waiting is only needed if both
    actions happen more than one window apart.
    """
    deadline = time.monotonic() + TOTP_INTERVAL_SECONDS + 5
    while True:
        now_counter = int(time.time()) // TOTP_INTERVAL_SECONDS
        if after is None:
            counter = now_counter
        else:
            candidates = [
                candidate
                for candidate in (now_counter - 1, now_counter, now_counter + 1)
                if candidate > after
            ]
            if not candidates:
                if time.monotonic() >= deadline:
                    raise AssertionError("Could not obtain a fresh TOTP window")
                time.sleep(1)
                continue
            counter = min(candidates)
        return pyotp.TOTP(secret).at(counter * TOTP_INTERVAL_SECONDS), counter


def _seed_crm_fixture() -> dict[str, str]:
    """Create the staff/user/game/version/artifact/complaint fixture in dev."""
    suffix = uuid.uuid4().hex[:8]
    login = f"e2ecrm{suffix}"
    plain_login = f"e2eplain{suffix}"
    secret = pyotp.random_base32()
    technical_id = f"e2ecrm{suffix}"
    host_label = f"e2ecrm{suffix}"
    slug = f"e2e-crm-{suffix}"
    complaint_subject = f"E2E complaint {suffix}"
    resolution = f"E2E resolution {suffix}"

    seed_lines = [
        "import hashlib",
        "import json",
        "from pathlib import Path",
        "from django.conf import settings",
        "from django.utils import timezone",
        "from apps.accounts.models import StaffRole, User",
        "from apps.catalog.models import Game, GameVersion, Genre",
        "from apps.moderation.models import Complaint",
        "from apps.pipeline.services.artifacts import (",
        "    ensure_root,",
        "    package_path,",
        "    runtime_hash_for,",
        "    runtime_path,",
        ")",
        f"login = {login!r}",
        f"plain_login = {plain_login!r}",
        f"password = {PASSWORD!r}",
        f"secret = {secret!r}",
        f"technical_id = {technical_id!r}",
        f"host_label = {host_label!r}",
        f"slug = {slug!r}",
        f"complaint_subject = {complaint_subject!r}",
        f"resolution = {resolution!r}",
        "genre, _ = Genre.objects.get_or_create(",
        "    code='e2ecrm', defaults={'sort_order': 999}",
        ")",
        "user = User.objects.filter(login=login).first()",
        "if user is None:",
        "    user = User.objects.create_user(",
        "        login=login,",
        "        password=password,",
        "        is_staff=True,",
        "        crm_role=StaffRole.OWNER,",
        "    )",
        "else:",
        "    user.set_password(password)",
        "    user.is_staff = True",
        "    user.is_active = True",
        "    user.crm_role = StaffRole.OWNER",
        "    user.save()",
        "user.totp_secret = secret",
        "user.totp_confirmed_at = timezone.now()",
        "user.totp_last_counter = None",
        "user.save(",
        "    update_fields=['totp_secret', 'totp_confirmed_at', 'totp_last_counter']",
        ")",
        "plain_user = User.objects.filter(login=plain_login).first()",
        "if plain_user is None:",
        "    plain_user = User.objects.create_user(",
        "        login=plain_login,",
        "        password=password,",
        "    )",
        "else:",
        "    plain_user.set_password(password)",
        "    plain_user.is_active = True",
        "    plain_user.is_staff = False",
        "    plain_user.crm_role = ''",
        "    plain_user.save(",
        "        update_fields=['password', 'is_active', 'is_staff', 'crm_role']",
        "    )",
        "game, _ = Game.objects.update_or_create(",
        "    technical_id=technical_id,",
        "    defaults={",
        "        'host_label': host_label,",
        "        'slug': slug,",
        "        'primary_genre': genre,",
        "        'status': Game.STATUS_PUBLISHED,",
        "        'published_at': timezone.now(),",
        "    },",
        ")",
        "package_bytes = bytes.fromhex('504b0304') + b'e2e-crm-package'",
        "package_hash = hashlib.sha256(package_bytes).hexdigest()",
        "runtime_files = {",
        "    'index.html': b'<!doctype html><html><body>e2e</body></html>',",
        "    'js/ba-sdk.js': b'/* e2e sdk */',",
        "}",
        "runtime_hashes = {",
        "    name: hashlib.sha256(payload).hexdigest()",
        "    for name, payload in runtime_files.items()",
        "}",
        "runtime_hash = runtime_hash_for(runtime_hashes)",
        "package_root = ensure_root(Path(settings.ZIP_PIPELINE_STORAGE_ROOT))",
        "package_file = package_path(package_root, package_hash)",
        "package_file.parent.mkdir(parents=True, exist_ok=True)",
        "package_file.write_bytes(package_bytes)",
        "runtime_dir = runtime_path(",
        "    ensure_root(Path(settings.ZIP_PUBLIC_RUNTIME_ROOT)),",
        "    runtime_hash,",
        "    host_label,",
        ")",
        "for relative, payload in runtime_files.items():",
        "    path = runtime_dir / relative",
        "    path.parent.mkdir(parents=True, exist_ok=True)",
        "    path.write_bytes(payload)",
        "version, _ = GameVersion.objects.get_or_create(",
        "    game=game,",
        "    semver='1.0.0',",
        "    defaults={",
        "        'package_hash': package_hash,",
        "        'runtime_hash': runtime_hash,",
        "        'sdk_version': '1.1.0',",
        "        'size_bytes': len(package_bytes),",
        "        'manifest': {'name': 'E2E CRM fixture'},",
        "        'supported_languages': ['en', 'ru'],",
        "        'validation_report': {",
        "            'fixture': 'crm-artifacts-e2e',",
        "            'ok': True,",
        "            'summary': {'blocker': 0, 'warning': 0, 'info': 1},",
        "            'diagnostics': [",
        "                {",
        "                    'code': 'V_E2E',",
        "                    'severity': 'info',",
        "                    'file': 'index.html',",
        "                    'message': 'E2E fixture',",
        "                    'hint': '',",
        "                },",
        "            ],",
        "        },",
        "        'e2e_report': {'passed': True},",
        "        'import_report': {'status': 'created'},",
        "    },",
        ")",
        "if game.current_version_id != version.pk:",
        "    game.current_version = version",
        "    game.save(update_fields=['current_version'])",
        "complaint, _ = Complaint.objects.get_or_create(",
        "    game=game,",
        "    subject=complaint_subject,",
        "    defaults={",
        "        'target_type': Complaint.TARGET_GAME,",
        "        'category': Complaint.CATEGORY_SPAM,",
        "    },",
        ")",
        "print('CRM_E2E_SEED=' + json.dumps({",
        "    'login': user.login,",
        "    'plain_login': plain_user.login,",
        "    'password': password,",
        "    'secret': secret,",
        "    'game_id': str(game.pk),",
        "    'version_id': str(version.pk),",
        "    'technical_id': game.technical_id,",
        "    'slug': game.slug,",
        "    'semver': version.semver,",
        "    'complaint_id': str(complaint.pk),",
        "    'complaint_subject': complaint.subject,",
        "    'resolution': resolution,",
        "}))",
    ]

    docker = shutil.which("docker")
    assert docker is not None, "docker is required for the CRM E2E fixture"
    completed = subprocess.run(  # noqa: S603 - fixed local dev stack fixture
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
            "\n".join(seed_lines),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )

    for line in completed.stdout.splitlines():
        if line.startswith(SEED_MARKER):
            payload = json.loads(line[len(SEED_MARKER) :])
            return {str(key): str(value) for key, value in payload.items()}
    raise AssertionError(
        f"CRM E2E fixture did not return identifiers: {completed.stdout}\n{completed.stderr}"
    )


@pytest.fixture
def seeded_crm() -> dict[str, str]:
    """Seed a fresh staff/game/version/complaint for each browser scenario.

    Function scope keeps each disposable staff account's TOTP counter fresh,
    so scenarios do not race on the one-time TOTP window.
    """
    return _seed_crm_fixture()


def _login_with_2fa(page: Page, seed: dict[str, str]) -> int:
    """Log in as the seeded owner, verify TOTP and land on the CRM dashboard."""
    page.goto(f"{BASE_URL}/en/auth/login/?next=/crm/", wait_until="domcontentloaded")
    page.locator("[name=username]").fill(seed["login"])
    page.locator("[name=password]").fill(seed["password"])
    page.locator("form button[type=submit]").click()
    page.wait_for_url("**/en/auth/2fa/", wait_until="domcontentloaded")

    code, counter = _totp_value(seed["secret"])
    page.locator("[name=code]").fill(code)
    page.get_by_role("button", name="Verify").click()
    page.wait_for_url("**/crm/", wait_until="domcontentloaded")
    return counter


def test_crm_staff_journey(page: Page, seeded_crm: dict[str, str]) -> None:
    login_counter = _login_with_2fa(page, seeded_crm)

    # Dashboard: staff session and observable counters.
    response = page.goto(f"{BASE_URL}/crm/", wait_until="domcontentloaded")
    assert response is not None
    assert response.status == 200
    expect(page.locator('[data-testid="crm-current-user"]')).to_contain_text(seeded_crm["login"])
    published = page.locator('[data-testid="dashboard-published-games"]')
    expect(published).to_be_visible()
    assert int(published.inner_text().strip()) >= 1

    # Games list: the seeded published game is present with its version.
    response = page.goto(f"{BASE_URL}/crm/games/?status=published", wait_until="domcontentloaded")
    assert response is not None
    assert response.status == 200
    game_row = page.locator('[data-testid="crm-game-row"]').filter(
        has_text=seeded_crm["technical_id"]
    )
    expect(game_row).to_be_visible()
    expect(game_row.locator('[data-testid="crm-game-status"]')).to_have_text("Опубликована")
    expect(game_row.locator('[data-testid="crm-game-version"]')).to_contain_text(
        seeded_crm["semver"]
    )

    # Game card: status, current version and the version history table.
    with page.expect_navigation(wait_until="domcontentloaded") as navigation:
        game_row.locator('[data-testid="crm-game-link"]').click()
    detail_response = navigation.value
    assert detail_response is not None
    assert detail_response.status == 200
    page.wait_for_url(f"**/crm/games/{seeded_crm['game_id']}/", wait_until="domcontentloaded")
    expect(page.locator('[data-testid="crm-card-title"]')).to_have_text(seeded_crm["technical_id"])
    expect(page.locator('[data-testid="crm-card-status"]')).to_have_text("Опубликована")
    expect(page.locator('[data-testid="crm-card-current-version"]')).to_contain_text(
        seeded_crm["semver"]
    )
    version_row = page.locator('[data-testid="crm-version-row"]').filter(
        has_text=seeded_crm["semver"]
    )
    expect(version_row).to_be_visible()
    expect(version_row.locator('[data-testid="crm-version-languages"]')).to_contain_text("en")

    # Step-up with a fresh TOTP window, then resolve the seeded complaint.
    response = page.goto(
        f"{BASE_URL}/crm/step-up/?next=/crm/moderation/",
        wait_until="domcontentloaded",
    )
    assert response is not None
    assert response.status == 200
    expect(page.locator('[data-testid="crm-step-up-form"]')).to_be_visible()
    step_up_code = _totp_value(seeded_crm["secret"], after=login_counter)[0]
    page.locator('[data-testid="crm-step-up-password"]').fill(seeded_crm["password"])
    page.locator('[data-testid="crm-step-up-totp"]').fill(step_up_code)
    with page.expect_navigation(wait_until="domcontentloaded") as navigation:
        page.locator('[data-testid="crm-step-up-submit"]').click()
    step_up_response = navigation.value
    assert step_up_response is not None
    assert step_up_response.status == 200
    page.wait_for_url("**/crm/moderation/", wait_until="domcontentloaded")

    complaint_row = page.locator('[data-testid="crm-moderation-complaint"]').filter(
        has_text=seeded_crm["complaint_subject"]
    )
    expect(complaint_row).to_be_visible()
    expect(complaint_row.locator('[data-testid="crm-moderation-complaint-status"]')).to_have_text(
        "Новая"
    )
    complaint_row.locator('[data-testid="crm-moderation-resolution"]').fill(
        seeded_crm["resolution"]
    )
    with page.expect_navigation(wait_until="domcontentloaded") as navigation:
        complaint_row.locator('[data-testid="crm-moderation-resolve"]').click()
    resolve_response = navigation.value
    assert resolve_response is not None
    assert resolve_response.status == 200
    page.wait_for_url("**/crm/moderation/", wait_until="domcontentloaded")

    expect(page.locator('[data-testid="crm-message"]')).to_contain_text("Жалоба решена.")
    resolved_row = page.locator('[data-testid="crm-moderation-complaint"]').filter(
        has_text=seeded_crm["complaint_subject"]
    )
    expect(resolved_row.locator('[data-testid="crm-moderation-complaint-status"]')).to_have_text(
        "Решена"
    )
    expect(
        resolved_row.locator('[data-testid="crm-moderation-complaint-resolution"]')
    ).to_contain_text(seeded_crm["resolution"])

    # Audit journal: the resolve decision is visible with the acting staff login.
    response = page.goto(f"{BASE_URL}/crm/audit/", wait_until="domcontentloaded")
    assert response is not None
    assert response.status == 200
    audit_row = (
        page.locator('[data-testid="crm-audit-row"]')
        .filter(has_text=seeded_crm["login"])
        .filter(has_text="Решение по жалобе")
    )
    expect(audit_row.first).to_be_visible()


def test_crm_requires_staff_login(page: Page) -> None:
    """Anonymous visitors are redirected to the portal staff login screen."""
    response = page.goto(f"{BASE_URL}/crm/", wait_until="domcontentloaded")

    assert response is not None
    assert response.status == 200
    assert "/en/auth/login/" in page.url
    expect(page.locator("h1")).to_have_text("Log in")


def _artifact_urls(seed: dict[str, str]) -> dict[str, str]:
    base = f"{BASE_URL}/crm/games/{seed['game_id']}/versions/{seed['version_id']}"
    return {
        "package": f"{base}/package/",
        "runtime": f"{base}/runtime/",
        "report": f"{base}/reports/validation.json",
    }


def _game_detail_url(seed: dict[str, str]) -> str:
    return f"{BASE_URL}/crm/games/{seed['game_id']}/"


def _downloaded_bytes(download: Download) -> bytes:
    path = download.path()
    assert path is not None
    return Path(path).read_bytes()


def _redirected_urls(response: Response | None) -> list[str]:
    """Return the URL chain that produced ``response`` (newest request first)."""
    assert response is not None
    urls: list[str] = []
    request = response.request
    while request is not None:
        urls.append(request.url)
        request = request.redirected_from
    return urls


def test_crm_artifact_downloads(page: Page, seeded_crm: dict[str, str]) -> None:
    """Staff step up once and download the package, runtime and report artifacts."""
    login_counter = _login_with_2fa(page, seeded_crm)
    page.goto(_game_detail_url(seeded_crm), wait_until="domcontentloaded")
    version_row = page.locator('[data-testid="crm-version-row"]').filter(
        has_text=seeded_crm["semver"]
    )
    expect(version_row).to_be_visible()

    # The package link is step-up protected: an unelevated staff session is
    # diverted to the step-up form instead of receiving a download.
    with page.expect_navigation(wait_until="domcontentloaded"):
        version_row.locator('[data-testid="crm-version-package"]').click()
    page.wait_for_url("**/crm/step-up/**", wait_until="domcontentloaded")
    expect(page.locator('[data-testid="crm-step-up-form"]')).to_be_visible()

    step_up_code = _totp_value(seeded_crm["secret"], after=login_counter)[0]
    page.locator('[data-testid="crm-step-up-password"]').fill(seeded_crm["password"])
    page.locator('[data-testid="crm-step-up-totp"]').fill(step_up_code)
    with page.expect_download() as download_info:
        page.locator('[data-testid="crm-step-up-submit"]').click()
    package = download_info.value
    expected_version = f"game-{seeded_crm['game_id']}-version-{seeded_crm['version_id']}"
    assert package.suggested_filename == f"{expected_version}-package.zip"
    package_bytes = _downloaded_bytes(package)
    assert package_bytes.startswith(b"PK\x03\x04")
    assert package_bytes == bytes.fromhex("504b0304") + b"e2e-crm-package"

    page.goto(_game_detail_url(seeded_crm), wait_until="domcontentloaded")
    version_row = page.locator('[data-testid="crm-version-row"]').filter(
        has_text=seeded_crm["semver"]
    )
    with page.expect_download() as download_info:
        version_row.locator('[data-testid="crm-version-runtime"]').click()
    runtime = download_info.value
    assert runtime.suggested_filename == f"{expected_version}-runtime.zip"
    runtime_bytes = _downloaded_bytes(runtime)
    assert runtime_bytes.startswith(b"PK\x03\x04")

    with page.expect_download() as download_info:
        version_row.get_by_role("link", name="Валидация JSON").click()
    report = download_info.value
    assert report.suggested_filename == f"{expected_version}-validation.json"
    report_bytes = _downloaded_bytes(report)
    assert report_bytes
    assert json.loads(report_bytes)["fixture"] == "crm-artifacts-e2e"


def test_crm_artifacts_require_staff(page: Page, seeded_crm: dict[str, str]) -> None:
    """Anonymous and non-staff sessions are redirected away from every artifact URL."""
    urls = _artifact_urls(seeded_crm)

    for url in urls.values():
        response = page.goto(url, wait_until="domcontentloaded")
        assert any("/crm/login/" in item for item in _redirected_urls(response))

    page.goto(f"{BASE_URL}/en/auth/login/", wait_until="domcontentloaded")
    page.locator("[name=username]").fill(seeded_crm["plain_login"])
    page.locator("[name=password]").fill(seeded_crm["password"])
    page.locator("form button[type=submit]").click()
    page.wait_for_url("**/en/account/", wait_until="domcontentloaded")

    for url in urls.values():
        response = page.goto(url, wait_until="domcontentloaded")
        assert any("/crm/login/" in item for item in _redirected_urls(response))
