"""System-wide ZIP storage quota (ARCADE-P4-STORAGE-001)."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.pipeline.services import quota as quota_module
from apps.pipeline.services.quota import (
    RESERVATIONS_FILE,
    StorageQuota,
    StorageQuotaError,
    quota_state_root,
    storage_usage,
)
from apps.pipeline.validation.codes import (
    X_STORAGE_FREE_SPACE,
    X_STORAGE_QUOTA,
)


def _roots(tmp_path: Path) -> tuple[Path, Path, Path]:
    uploads = tmp_path / "uploads"
    artifacts = tmp_path / "artifacts"
    packages = tmp_path / "packages"
    for root in (uploads, artifacts, packages):
        root.mkdir()
    return uploads, artifacts, packages


def _quota(tmp_path: Path, roots: tuple[Path, ...], **kwargs: object) -> StorageQuota:
    options: dict[str, object] = {
        "state_root": tmp_path / "quota-state",
        "max_bytes": 10_000,
        "min_free_bytes": 0,
        "reservation_ttl_seconds": 60,
    }
    options.update(kwargs)
    return StorageQuota(roots, **options)  # type: ignore[arg-type]


def test_usage_covers_uploads_artifacts_and_packages(tmp_path: Path) -> None:
    uploads, artifacts, packages = _roots(tmp_path)
    (uploads / "job" / "source.zip").parent.mkdir()
    (uploads / "job" / "source.zip").write_bytes(b"u" * 100)
    (artifacts / "job" / "result").mkdir(parents=True)
    (artifacts / "job" / "result" / "index.html").write_bytes(b"a" * 200)
    (packages / "hash.zip").write_bytes(b"p" * 300)

    assert storage_usage((uploads, artifacts, packages)) == 600

    quota = _quota(tmp_path, (uploads, artifacts, packages), max_bytes=600)
    with pytest.raises(StorageQuotaError) as error:
        quota.reserve(1)
    assert error.value.code == X_STORAGE_QUOTA


def test_quota_rejection_is_non_destructive(tmp_path: Path) -> None:
    uploads, artifacts, packages = _roots(tmp_path)
    published = artifacts / "published-runtime" / "index.html"
    published.parent.mkdir()
    published.write_bytes(b"published")
    quota = _quota(tmp_path, (uploads, artifacts, packages), max_bytes=10)

    with pytest.raises(StorageQuotaError) as error:
        quota.reserve(100)

    assert error.value.code == X_STORAGE_QUOTA
    assert published.read_bytes() == b"published"
    assert sorted(path.name for path in artifacts.iterdir()) == ["published-runtime"]


def test_concurrent_uploads_never_exceed_quota(tmp_path: Path) -> None:
    uploads, artifacts, packages = _roots(tmp_path)
    quota = _quota(tmp_path, (uploads, artifacts, packages), max_bytes=1_000)

    def attempt(index: int) -> str:
        try:
            reservation = quota.reserve(600)
        except StorageQuotaError as exc:
            return exc.code
        try:
            # Simulate the upload while the reservation is held.
            (uploads / f"job-{index}").write_bytes(b"x" * 600)
        finally:
            quota.release(reservation)
        return "ok"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(attempt, range(2)))

    assert results == [X_STORAGE_QUOTA, "ok"]
    assert storage_usage((uploads,)) <= 1_000


def test_free_space_pressure_is_a_stable_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    uploads, artifacts, packages = _roots(tmp_path)
    quota = _quota(
        tmp_path,
        (uploads, artifacts, packages),
        max_bytes=10_000,
        min_free_bytes=500,
    )
    monkeypatch.setattr(
        quota_module.os,
        "statvfs",
        lambda _path: SimpleNamespace(f_bavail=100, f_frsize=1),
    )

    with pytest.raises(StorageQuotaError) as error:
        quota.reserve(1_000)

    assert error.value.code == X_STORAGE_FREE_SPACE
    assert error.value.free == 100


def test_stale_reservation_expires_after_restart(tmp_path: Path) -> None:
    uploads, artifacts, packages = _roots(tmp_path)
    quota = _quota(
        tmp_path,
        (uploads, artifacts, packages),
        max_bytes=1_000,
        reservation_ttl_seconds=60,
    )
    state = quota.state_root
    state.mkdir(parents=True)
    now = time.time()
    (state / RESERVATIONS_FILE).write_text(
        json.dumps({"old": {"bytes": 900, "created_at": now - 3_600}}),
        encoding="utf-8",
    )

    reservation = quota.reserve(900)
    quota.release(reservation)

    assert quota.usage_bytes() >= 0


def test_release_is_idempotent(tmp_path: Path) -> None:
    uploads, artifacts, packages = _roots(tmp_path)
    quota = _quota(tmp_path, (uploads, artifacts, packages), max_bytes=1_000)
    reservation = quota.reserve(200)
    quota.release(reservation)
    quota.release(reservation)
    second = quota.reserve(900)
    quota.release(second)


def test_assert_within_limit_flags_existing_overflow(tmp_path: Path) -> None:
    uploads, artifacts, packages = _roots(tmp_path)
    (uploads / "big.bin").write_bytes(b"x" * 500)
    quota = _quota(tmp_path, (uploads, artifacts, packages), max_bytes=100)

    with pytest.raises(StorageQuotaError) as error:
        quota.assert_within_limit()
    assert error.value.code == X_STORAGE_QUOTA


def test_state_root_falls_back_to_uploads(tmp_path: Path, settings) -> None:
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    # Direct assignment (not monkeypatch): pytest-django's settings wrapper must
    # restore the original value rather than mark the setting deleted.
    settings.ZIP_QUOTA_STATE_ROOT = None
    settings.ZIP_UPLOADS_ROOT = uploads

    assert quota_state_root() == uploads / ".quota"
