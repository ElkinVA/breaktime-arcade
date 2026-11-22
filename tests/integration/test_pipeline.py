"""Integration coverage for the ZIP → card/version → publish pipeline."""

from __future__ import annotations

import io
import json
import os
import stat
import zipfile
from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.storage import default_storage
from django.utils.functional import empty
from PIL import Image

from apps.catalog.models import Game, GameVersion, Genre, Tag
from apps.i18n.models import Language
from apps.pipeline.models import GameImportDraft, ZipExtractionJob
from apps.pipeline.services.importer import import_package
from apps.pipeline.services.publishing import publish_version
from apps.pipeline.services.rollback import rollback_version
from apps.pipeline.services.worker import cleanup_expired_jobs, cleanup_upload_jobs


@pytest.fixture
def pipeline_env(db, tmp_path, settings, inline_zip_worker):
    settings.MEDIA_ROOT = str(tmp_path / "media")
    settings.ZIP_UPLOADS_ROOT = str(tmp_path / "zip-uploads")
    settings.ZIP_ARTIFACTS_ROOT = str(tmp_path / "zip-artifacts")
    default_storage._wrapped = empty
    Genre.objects.get_or_create(code="arcade")
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
    game_js: str = "var started = true;",
    extra: dict[str, bytes] | None = None,
    root_folder: str | None = None,
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
        "js/game.js": game_js.encode(),
        "locales/en.json": json.dumps({"start": "START"}).encode(),
        "catalog/en.json": json.dumps(_catalog(name=name)).encode(),
        "assets/cover.png": _png((10, 20, 30)),
        "assets/screen-1.png": _png((40, 50, 60)),
        "assets/screen-2.png": _png((70, 80, 90)),
        "README.md": b"# Test Game\n",
        "SELF-CHECK.md": b"# Self check\n",
    }
    if extra:
        files.update(extra)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name_in_zip, payload in files.items():
            if root_folder:
                name_in_zip = f"{root_folder}/{name_in_zip}"
            archive.writestr(name_in_zip, payload)
    return buffer.getvalue()


def _official_sdk(env: Path) -> Path:
    sdk = env / "sdk" / "1.1.0" / "ba-sdk.js"
    sdk.parent.mkdir(parents=True, exist_ok=True)
    if not sdk.is_file():
        sdk.write_bytes(b"/* official SDK 1.1.0 */")
    return sdk


def _run(env: Path, data: bytes, **kwargs):
    _official_sdk(env)
    return import_package(
        data,
        storage_root=env / "store",
        runtime_root=env / "runtime",
        sdk_root=env / "sdk",
        **kwargs,
    )


@pytest.mark.django_db
def test_valid_package_creates_card_version_and_runtime(pipeline_env: Path) -> None:
    data = _package()
    result = _run(pipeline_env, data)

    assert result.status == "created"
    assert result.ok
    assert result.game is not None and result.version is not None
    game = result.game
    version = result.version
    assert game.technical_id == "test_game"
    assert game.primary_genre.code == "arcade"
    assert Game.objects.count() == 1
    assert GameVersion.objects.count() == 1
    assert version.package_hash != version.runtime_hash
    assert version.sdk_version == "1.1.0"
    assert version.entry_path == "index.html"
    assert version.validation_report["ok"] is True
    assert version.e2e_report["passed"] is True
    assert version.injection_report["path"] == "js/ba-sdk.js"

    original = Path(result.draft.package_path)
    assert original.is_file()
    assert original.read_bytes() == data
    assert original.name == f"{version.package_hash}.zip"

    runtime_dir = pipeline_env / "runtime" / "test-game" / version.runtime_hash
    assert runtime_dir.is_dir()
    assert (runtime_dir / "index.html").is_file()
    official_sdk = _official_sdk(pipeline_env)
    assert (runtime_dir / "js" / "ba-sdk.js").read_bytes() == official_sdk.read_bytes()
    assert result.draft.runtime_path == str(runtime_dir)

    assert stat.S_IMODE(runtime_dir.stat().st_mode) == 0o755
    for path in runtime_dir.rglob("*"):
        expected = 0o755 if path.is_dir() else 0o644
        assert stat.S_IMODE(path.stat().st_mode) == expected, path

    assert game.translations.count() == 1
    translation = game.translations.get()
    assert translation.name == "Test Game"
    assert game.assets.count() == 3
    assert Tag.objects.filter(code="reflex").exists()
    assert result.draft.status == GameImportDraft.STATUS_IMPORTED

    job = ZipExtractionJob.objects.get(draft=result.draft)
    assert job.status == ZipExtractionJob.STATUS_COMPLETED
    assert job.queue == "zip"
    assert job.attempts == 1
    assert not (pipeline_env / "zip-uploads" / str(job.id)).exists()


