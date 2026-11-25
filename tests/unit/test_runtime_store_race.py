"""Concurrent runtime publication must adopt an identical bundle (§5.5)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from apps.pipeline.services.artifacts import (
    ArtifactError,
    runtime_hash_for,
    store_runtime,
    tree_hashes,
)


def _bundle(root: Path, body: str) -> Path:
    bundle = root / "bundle"
    bundle.mkdir(parents=True)
    (bundle / "index.html").write_text(body, encoding="utf-8")
    return bundle


def test_store_runtime_reuses_identical_concurrent_bundle(tmp_path: Path) -> None:
    staging = _bundle(tmp_path, "<html>one</html>")
    runtime_hash = runtime_hash_for(tree_hashes(staging))
    target = store_runtime(tmp_path / "runtime", runtime_hash, staging)

    second_staging = _bundle(tmp_path / "second", "<html>one</html>")
    again = store_runtime(tmp_path / "runtime", runtime_hash, second_staging)

    assert again == target
    assert (target / "index.html").read_text(encoding="utf-8") == "<html>one</html>"


def test_store_runtime_adopts_bundle_published_during_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = _bundle(tmp_path, "<html>one</html>")
    runtime_hash = runtime_hash_for(tree_hashes(staging))
    real_rename = Path.rename

    def racing_rename(self: Path, target: Path) -> None:
        if self.name.startswith(".ba-runtime-"):
            shutil.copytree(self, target)
            raise FileExistsError("concurrent publisher won")
        real_rename(self, target)

    monkeypatch.setattr(Path, "rename", racing_rename)

    target = store_runtime(tmp_path / "runtime", runtime_hash, staging)

    assert (target / "index.html").read_text(encoding="utf-8") == "<html>one</html>"
    assert runtime_hash_for(tree_hashes(target)) == runtime_hash


def test_store_runtime_rejects_conflicting_existing_bundle(tmp_path: Path) -> None:
    staging = _bundle(tmp_path, "<html>one</html>")
    runtime_hash = runtime_hash_for(tree_hashes(staging))
    target = store_runtime(tmp_path / "runtime", runtime_hash, staging)
    (target / "index.html").write_text("<html>tampered</html>", encoding="utf-8")

    other = _bundle(tmp_path / "other", "<html>one</html>")

    with pytest.raises(ArtifactError) as exc:
        store_runtime(tmp_path / "runtime", runtime_hash, other)
    assert exc.value.code == "X_ARTIFACT_CONFLICT"
