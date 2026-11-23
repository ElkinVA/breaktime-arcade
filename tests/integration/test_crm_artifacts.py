"""Staff-only CRM downloads for packages, runtime bundles and reports."""

from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile
from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StaffRole, User
from apps.catalog.models import Game, GameVersion, Genre
from apps.crm.services import version_downloads as downloads
from apps.crm.services.step_up import SESSION_KEY
from apps.i18n.models import Language
from apps.pipeline.services.artifacts import ensure_root, package_path, runtime_path

PASSWORD = "correct horse battery staple"
PACKAGE_BYTES = b"PK\x03\x04original-package-bytes"
RUNTIME_FILES = {
    "index.html": b"<!doctype html><html><body>game</body></html>",
    "js/ba-sdk.js": b"/* official SDK 1.1.0 */",
    "js/game.js": b"var started = true;",
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _genre() -> Genre:
    genre, _created = Genre.objects.get_or_create(code="artifacts")
    return genre


def _language() -> Language:
    language, _created = Language.objects.get_or_create(code="en", defaults={"name": "English"})
    return language


def _game(*, technical_id: str = "artifact_game", host_label: str = "artifact-game.test") -> Game:
    return Game.objects.create(
        technical_id=technical_id,
        host_label=host_label,
        slug=f"slug-{technical_id}",
        primary_genre=_genre(),
        status=Game.STATUS_PUBLISHED,
        published_at=timezone.now(),
    )


def _version(
    game: Game,
    *,
    semver: str = "1.0.0",
    package_hash: str | None = None,
    runtime_hash: str | None = None,
) -> GameVersion:
    return GameVersion.objects.create(
        game=game,
        semver=semver,
        package_hash=package_hash or hashlib.sha256(PACKAGE_BYTES).hexdigest(),
        runtime_hash=runtime_hash or _sha(f"runtime-{semver}"),
        sdk_version="1.1.0",
        size_bytes=len(PACKAGE_BYTES),
        manifest={},
        supported_languages=["en"],
        validation_report={
            "ok": False,
            "summary": {"blocker": 1, "warning": 1, "info": 0},
            "diagnostics": [
                {
                    "code": "V_LOCALE_PARITY",
                    "severity": "blocker",
                    "file": "locales/de.json",
                    "message": "Отсутствуют ключи: resume",
                    "hint": "Добавьте ключи во все локали.",
                }
            ],
        },
        import_report={
            "created": True,
            "status": "created",
            "updated_fields": ["name"],
            "conflicts": [
                {"scope": "game", "field": "name", "resolution": "keep"},
            ],
        },
        e2e_report={
            "passed": True,
            "kind": "static",
            "checks": [{"name": "entry", "passed": True, "detail": "index.html"}],
            "notes": ["Playwright не выполнялся."],
        },
    )


def _store_package(version: GameVersion) -> None:
    root = ensure_root(Path(settings.ZIP_PIPELINE_STORAGE_ROOT))
    target = package_path(root, version.package_hash)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(PACKAGE_BYTES)


def _store_runtime(version: GameVersion) -> Path:
    root = ensure_root(Path(settings.ZIP_PUBLIC_RUNTIME_ROOT))
    directory = runtime_path(root, version.runtime_hash, version.game.host_label)
    for relative, payload in RUNTIME_FILES.items():
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    return directory


def _staff(role: str = StaffRole.OWNER) -> User:
    staff = User.objects.create_user(
        login=f"artifact-staff-{User.objects.count()}",
        password=PASSWORD,
        is_staff=True,
        crm_role=role,
    )
    User.objects.filter(pk=staff.pk).update(totp_confirmed_at=timezone.now())
    staff.refresh_from_db()
    return staff


def _staff_client(*, role: str = StaffRole.OWNER, elevated: bool = False) -> Client:
    staff = _staff(role)
    client = Client()
    client.force_login(staff)
    session = client.session
    session["ba_2fa_verified"] = True
    if elevated:
        session[SESSION_KEY] = timezone.now().isoformat()
    session.save()
    return client


def _assert_attachment(response, filename: str) -> None:
    assert response["Content-Disposition"] == f'attachment; filename="{filename}"'
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Cache-Control"] == "private, no-store"


@pytest.fixture
def artifact_env(tmp_path, settings):
    settings.ZIP_PIPELINE_STORAGE_ROOT = str(tmp_path / "store")
    settings.ZIP_PUBLIC_RUNTIME_ROOT = str(tmp_path / "runtime")
    settings.ZIP_ARTIFACTS_ROOT = str(tmp_path / "artifacts")
    _genre()
    _language()
    return tmp_path


@pytest.mark.django_db
def test_package_and_runtime_downloads_are_byte_exact(artifact_env: Path) -> None:
    game = _game()
    version = _version(game)
    _store_package(version)
    _store_runtime(version)
    client = _staff_client(elevated=True)

    package_response = client.get(reverse("crm:version_package", args=[game.id, version.id]))
    assert package_response.status_code == 200
    assert b"".join(package_response.streaming_content) == PACKAGE_BYTES
    assert package_response["Content-Type"] == "application/zip"
    _assert_attachment(package_response, f"game-{game.id}-version-{version.id}-package.zip")

    runtime_response = client.get(reverse("crm:version_runtime", args=[game.id, version.id]))
    assert runtime_response.status_code == 200
    assert runtime_response["Content-Type"] == "application/zip"
    _assert_attachment(runtime_response, f"game-{game.id}-version-{version.id}-runtime.zip")
    runtime_bytes = b"".join(runtime_response.streaming_content)
    with zipfile.ZipFile(io.BytesIO(runtime_bytes)) as archive:
        assert sorted(archive.namelist()) == sorted(RUNTIME_FILES)
        for relative, payload in RUNTIME_FILES.items():
            assert archive.read(relative) == payload


@pytest.mark.django_db
def test_package_response_streams_in_bounded_chunks(
    artifact_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The package is hashed and served chunk by chunk, never as one buffer."""
    game = _game(technical_id="chunked_package", host_label="chunked-package.test")
    payload = b"PK\x03\x04" + b"payload" * (downloads.ARTIFACT_CHUNK_SIZE // 2)
    version = _version(game, package_hash=hashlib.sha256(payload).hexdigest())
    root = ensure_root(Path(settings.ZIP_PIPELINE_STORAGE_ROOT))
    target = package_path(root, version.package_hash)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)

    read_sizes: list[int] = []
    real_read = downloads.os.read

    def tracking_read(fd: int, size: int) -> bytes:
        read_sizes.append(size)
        return real_read(fd, size)

    monkeypatch.setattr(downloads.os, "read", tracking_read)

    response = downloads.package_response(version)
    assert response.streaming
    assert read_sizes
    assert max(read_sizes) <= downloads.ARTIFACT_CHUNK_SIZE
    assert len(read_sizes) >= 3  # the hash pass never asks for the whole file
    assert response.block_size == downloads.ARTIFACT_CHUNK_SIZE
    assert b"".join(response.streaming_content) == payload
    response.close()


@pytest.mark.django_db
def test_package_in_place_mutation_during_read_fails_the_hash(
    artifact_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second handle rewriting the inode while it is read must fail the request.

    The descriptor is read once, so bytes mutated after the first chunk are
    hashed as mutated and can never match ``version.package_hash``.
    """
    game = _game(technical_id="inplace_during", host_label="inplace-during.test")
    payload = b"PK\x03\x04" + b"A" * (2 * downloads.ARTIFACT_CHUNK_SIZE)
    version = _version(game, package_hash=hashlib.sha256(payload).hexdigest())
    root = ensure_root(Path(settings.ZIP_PIPELINE_STORAGE_ROOT))
    target = package_path(root, version.package_hash)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)

    real_read = downloads.os.read
    mutated = False

    def mutating_read(fd: int, size: int) -> bytes:
        nonlocal mutated
        chunk = real_read(fd, size)
        if chunk and not mutated:
            mutated = True
            # A second descriptor on the same inode rewrites the whole file.
            with target.open("r+b") as attacker:
                attacker.write(b"X" * len(payload))
        return chunk

    monkeypatch.setattr(downloads.os, "read", mutating_read)

    with pytest.raises(downloads.ArtifactUnavailable):
        downloads.package_response(version)
    assert mutated


@pytest.mark.django_db
def test_package_body_is_the_hash_verified_bytes_after_in_place_mutation(
    artifact_env: Path,
) -> None:
    """Mutating the store after open must not change the served body.

    The response streams the spool produced during the hashing pass, so a
    hardlink writing the same inode after ``package_response`` returns leaves
    the body byte-identical to the bytes that matched ``package_hash``.
    """
    game = _game(technical_id="inplace_after", host_label="inplace-after.test")
    version = _version(game)
    _store_package(version)
    root = ensure_root(Path(settings.ZIP_PIPELINE_STORAGE_ROOT))
    target = package_path(root, version.package_hash)

    response = downloads.package_response(version)
    hardlink = artifact_env / "package-hardlink.zip"
    os.link(target, hardlink)
    with hardlink.open("r+b") as attacker:
        attacker.write(b"X" * len(PACKAGE_BYTES))
    assert target.read_bytes() != PACKAGE_BYTES

    body = b"".join(response.streaming_content)
    assert body == PACKAGE_BYTES
    assert hashlib.sha256(body).hexdigest() == version.package_hash
    response.close()


@pytest.mark.django_db
def test_corrupted_package_is_rejected_before_any_body_is_served(
    artifact_env: Path,
) -> None:
    """A mismatched SHA-256 must never turn into a partial download."""
    game = _game(technical_id="corrupted_package", host_label="corrupted-package.test")
    version = _version(game)
    _store_package(version)
    root = ensure_root(Path(settings.ZIP_PIPELINE_STORAGE_ROOT))
    target = package_path(root, version.package_hash)
    target.write_bytes(b"corrupted package bytes")

    with pytest.raises(downloads.ArtifactUnavailable):
        downloads.package_response(version)

    client = _staff_client(elevated=True)
    response = client.get(reverse("crm:version_package", args=[game.id, version.id]))
    assert response.status_code == 404
    assert b"corrupted package bytes" not in response.content


@pytest.mark.django_db
def test_runtime_response_spools_the_archive_to_a_temp_file(
    artifact_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The runtime ZIP is built on disk, not in an in-memory io.BytesIO."""
    game = _game(technical_id="runtime_spool", host_label="runtime-spool.test")
    version = _version(game)
    _store_runtime(version)

    created: list[io.BufferedIOBase] = []
    real_temporary_file = downloads.tempfile.TemporaryFile

    def tracking_temporary_file(*args: object, **kwargs: object) -> io.BufferedIOBase:
        handle = real_temporary_file(*args, **kwargs)
        created.append(handle)
        return handle

    monkeypatch.setattr(downloads.tempfile, "TemporaryFile", tracking_temporary_file)

    response = downloads.runtime_response(version)
    assert created
    assert response.file_to_stream is created[0]
    assert not isinstance(response.file_to_stream, io.BytesIO)
    assert response.file_to_stream.fileno() >= 0

    body = b"".join(response.streaming_content)
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        assert sorted(archive.namelist()) == sorted(RUNTIME_FILES)
        for relative, payload in RUNTIME_FILES.items():
            assert archive.read(relative) == payload
    response.close()
    assert created[0].closed


@pytest.mark.django_db
def test_version_reports_render_json_and_markdown(artifact_env: Path) -> None:
    game = _game(technical_id="report_game", host_label="report-game.test")
    version = _version(game)
    client = _staff_client()

    json_response = client.get(
        reverse("crm:version_report", args=[game.id, version.id, "validation", "json"])
    )
    assert json_response.status_code == 200
    assert json.loads(json_response.content) == version.validation_report
    assert json_response["Content-Type"] == "application/json; charset=utf-8"
    _assert_attachment(json_response, f"game-{game.id}-version-{version.id}-validation.json")

    markdown_response = client.get(
        reverse("crm:version_report", args=[game.id, version.id, "validation", "md"])
    )
    assert markdown_response.status_code == 200
    assert markdown_response["Content-Type"] == "text/markdown; charset=utf-8"
    markdown = markdown_response.content.decode()
    assert "# Отчёт валидации пакета" in markdown
    assert "V_LOCALE_PARITY" in markdown
    assert "locales/de.json" in markdown

    autotest_response = client.get(
        reverse("crm:version_report", args=[game.id, version.id, "autotest", "md"])
    )
    assert autotest_response.status_code == 200
    assert "# Отчёт автотеста версии" in autotest_response.content.decode()

    import_response = client.get(
        reverse("crm:version_report", args=[game.id, version.id, "import", "json"])
    )
    assert import_response.status_code == 200
    assert json.loads(import_response.content) == version.import_report

    unknown_kind = client.get(
        reverse("crm:version_report", args=[game.id, version.id, "unknown", "json"])
    )
    assert unknown_kind.status_code == 404

    bad_format = client.get(
        reverse("crm:version_report", args=[game.id, version.id, "validation", "csv"])
    )
    assert bad_format.status_code == 400


@pytest.mark.django_db
def test_missing_artifacts_return_404(artifact_env: Path) -> None:
    game = _game(technical_id="missing_game", host_label="missing-game.test")
    version = _version(game)
    client = _staff_client(elevated=True)

    assert client.get(reverse("crm:version_package", args=[game.id, version.id])).status_code == 404
    assert client.get(reverse("crm:version_runtime", args=[game.id, version.id])).status_code == 404

    other_game = _game(technical_id="other_game", host_label="other-game.test")
    assert (
        client.get(reverse("crm:version_package", args=[other_game.id, version.id])).status_code
        == 404
    )


@pytest.mark.django_db
def test_artifacts_require_staff_role_and_step_up(artifact_env: Path) -> None:
    game = _game(technical_id="guarded_artifacts", host_label="guarded-artifacts.test")
    version = _version(game)
    _store_package(version)
    _store_runtime(version)
    package_url = reverse("crm:version_package", args=[game.id, version.id])
    runtime_url = reverse("crm:version_runtime", args=[game.id, version.id])
    report_url = reverse("crm:version_report", args=[game.id, version.id, "validation", "json"])

    anonymous = Client()
    for url in (package_url, runtime_url, report_url):
        response = anonymous.get(url)
        assert response.status_code == 302
        assert response.url == reverse("crm:login")

    non_staff_user = User.objects.create_user(login="artifacts-plain", password=PASSWORD)
    non_staff = Client()
    non_staff.force_login(non_staff_user)
    for url in (package_url, runtime_url, report_url):
        response = non_staff.get(url)
        assert response.status_code == 302
        assert response.url == reverse("crm:login")

    observer = _staff_client(role=StaffRole.OBSERVER)
    assert observer.get(report_url).status_code == 403

    not_elevated = _staff_client()
    for url in (package_url, runtime_url):
        response = not_elevated.get(url)
        assert response.status_code == 302
        assert response.url.startswith(reverse("crm:step_up"))
    # Reports only require the staff role; no step-up is expected.
    assert not_elevated.get(report_url).status_code == 200


@pytest.mark.django_db
def test_traversal_and_symlinks_cannot_escape_artifact_roots(artifact_env: Path) -> None:
    client = _staff_client(elevated=True)

    bad_package_game = _game(technical_id="bad_package", host_label="bad-package.test")
    bad_package = _version(
        bad_package_game,
        package_hash="../../../../etc/passwd",
    )
    response = client.get(
        reverse("crm:version_package", args=[bad_package_game.id, bad_package.id])
    )
    assert response.status_code == 404

    outside_game = _game(technical_id="outside_game", host_label="..")
    outside_version = _version(outside_game, semver="9.9.9")
    outside = artifact_env / outside_version.runtime_hash
    outside.mkdir(parents=True)
    (outside / "index.html").write_bytes(b"outside the runtime root")
    response = client.get(
        reverse("crm:version_runtime", args=[outside_game.id, outside_version.id])
    )
    assert response.status_code == 404

    symlink_game = _game(technical_id="symlink_game", host_label="symlink-game.test")
    symlink_version = _version(symlink_game, semver="8.8.8")
    root = ensure_root(Path(settings.ZIP_PUBLIC_RUNTIME_ROOT))
    target = runtime_path(root, symlink_version.runtime_hash, symlink_game.host_label)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(artifact_env, target_is_directory=True)
    response = client.get(
        reverse("crm:version_runtime", args=[symlink_game.id, symlink_version.id])
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_package_symlink_swap_between_check_and_read_is_rejected(
    artifact_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A symlink swapped in after resolution must not be read as the package."""
    game = _game(technical_id="toctou_package_link", host_label="toctou-package-link.test")
    version = _version(game)
    _store_package(version)
    root = ensure_root(Path(settings.ZIP_PIPELINE_STORAGE_ROOT))
    target = package_path(root, version.package_hash)
    secret = artifact_env / "secret.txt"
    secret.write_bytes(b"attacker-controlled")
    real_open = os.open
    swapped = False

    def swapping_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if not swapped and Path(path) == target:
            swapped = True
            target.unlink()
            target.symlink_to(secret)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(downloads.os, "open", swapping_open)

    with pytest.raises(downloads.ArtifactUnavailable):
        downloads.package_response(version)
    assert swapped


@pytest.mark.django_db
def test_package_file_swap_between_check_and_read_is_rejected(
    artifact_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replacing the package with another regular file is caught by fstat."""
    game = _game(technical_id="toctou_package_swap", host_label="toctou-package-swap.test")
    version = _version(game)
    _store_package(version)
    root = ensure_root(Path(settings.ZIP_PIPELINE_STORAGE_ROOT))
    target = package_path(root, version.package_hash)
    replacement = target.with_name(f"{target.stem}-replacement.zip")
    real_open = os.open
    swapped = False

    def swapping_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if not swapped and Path(path) == target:
            swapped = True
            replacement.write_bytes(b"replacement package")
            replacement.replace(target)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(downloads.os, "open", swapping_open)

    with pytest.raises(downloads.ArtifactUnavailable):
        downloads.package_response(version)
    assert swapped


@pytest.mark.django_db
def test_runtime_directory_symlink_swap_between_check_and_read_is_rejected(
    artifact_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A runtime root swapped for a symlink after resolution is rejected."""
    game = _game(technical_id="toctou_runtime_link", host_label="toctou-runtime-link.test")
    version = _version(game)
    directory = _store_runtime(version)
    outside = artifact_env / "outside-runtime"
    outside.mkdir()
    (outside / "index.html").write_bytes(b"outside")
    real_open = os.open
    swapped = False

    def swapping_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if not swapped and Path(path) == directory:
            swapped = True
            directory.rename(directory.with_name(f"{directory.name}-moved"))
            directory.symlink_to(outside, target_is_directory=True)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(downloads.os, "open", swapping_open)

    with pytest.raises(downloads.ArtifactUnavailable):
        downloads.runtime_response(version)
    assert swapped


@pytest.mark.django_db
def test_runtime_tree_internal_symlink_is_rejected(artifact_env: Path) -> None:
    """Symlinks inside the published runtime tree still cannot be served."""
    game = _game(technical_id="toctou_runtime_tree", host_label="toctou-runtime-tree.test")
    version = _version(game)
    directory = _store_runtime(version)
    (directory / "leak.js").symlink_to(artifact_env / "secret.txt")

    with pytest.raises(downloads.ArtifactUnavailable):
        downloads.runtime_response(version)


@pytest.mark.django_db
def test_game_card_links_to_artifact_downloads(artifact_env: Path) -> None:
    game = _game(technical_id="card_links", host_label="card-links.test")
    version = _version(game)
    client = _staff_client()

    response = client.get(reverse("crm:game_detail", args=[game.id]))

    assert response.status_code == 200
    content = response.content.decode()
    assert reverse("crm:version_package", args=[game.id, version.id]) in content
    assert reverse("crm:version_runtime", args=[game.id, version.id]) in content
    assert (
        reverse("crm:version_report", args=[game.id, version.id, "validation", "json"]) in content
    )