@pytest.mark.django_db
def test_single_root_folder_is_supported(pipeline_env: Path) -> None:
    result = _run(pipeline_env, _package(root_folder="test_game-1.0.0"))

    assert result.status == "created"
    assert result.game is not None
    assert result.game.technical_id == "test_game"


@pytest.mark.django_db
def test_duplicate_package_is_idempotent(pipeline_env: Path) -> None:
    data = _package()
    first = _run(pipeline_env, data)
    second = _run(pipeline_env, data)

    assert first.status == "created"
    assert second.status == "duplicate"
    assert second.version is not None and first.version is not None
    assert second.version.pk == first.version.pk
    assert Game.objects.count() == 1
    assert GameVersion.objects.count() == 1
    assert any(item.code == "I_DUPLICATE_PACKAGE" for item in second.report.diagnostics)


@pytest.mark.django_db
def test_quota_exhaustion_is_non_destructive_for_published_version(
    pipeline_env: Path, settings
) -> None:
    first = _run(pipeline_env, _package())
    assert first.game is not None and first.version is not None
    game = first.game
    version = first.version
    assert publish_version(game, version).ok
    runtime_dir = Path(first.draft.runtime_path)
    runtime_files = {
        path.relative_to(runtime_dir).as_posix(): path.read_bytes()
        for path in runtime_dir.rglob("*")
        if path.is_file()
    }
    package_path = Path(first.draft.package_path)
    package_bytes = package_path.read_bytes()
    packages_before = sorted((pipeline_env / "store" / "packages").iterdir())

    settings.ZIP_STORAGE_QUOTA_BYTES = 1
    settings.ZIP_STORAGE_MIN_FREE_BYTES = 0
    settings.ZIP_QUOTA_STATE_ROOT = pipeline_env / "quota-state"

    second = _run(pipeline_env, _package(version="1.1.0"))

    assert second.status == "rejected"
    assert any(item.code == "X_STORAGE_QUOTA" for item in second.report.diagnostics)
    assert GameVersion.objects.filter(game=game).count() == 1
    game.refresh_from_db()
    assert game.current_version_id == version.id
    assert game.status == Game.STATUS_PUBLISHED
    assert package_path.read_bytes() == package_bytes
    assert sorted((pipeline_env / "store" / "packages").iterdir()) == packages_before
    assert {
        path.relative_to(runtime_dir).as_posix(): path.read_bytes()
        for path in runtime_dir.rglob("*")
        if path.is_file()
    } == runtime_files


