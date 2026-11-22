"""The real Neon Snake package must import and publish through the pipeline."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from django.core.files.storage import default_storage
from django.utils.functional import empty

from apps.catalog.models import Game, GameAsset, GameVersion, Genre
from apps.i18n.models import Language
from apps.pipeline.services.importer import import_package
from apps.pipeline.services.publishing import publish_version

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "games-src" / "neon_snake"
OFFICIAL_SDK = ROOT / "sdk" / "1.1.0" / "ba-sdk.js"
LANGUAGES = {
    "en": "English",
    "de": "Deutsch",
    "nl": "Nederlands",
    "ru": "Русский",
    "fr": "Français",
    "es": "Español",
}


def _load_pack() -> ModuleType:
    path = PACKAGE / "pack.py"
    spec = importlib.util.spec_from_file_location("neon_snake_pack_import", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def neon_env(db, tmp_path, settings, inline_zip_worker):
    settings.MEDIA_ROOT = str(tmp_path / "media")
    settings.ZIP_UPLOADS_ROOT = str(tmp_path / "zip-uploads")
    settings.ZIP_ARTIFACTS_ROOT = str(tmp_path / "zip-artifacts")
    settings.ZIP_QUOTA_STATE_ROOT = str(tmp_path / "quota-state")
    settings.ZIP_STORAGE_MIN_FREE_BYTES = 0
    default_storage._wrapped = empty  # type: ignore[attr-defined]
    genre, _ = Genre.objects.get_or_create(code="arcade")
    assert genre.sort_order >= 0
    for code, name in LANGUAGES.items():
        Language.objects.get_or_create(code=code, defaults={"name": name})
    yield tmp_path
    default_storage._wrapped = empty  # type: ignore[attr-defined]


@pytest.mark.django_db
def test_neon_snake_imports_persists_and_publishes(neon_env: Path) -> None:
    pack = _load_pack()
    zip_path = pack.build_zip(neon_env / "neon_snake.zip")
    data = zip_path.read_bytes()

    result = import_package(
        data,
        original_filename="neon_snake-1.0.0.zip",
        storage_root=neon_env / "store",
        runtime_root=neon_env / "runtime",
        sdk_root=ROOT / "sdk",
    )

    assert result.status == "created"
    assert result.ok
    assert result.game is not None and result.version is not None
    game = result.game
    version = result.version

    assert game.technical_id == "neon_snake"
    assert game.host_label == "neon-snake"
    assert game.primary_genre.code == "arcade"
    assert game.default_language == "en"
    assert game.score_max_value == 100000
    assert game.score_unit == "points"
    assert game.max_session_seconds == 1800
    assert game.pause_on_blur is True
    assert game.capabilities["storage"] == "sdk"
    assert game.capabilities["externalOrigins"] == []

    assert version.semver == "1.0.0"
    assert version.package_hash != version.runtime_hash
    assert version.sdk_version == "1.1.0"
    assert version.entry_path == "index.html"
    assert (version.critical_path_bytes_declared or 0) > 0
    assert (version.critical_path_bytes_measured or 0) > 0
    assert version.e2e_report["passed"] is True
    assert version.injection_report["path"] == "js/ba-sdk.js"
    official_sha = hashlib.sha256(OFFICIAL_SDK.read_bytes()).hexdigest()
    assert version.injection_report["after_sha256"] == official_sha
    assert version.injection_report["sdk_version"] == "1.1.0"
    assert version.validation_report["ok"] is True

    # Card translations from catalog/*.json.
    assert game.translations.count() == 6
    translations = {
        item.language.code: item for item in game.translations.select_related("language")
    }
    assert set(translations) == set(LANGUAGES)
    assert translations["en"].name == "Neon Snake"
    assert translations["de"].name == "Neon Snake"
    assert translations["ru"].name == "Neon Snake"
    assert translations["en"].description.startswith("Neon Snake brings")

    # Cover + two screenshots, each with alt text in all six languages.
    assert game.assets.count() == 3
    cover = game.assets.get(type=GameAsset.TYPE_COVER)
    shots = list(game.assets.filter(type=GameAsset.TYPE_SCREENSHOT).order_by("sort_order"))
    assert cover.sort_order == 0
    assert len(shots) == 2
    for asset in [cover, *shots]:
        assert asset.width == 1280 and asset.height == 720
        assert set(asset.alt) == set(LANGUAGES)
        assert all(asset.alt[code] for code in LANGUAGES)
        assert asset.file.name
        stored = neon_env / "media" / asset.file.name
        assert stored.is_file()
        assert stored.stat().st_mode & 0o777 == 0o644

    # Runtime bundle persists with the official SDK injected, not the packaged copy.
    runtime_dir = Path(result.draft.runtime_path)
    assert runtime_dir.is_dir()
    assert (runtime_dir / "index.html").is_file()
    assert (runtime_dir / "js" / "game.js").is_file()
    assert (runtime_dir / "locales" / "ru.json").is_file()
    assert (runtime_dir / "catalog" / "es.json").is_file()
    assert (runtime_dir / "assets" / "cover.webp").is_file()
    assert (runtime_dir / "js" / "ba-sdk.js").read_bytes() == OFFICIAL_SDK.read_bytes()
    assert (runtime_dir / "js" / "ba-sdk.js").read_bytes() != data

    original = Path(result.draft.package_path)
    assert original.is_file()
    assert original.read_bytes() == data

    assert publish_version(game, version).ok
    game.refresh_from_db()
    assert game.status == Game.STATUS_PUBLISHED
    assert game.current_version_id == version.id
    assert Game.objects.count() == 1
    assert GameVersion.objects.count() == 1
