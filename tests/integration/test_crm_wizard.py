"""CRM ZIP wizard, reports, diff and step-up publish (§2.14.5, §2.16.1)."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pyotp
import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import empty
from PIL import Image

from apps.accounts.models import StaffRole, User
from apps.catalog.models import Game, GameVersion, Genre
from apps.crm.services.reports import csv_cell
from apps.i18n.models import Language
from apps.pipeline.models import GameImportDraft

PASSWORD = "correct horse battery staple"


@pytest.fixture
def wizard_env(db, tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path / "media")
    settings.ZIP_PIPELINE_STORAGE_ROOT = str(tmp_path / "store")
    settings.ZIP_PUBLIC_RUNTIME_ROOT = str(tmp_path / "runtime")
    settings.SDK_SOURCE_ROOT = str(tmp_path / "sdk")
    default_storage._wrapped = empty
    sdk = tmp_path / "sdk" / "1.1.0" / "ba-sdk.js"
    sdk.parent.mkdir(parents=True, exist_ok=True)
    sdk.write_bytes(b"/* official SDK 1.1.0 */")
    Genre.objects.get_or_create(code="arcade")
    Genre.objects.get_or_create(code="puzzle")
    Language.objects.get_or_create(code="en", defaults={"name": "English"})
    yield tmp_path
    default_storage._wrapped = empty


def _png(color: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (1280, 720), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _manifest(
    *,
    version: str = "1.0.0",
    name: str = "Test Game",
    genre: str = "arcade",
) -> dict[str, object]:
    return {
        "cartridge": 1,
        "id": "test_game",
        "version": version,
        "sdkVersion": "^1.0",
        "protocol": 1,
        "name": name,
        "entry": "index.html",
        "genre": genre,
        "tags": ["reflex"],
        "supportedLanguages": ["en"],
        "defaultLanguage": "en",
        "mobileSupport": True,
        "orientation": "any",
        "estimatedPlayMinutes": 5,
        "theme": {"accent": "#39FF88"},
        "score": {
            "type": "integer",
            "unit": "points",
            "direction": "higher_is_better",
            "minValue": 0,
            "maxValue": 1000,
            "schemaVersion": 1,
        },
        "limits": {
            "minPlaytimeSeconds": 15,
            "maxSessionSeconds": 1800,
            "pauseOnBlur": True,
        },
        "capabilities": {
            "wasm": False,
            "pointerLock": False,
            "storage": "sdk",
            "externalOrigins": [],
        },
        "leaderboard": {"enabled": True, "claimedVerification": "client_reported"},
        "assets": {
            "cover": "assets/cover.png",
            "screenshots": ["assets/screen-1.png", "assets/screen-2.png"],
            "critical": [
                "index.html",
                "css/style.css",
                "js/ba-sdk.js",
                "js/rng.js",
                "js/game.js",
                "locales/en.json",
            ],
            "criticalPathBytes": 20000,
        },
        "credits": [{"author": "Test", "license": "CC0-1.0", "aiGenerated": True}],
    }


def _catalog(*, name: str = "Test Game") -> dict[str, object]:
    return {
        "name": name,
        "shortDescription": "Short description",
        "description": "D" * 300,
        "instructions": "Use the arrow keys",
        "controls": "Arrow keys",
        "seoTitle": name,
        "seoDescription": "Test game description",
        "coverAlt": "Cover alt",
        "screenshotAlts": ["Screenshot one", "Screenshot two"],
    }


def _package(
    *,
    version: str = "1.0.0",
    name: str = "Test Game",
    genre: str = "arcade",
    extra: dict[str, bytes] | None = None,
) -> bytes:
    manifest = _manifest(version=version, name=name, genre=genre)
    files: dict[str, bytes] = {
        "manifest.json": json.dumps(manifest).encode(),
        "index.html": (
            b'<!doctype html><html><head><link rel="stylesheet" href="css/style.css">'
            b'</head><body><script src="js/ba-sdk.js"></script>'
            b'<script src="js/rng.js"></script><script src="js/game.js"></script>'
            b"</body></html>"
        ),
        "css/style.css": b"body { margin: 0; }",
        "js/ba-sdk.js": b"/* BA-SDK MOCK - replaced by the platform */",
        "js/rng.js": b"var seeded = 1;",
        "js/game.js": b"var started = true;",
        "locales/en.json": json.dumps({"start": "START"}).encode(),
        "catalog/en.json": json.dumps(_catalog(name=name)).encode(),
        "assets/cover.png": _png((10, 20, 30)),
        "assets/screen-1.png": _png((40, 50, 60)),
        "assets/screen-2.png": _png((70, 80, 90)),
    }
    if extra:
        files.update(extra)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name_in_zip, payload in files.items():
            archive.writestr(name_in_zip, payload)
    return buffer.getvalue()


def _staff_client(
    secret: str = "",
    *,
    role: str = StaffRole.OWNER,
) -> tuple[User, Client]:
    staff = User.objects.create_user(
        login="staff",
        password=PASSWORD,
        is_staff=True,
        crm_role=role,
    )
    User.objects.filter(pk=staff.pk).update(
        totp_confirmed_at=timezone.now(),
        totp_secret=secret,
        totp_last_counter=None,
    )
    staff.refresh_from_db()
    client = Client()
    client.force_login(staff)
    session = client.session
    session["ba_2fa_verified"] = True
    session.save()
    return staff, client


def _elevate(client: Client) -> None:
    session = client.session
    session["crm_step_up_at"] = timezone.now().isoformat()
    session.save()


def _upload(
    client: Client,
    data: bytes,
    *,
    filename: str = "game.zip",
    game: Game | None = None,
):
    payload: dict[str, object] = {
        "package": SimpleUploadedFile(filename, data, content_type="application/zip")
    }
    if game is not None:
        payload["game_id"] = str(game.id)
    return client.post(reverse("crm:wizard_upload"), payload)


def _latest_draft() -> GameImportDraft:
    draft = GameImportDraft.objects.order_by("-created_at").first()
    assert draft is not None
    return draft


@pytest.mark.django_db
def test_wizard_upload_accepts_valid_package_and_persists_reports(wizard_env: Path) -> None:
    _staff, client = _staff_client()

    response = _upload(client, _package())

    assert response.status_code == 302
    draft = _latest_draft()
    assert response.url == reverse("crm:wizard_analysis", args=[draft.id])
    assert draft.status == GameImportDraft.STATUS_IMPORTED
    assert draft.game is not None and draft.version is not None
    assert draft.validation_report["ok"] is True
    assert draft.e2e_report["passed"] is True
    assert draft.package_hash
    assert Game.objects.count() == 1
    assert GameVersion.objects.count() == 1

    analysis = client.get(reverse("crm:wizard_analysis", args=[draft.id]))
    assert analysis.status_code == 200
    content = analysis.content.decode()
    assert 'data-testid="crm-wizard-status"' in content
    assert 'data-testid="crm-wizard-report-json"' in content
    assert 'data-testid="crm-wizard-report-csv"' in content
    assert 'data-testid="crm-wizard-next-card"' in content
    assert draft.package_hash not in content
    assert draft.version.runtime_hash not in content

    card = client.get(reverse("crm:wizard_card", args=[draft.id]))
    assert card.status_code == 200
    card_content = card.content.decode()
    assert 'data-testid="crm-wizard-card-id">test_game<' in card_content
    assert 'data-testid="crm-wizard-diff-empty"' in card_content
    assert draft.package_hash not in card_content

    check = client.get(reverse("crm:wizard_check", args=[draft.id]))
    assert check.status_code == 200
    check_content = check.content.decode()
    assert 'data-testid="crm-wizard-autotest-status">Пройден<' in check_content
    assert 'data-testid="crm-wizard-ready"' in check_content

    publish = client.get(reverse("crm:wizard_publish", args=[draft.id]))
    assert publish.status_code == 200
    publish_content = publish.content.decode()
    assert 'data-testid="crm-wizard-publish-form"' in publish_content
    assert 'data-testid="crm-wizard-publish-ready"' in publish_content


@pytest.mark.django_db
def test_wizard_rejects_unsafe_package_with_structured_diagnostics(wizard_env: Path) -> None:
    _staff, client = _staff_client()

    response = _upload(client, _package(extra={"../evil.js": b"var evil = 1;"}))

    assert response.status_code == 302
    draft = _latest_draft()
    assert draft.status == GameImportDraft.STATUS_REJECTED
    assert draft.version is None
    assert Game.objects.count() == 0
    codes = {item["code"] for item in draft.validation_report["diagnostics"]}
    assert "V_PATH_TRAVERSAL" in codes

    analysis = client.get(reverse("crm:wizard_analysis", args=[draft.id]))
    content = analysis.content.decode()
    assert 'data-testid="crm-wizard-rejected"' in content
    assert "V_PATH_TRAVERSAL" in content
    assert 'data-testid="crm-wizard-diagnostic-row"' in content
    assert 'data-testid="crm-wizard-blocked-next"' in content
    assert 'data-testid="crm-wizard-next-card"' not in content


@pytest.mark.django_db
def test_wizard_rejects_invalid_zip_and_oversized_package(
    wizard_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _staff, client = _staff_client()

    _upload(client, b"this is not a zip")
    invalid = _latest_draft()
    assert invalid.status == GameImportDraft.STATUS_REJECTED
    codes = {item["code"] for item in invalid.validation_report["diagnostics"]}
    assert "V_ARCHIVE_BAD" in codes

    from apps.pipeline.validation import structure

    monkeypatch.setattr(structure, "MAX_ZIP_BYTES", 4)
    _upload(client, b"12345")
    oversized = GameImportDraft.objects.exclude(pk=invalid.pk).get()
    assert oversized.status == GameImportDraft.STATUS_REJECTED
    codes = {item["code"] for item in oversized.validation_report["diagnostics"]}
    assert "V_ARCHIVE_TOO_LARGE" in codes


@pytest.mark.django_db
def test_wizard_shows_import_diff_for_crm_overrides(wizard_env: Path) -> None:
    _staff, client = _staff_client()
    _upload(client, _package())
    draft = _latest_draft()
    assert draft.game is not None
    game = draft.game
    game.overridden_fields = ["primary_genre"]
    game.save(update_fields=["overridden_fields"])

    response = _upload(
        client,
        _package(version="1.1.0", genre="puzzle", name="Updated Game"),
        game=game,
    )

    assert response.status_code == 302
    updated = GameImportDraft.objects.exclude(pk=draft.id).get()
    assert updated.version is not None
    assert any(item["field"] == "primary_genre" for item in updated.conflicts)

    card = client.get(reverse("crm:wizard_card", args=[updated.id]))
    content = card.content.decode()
    assert 'data-testid="crm-wizard-diff-row"' in content
    assert "primary_genre" in content
    assert "arcade" in content
    assert "puzzle" in content
    assert "keep" in content

    game.refresh_from_db()
    assert game.primary_genre.code == "arcade"
    assert game.versions.count() == 2

    upload_page = client.get(reverse("crm:wizard_upload"), {"game_id": str(game.id)})
    assert 'data-testid="crm-wizard-target-game"' in upload_page.content.decode()


@pytest.mark.django_db
def test_report_download_json_and_csv_are_safe(wizard_env: Path) -> None:
    _staff, client = _staff_client()
    _upload(client, _package())
    draft = _latest_draft()
    assert draft.version is not None

    json_response = client.get(reverse("crm:wizard_report", args=[draft.id]), {"format": "json"})
    assert json_response.status_code == 200
    assert json_response["Content-Type"].startswith("application/json")
    assert json_response["Content-Disposition"].startswith("attachment;")
    assert f"draft-{draft.id}-report.json" in json_response["Content-Disposition"]
    assert json_response["X-Content-Type-Options"] == "nosniff"
    payload = json.loads(json_response.content)
    assert payload["draft"]["id"] == str(draft.id)
    assert payload["validation"]["ok"] is True
    assert payload["autotest"]["passed"] is True
    assert "package_path" not in payload["draft"]
    assert "runtime_path" not in payload["draft"]
    body = json_response.content.decode()
    assert str(wizard_env) not in body

    csv_response = client.get(reverse("crm:wizard_report", args=[draft.id]), {"format": "csv"})
    assert csv_response.status_code == 200
    assert csv_response["Content-Type"].startswith("text/csv")
    assert f"draft-{draft.id}-report.csv" in csv_response["Content-Disposition"]
    assert csv_response.content.decode().splitlines()[0] == "code,severity,file,message,hint"

    bad = client.get(reverse("crm:wizard_report", args=[draft.id]), {"format": "../x"})
    assert bad.status_code == 400

    assert csv_cell("=2+2") == "'=2+2"
    assert csv_cell("normal") == "normal"


@pytest.mark.django_db
def test_report_and_wizard_require_staff(wizard_env: Path) -> None:
    _staff, staff_client = _staff_client()
    _upload(staff_client, _package())
    draft = _latest_draft()

    anonymous = Client()
    for url in (
        reverse("crm:wizard_upload"),
        reverse("crm:wizard_analysis", args=[draft.id]),
        reverse("crm:wizard_card", args=[draft.id]),
        reverse("crm:wizard_check", args=[draft.id]),
        reverse("crm:wizard_publish", args=[draft.id]),
        reverse("crm:wizard_report", args=[draft.id]),
    ):
        response = anonymous.get(url)
        assert response.status_code == 302
        assert response.url == reverse("crm:login")

    plain = User.objects.create_user(login="plain", password=PASSWORD)
    non_staff = Client()
    non_staff.force_login(plain)
    response = non_staff.get(reverse("crm:wizard_report", args=[draft.id]))
    assert response.status_code == 302
    assert response.url == reverse("crm:login")
    assert draft.package_hash not in response.content.decode()


@pytest.mark.django_db
def test_step_up_requires_password_and_totp_and_failure_changes_nothing() -> None:
    secret = pyotp.random_base32()
    _staff, client = _staff_client(secret)
    code = pyotp.TOTP(secret).now()
    url = reverse("crm:step_up")

    page = client.get(url)
    assert page.status_code == 200
    assert 'data-testid="crm-step-up-form"' in page.content.decode()

    wrong_password = client.post(url, {"password": "wrong", "totp_code": code})
    assert wrong_password.status_code == 200
    assert "crm_step_up_at" not in client.session

    wrong_code = client.post(url, {"password": PASSWORD, "totp_code": "000000"})
    assert wrong_code.status_code == 200
    assert "crm_step_up_at" not in client.session

    success = client.post(
        url,
        {"password": PASSWORD, "totp_code": code, "next": reverse("crm:games")},
    )
    assert success.status_code == 302
    assert success.url == reverse("crm:games")
    assert "crm_step_up_at" in client.session


@pytest.mark.django_db
def test_wizard_publish_requires_step_up_and_publishes_on_success(wizard_env: Path) -> None:
    secret = pyotp.random_base32()
    _staff, client = _staff_client(secret)
    _upload(client, _package())
    draft = _latest_draft()
    assert draft.game is not None and draft.version is not None
    game = draft.game
    version = draft.version
    publish_url = reverse("crm:wizard_publish", args=[draft.id])

    no_step_up = client.post(publish_url, {"version_id": str(version.id)})
    assert no_step_up.status_code == 200
    assert 'data-testid="crm-wizard-publish-error"' in no_step_up.content.decode()
    game.refresh_from_db()
    assert game.current_version_id is None

    bad = client.post(
        publish_url,
        {"version_id": str(version.id), "password": "wrong", "totp_code": "000000"},
    )
    assert bad.status_code == 200
    game.refresh_from_db()
    assert game.current_version_id is None

    code = pyotp.TOTP(secret).now()
    success = client.post(
        publish_url,
        {"version_id": str(version.id), "password": PASSWORD, "totp_code": code},
    )
    assert success.status_code == 302
    assert success.url == reverse("crm:game_detail", args=[game.id])
    game.refresh_from_db()
    draft.refresh_from_db()
    assert game.current_version_id == version.id
    assert game.status == Game.STATUS_PUBLISHED
    assert draft.status == GameImportDraft.STATUS_PUBLISHED


@pytest.mark.django_db
def test_wizard_publish_accepts_recent_session_step_up(wizard_env: Path) -> None:
    _staff, client = _staff_client()
    _elevate(client)
    _upload(client, _package())
    draft = _latest_draft()
    assert draft.game is not None and draft.version is not None

    response = client.post(
        reverse("crm:wizard_publish", args=[draft.id]),
        {"version_id": str(draft.version.id)},
    )

    assert response.status_code == 302
    draft.game.refresh_from_db()
    assert draft.game.current_version_id == draft.version.id


@pytest.mark.django_db
def test_publish_and_rollback_require_step_up_on_game_card() -> None:
    genre = Genre.objects.create(code="stepup_genre")
    game = Game.objects.create(
        technical_id="stepup_game",
        host_label="stepup-game.games.test",
        slug="stepup-game",
        primary_genre=genre,
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
    )
    old = GameVersion.objects.create(
        game=game,
        semver="1.0.0",
        package_hash="a" * 64,
        runtime_hash="b" * 64,
        sdk_version="1.1.0",
        size_bytes=1000,
        manifest={},
        supported_languages=["en"],
        validation_report={"ok": True, "summary": {"blocker": 0}},
        e2e_report={"passed": True},
    )
    new = GameVersion.objects.create(
        game=game,
        semver="2.0.0",
        package_hash="c" * 64,
        runtime_hash="d" * 64,
        sdk_version="1.1.0",
        size_bytes=1000,
        manifest={},
        supported_languages=["en"],
        validation_report={"ok": True, "summary": {"blocker": 0}},
        e2e_report={"passed": True},
    )
    game.current_version = new
    game.save(update_fields=["current_version"])
    secret = pyotp.random_base32()
    _staff, client = _staff_client(secret)

    publish_url = reverse("crm:game_publish", args=[game.id])
    rollback_url = reverse("crm:game_rollback", args=[game.id])

    no_step_up = client.post(publish_url, {"version_id": str(old.id)})
    assert no_step_up.status_code == 302
    game.refresh_from_db()
    assert game.current_version_id == new.id

    wrong = client.post(
        publish_url,
        {"version_id": str(old.id), "password": PASSWORD, "totp_code": "000000"},
    )
    assert wrong.status_code == 302
    game.refresh_from_db()
    assert game.current_version_id == new.id

    code = pyotp.TOTP(secret).now()
    published = client.post(
        publish_url,
        {"version_id": str(old.id), "password": PASSWORD, "totp_code": code},
    )
    assert published.status_code == 302
    game.refresh_from_db()
    assert game.current_version_id == old.id

    # The same successful step-up elevates the session for rollback.
    rolled_back = client.post(rollback_url, {"version_id": str(new.id)})
    assert rolled_back.status_code == 302
    game.refresh_from_db()
    assert game.current_version_id == new.id

    plain = User.objects.create_user(login="plain", password=PASSWORD)
    non_staff = Client()
    non_staff.force_login(plain)
    response = non_staff.post(publish_url, {"version_id": str(old.id)})
    assert response.status_code == 302
    assert response.url == reverse("crm:login")
    game.refresh_from_db()
    assert game.current_version_id == new.id


@pytest.mark.django_db
def test_publish_and_upload_are_csrf_protected(wizard_env: Path) -> None:
    staff, client = _staff_client()
    _elevate(client)
    _upload(client, _package())
    draft = _latest_draft()
    assert draft.game is not None and draft.version is not None

    guarded = Client(enforce_csrf_checks=True)
    guarded.force_login(staff)
    guarded_session = guarded.session
    guarded_session["ba_2fa_verified"] = True
    guarded_session["crm_step_up_at"] = timezone.now().isoformat()
    guarded_session.save()

    csrf_upload = guarded.post(
        reverse("crm:wizard_upload"),
        {"package": SimpleUploadedFile("game.zip", _package(), content_type="application/zip")},
    )
    assert csrf_upload.status_code == 403

    csrf_publish = guarded.post(
        reverse("crm:wizard_publish", args=[draft.id]),
        {"version_id": str(draft.version.id)},
    )
    assert csrf_publish.status_code == 403
    draft.game.refresh_from_db()
    assert draft.game.current_version_id is None


@pytest.mark.django_db
def test_upload_form_rejects_non_zip_and_empty_file(wizard_env: Path) -> None:
    _staff, client = _staff_client()

    response = client.post(
        reverse("crm:wizard_upload"),
        {"package": SimpleUploadedFile("game.txt", b"hello", content_type="text/plain")},
    )

    assert response.status_code == 200
    assert 'data-testid="crm-wizard-upload-error"' in response.content.decode()
    assert GameImportDraft.objects.count() == 0
    assert Game.objects.count() == 0

    empty = client.post(
        reverse("crm:wizard_upload"),
        {"package": SimpleUploadedFile("empty.zip", b"", content_type="application/zip")},
    )
    assert empty.status_code == 200
    assert 'data-testid="crm-wizard-upload-error"' in empty.content.decode()
    assert GameImportDraft.objects.count() == 0