@pytest.mark.django_db
def test_broker_failure_does_not_damage_published_version(pipeline_env: Path, monkeypatch) -> None:
    from apps.pipeline.services import extraction

    first = _run(pipeline_env, _package())
    assert first.game is not None and first.version is not None
    game = first.game
    version = first.version
    assert publish_version(game, version).ok
    runtime_dir = Path(first.draft.runtime_path)
    runtime_before = {
        path.relative_to(runtime_dir).as_posix(): path.read_bytes()
        for path in runtime_dir.rglob("*")
        if path.is_file()
    }

    def unavailable(_job_id: str) -> str:
        raise RuntimeError("broker down")

    monkeypatch.setattr(extraction, "enqueue_extraction", unavailable)
    second = _run(pipeline_env, _package(version="1.1.0"))

    assert second.status == "rejected"
    assert any(item.code == "X_WORKER_UNAVAILABLE" for item in second.report.diagnostics)
    assert GameVersion.objects.filter(game=game).count() == 1
    game.refresh_from_db()
    assert game.current_version_id == version.id
    assert {
        path.relative_to(runtime_dir).as_posix(): path.read_bytes()
        for path in runtime_dir.rglob("*")
        if path.is_file()
    } == runtime_before


@pytest.mark.django_db
def test_duplicate_import_creates_no_additional_storage(pipeline_env: Path) -> None:
    data = _package()
    first = _run(pipeline_env, data)
    assert first.version is not None
    packages_before = sorted((pipeline_env / "store" / "packages").iterdir())
    runtimes_before = sorted((pipeline_env / "runtime").rglob("*"))

    second = _run(pipeline_env, data)

    assert second.status == "duplicate"
    assert second.version is not None and second.version.pk == first.version.pk
    assert GameVersion.objects.count() == 1
    assert sorted((pipeline_env / "store" / "packages").iterdir()) == packages_before
    assert sorted((pipeline_env / "runtime").rglob("*")) == runtimes_before


def test_cleanup_rerun_never_touches_published_artifacts(pipeline_env: Path) -> None:
    store = pipeline_env / "store"
    runtime = pipeline_env / "runtime"
    uploads = Path(settings.ZIP_UPLOADS_ROOT)
    artifacts = Path(settings.ZIP_ARTIFACTS_ROOT)
    (store / "packages").mkdir(parents=True, exist_ok=True)
    (runtime / "published").mkdir(parents=True, exist_ok=True)
    package = store / "packages" / "abc.zip"
    package.write_bytes(b"original")
    runtime_file = runtime / "published" / "index.html"
    runtime_file.write_bytes(b"published")
    abandoned = uploads / "00000000-0000-0000-0000-000000000001"
    abandoned.mkdir(parents=True)
    (abandoned / "source.zip").write_bytes(b"abandoned")
    os.utime(abandoned, (1_000_000, 1_000_000))
    expired = artifacts / "00000000-0000-0000-0000-000000000002"
    expired.mkdir(parents=True)
    os.utime(expired, (1_000_000, 1_000_000))

    first_uploads = cleanup_upload_jobs(uploads_root=uploads, staging_ttl=60, now=1_000_061)
    second_uploads = cleanup_upload_jobs(uploads_root=uploads, staging_ttl=60, now=1_000_061)
    first_artifacts = cleanup_expired_jobs(
        artifacts_root=artifacts, staging_ttl=60, completed_ttl=60, now=1_000_061
    )
    second_artifacts = cleanup_expired_jobs(
        artifacts_root=artifacts, staging_ttl=60, completed_ttl=60, now=1_000_061
    )

    assert first_uploads == {"removed": 1}
    assert second_uploads == {"removed": 0}
    assert first_artifacts["removed"] == 1
    assert second_artifacts["removed"] == 0
    assert package.read_bytes() == b"original"
    assert runtime_file.read_bytes() == b"published"


