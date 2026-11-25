"""Orphan runtime bundles are removed only after TTL (§5.5)."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from django.conf import settings

from apps.catalog.models import Game, GameVersion, Genre
from apps.pipeline.services.runtime_cleanup import cleanup_orphan_runtimes

TTL = 24 * 60 * 60
REFERENCED = "a" * 64
OLD_ORPHAN = "b" * 64
FRESH_ORPHAN = "c" * 64
LINK_ORPHAN = "d" * 64
FLAT_ORPHAN = "e" * 64


def _game() -> Game:
    genre = Genre.objects.create(code="orphan_genre")
    return Game.objects.create(
        technical_id="orphan_game",
        host_label="orphan-game.games.test",
        slug="orphan-game",
        primary_genre=genre,
    )


def _version(game: Game, runtime_hash: str) -> GameVersion:
    return GameVersion.objects.create(
        game=game,
        semver="1.0.0",
        package_hash="1" * 64,
        runtime_hash=runtime_hash,
        sdk_version="1.1.0",
        size_bytes=1000,
        manifest={},
        supported_languages=["en"],
    )


def _bundle(root: Path, runtime_hash: str, *, mtime: float | None = None) -> Path:
    path = root / "host.games.test" / runtime_hash
    path.mkdir(parents=True)
    (path / "index.html").write_text("<html></html>", encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


@pytest.mark.django_db
def test_cleanup_removes_only_unreferenced_expired_bundles(tmp_path: Path) -> None:
    now = time.time()
    _version(_game(), REFERENCED)
    referenced = _bundle(tmp_path, REFERENCED, mtime=now - TTL - 10)
    old = _bundle(tmp_path, OLD_ORPHAN, mtime=now - TTL - 10)
    fresh = _bundle(tmp_path, FRESH_ORPHAN, mtime=now)
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "host.games.test" / LINK_ORPHAN).symlink_to(outside)
    flat = tmp_path / FLAT_ORPHAN
    flat.mkdir()
    os.utime(flat, (now - TTL - 10, now - TTL - 10))

    result = cleanup_orphan_runtimes(runtime_root=tmp_path, ttl_seconds=TTL, now=now)

    assert result == {"removed": 2, "skipped": 2}
    assert referenced.is_dir()
    assert not old.exists()
    assert fresh.is_dir()
    assert (tmp_path / "host.games.test" / LINK_ORPHAN).is_symlink()
    assert not flat.exists()
    assert cleanup_orphan_runtimes(runtime_root=tmp_path, ttl_seconds=TTL, now=now)["removed"] == 0


def test_cleanup_is_scheduled_and_registered() -> None:
    entry = settings.CELERY_BEAT_SCHEDULE["pipeline-cleanup-orphan-runtimes"]
    assert entry["task"] == "apps.pipeline.tasks.cleanup_orphan_runtimes"
    from apps.pipeline.tasks import cleanup_orphan_runtimes_task

    assert cleanup_orphan_runtimes_task.name == "apps.pipeline.tasks.cleanup_orphan_runtimes"


@pytest.mark.django_db
def test_cleanup_handles_missing_root(tmp_path: Path) -> None:
    assert cleanup_orphan_runtimes(runtime_root=tmp_path / "missing") == {
        "removed": 0,
        "skipped": 0,
    }
    assert not (tmp_path / "missing").exists()


def test_cleanup_refuses_symlink_root(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)

    assert cleanup_orphan_runtimes(runtime_root=link) == {"removed": 0, "skipped": 0}
    assert real.is_dir()