@pytest.mark.django_db
def test_reimport_preserves_crm_overrides_and_records_conflicts(pipeline_env: Path) -> None:
    first = _run(pipeline_env, _package())
    assert first.game is not None and first.version is not None
    game = first.game
    game.overridden_fields = ["primary_genre"]
    game.save(update_fields=["overridden_fields"])
    translation = game.translations.get()
    translation.overridden_fields = ["name"]
    translation.save(update_fields=["overridden_fields"])
    Genre.objects.create(code="puzzle")

    updated = _run(
        pipeline_env,
        _package(version="1.1.0", name="Renamed Game", genre="puzzle"),
        target_game=game,
    )

    assert updated.status == "updated"
    assert updated.version is not None
    game.refresh_from_db()
    translation.refresh_from_db()
    assert game.primary_genre.code == "arcade"
    assert translation.name == "Test Game"
    assert GameVersion.objects.filter(game=game).count() == 2

    conflicts = updated.conflicts
    assert any(item["field"] == "primary_genre" for item in conflicts)
    assert any(item["scope"] == "translation:en" and item["field"] == "name" for item in conflicts)
    assert updated.version.import_report["conflicts"]


@pytest.mark.django_db
def test_unsafe_path_is_rejected(pipeline_env: Path) -> None:
    data = _package(extra={"../evil.js": b"var evil = 1;"})
    result = _run(pipeline_env, data)

    assert result.status == "rejected"
    codes = {item.code for item in result.report.diagnostics}
    assert "V_PATH_TRAVERSAL" in codes
    assert Game.objects.count() == 0
    assert GameVersion.objects.count() == 0
    assert result.draft.status == GameImportDraft.STATUS_REJECTED
    assert result.draft.validation_report["ok"] is False


@pytest.mark.django_db
def test_forbidden_api_is_rejected(pipeline_env: Path) -> None:
    data = _package(game_js='eval("1 + 1");')
    result = _run(pipeline_env, data)

    assert result.status == "rejected"
    codes = {item.code for item in result.report.diagnostics}
    assert "V_FORBIDDEN_API" in codes
    assert Game.objects.count() == 0


@pytest.mark.django_db
def test_duplicate_semver_with_other_payload_is_rejected(pipeline_env: Path) -> None:
    first = _run(pipeline_env, _package())
    assert first.game is not None
    second = _run(
        pipeline_env,
        _package(game_js="var changed = true;"),
        target_game=first.game,
    )

    assert second.status == "rejected"
    assert any(item.code == "V_VERSION_DUP" for item in second.report.diagnostics)
    assert GameVersion.objects.filter(game=first.game).count() == 1


@pytest.mark.django_db
def test_publish_and_rollback_switch_current_version(pipeline_env: Path) -> None:
    first = _run(pipeline_env, _package())
    assert first.game is not None and first.version is not None
    game = first.game
    second = _run(pipeline_env, _package(version="1.1.0"), target_game=game)
    assert second.version is not None

    published_first = publish_version(game, first.version)
    assert published_first.ok
    game.refresh_from_db()
    assert game.current_version_id == first.version.id
    assert game.status == Game.STATUS_PUBLISHED
    published_at = game.published_at
    assert published_at is not None

    published_second = publish_version(game, second.version)
    assert published_second.ok
    game.refresh_from_db()
    assert game.current_version_id == second.version.id

    rolled_back = rollback_version(game, first.version)
    assert rolled_back.ok
    game.refresh_from_db()
    assert game.current_version_id == first.version.id
    assert game.status == Game.STATUS_PUBLISHED
    assert game.published_at == published_at


@pytest.mark.django_db
def test_publish_blocks_without_green_autotest(pipeline_env: Path) -> None:
    first = _run(pipeline_env, _package())
    assert first.game is not None and first.version is not None
    game = first.game
    blocked_version = GameVersion.objects.create(
        game=game,
        semver="2.0.0",
        package_hash="9" * 64,
        runtime_hash="8" * 64,
        sdk_version="1.1.0",
        size_bytes=1024,
        manifest={"id": "test_game"},
        supported_languages=["en"],
        validation_report={"ok": True, "summary": {"blocker": 0}},
        e2e_report={"passed": False},
    )

    result = publish_version(game, blocked_version)

    assert not result.ok
    assert result.reason == "V_AUTOTEST_FAILED"
    game.refresh_from_db()
    assert game.current_version_id is None
