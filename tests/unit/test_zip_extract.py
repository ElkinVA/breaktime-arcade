from __future__ import annotations

import hashlib
import io
import stat
import time
import zipfile
from pathlib import Path
from typing import cast

import pytest

from apps.pipeline.services.unpack import (
    X_CRC_MISMATCH,
    X_DESTINATION_EXISTS,
    X_LIMIT_FILE,
    X_LIMIT_FILES,
    X_LIMIT_TOTAL,
    X_PATH_UNSAFE,
    X_PREFIX_CONFLICT,
    X_PREFLIGHT_REJECTED,
    X_TIMEOUT,
    ExtractionError,
    extract_zip,
)


def _zip(
    entries: dict[str, bytes],
    *,
    compression: int = zipfile.ZIP_DEFLATED,
) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=compression) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _no_staging(parent: Path) -> None:
    assert not list(parent.glob(".ba-extract-*"))


def test_extract_valid_package_with_hashes(tmp_path: Path, monkeypatch) -> None:
    data = _zip({"index.html": b"hello", "js/game.js": b"x" * 100})

    def forbidden(*args, **kwargs):
        raise AssertionError("extract/extractall must not be used")

    monkeypatch.setattr(zipfile.ZipFile, "extract", forbidden)
    monkeypatch.setattr(zipfile.ZipFile, "extractall", forbidden)

    result = extract_zip(data, tmp_path / "pkg")
    assert result.root == (tmp_path / "pkg").resolve()
    assert result.total_bytes == 105
    assert {item.path for item in result.files} == {"index.html", "js/game.js"}
    assert (result.root / "js/game.js").read_bytes() == b"x" * 100
    assert result.files[1].sha256 == hashlib.sha256(b"x" * 100).hexdigest()
    _no_staging(tmp_path)


def test_preflight_rejection_creates_nothing(tmp_path: Path) -> None:
    data = _zip({"../evil.js": b"x"})
    with pytest.raises(ExtractionError) as error:
        extract_zip(data, tmp_path / "pkg")
    assert error.value.code == X_PREFLIGHT_REJECTED
    assert error.value.report is not None
    assert not (tmp_path / "pkg").exists()
    _no_staging(tmp_path)


def test_symlink_is_rejected_by_preflight(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo("link.js")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "index.html")
    with pytest.raises(ExtractionError) as error:
        extract_zip(buffer.getvalue(), tmp_path / "pkg")
    assert error.value.code == X_PREFLIGHT_REJECTED
    assert not (tmp_path / "pkg").exists()
    _no_staging(tmp_path)


def test_per_file_and_total_limits(tmp_path: Path) -> None:
    with pytest.raises(ExtractionError) as error:
        extract_zip(
            _zip({"js/game.js": b"x" * 2048}, compression=zipfile.ZIP_STORED),
            tmp_path / "file-limit",
            max_file_bytes=1024,
        )
    assert error.value.code == X_LIMIT_FILE

    with pytest.raises(ExtractionError) as error:
        extract_zip(
            _zip(
                {"js/a.js": b"x" * 800, "js/b.js": b"y" * 800},
                compression=zipfile.ZIP_STORED,
            ),
            tmp_path / "total-limit",
            max_total_bytes=1000,
        )
    assert error.value.code == X_LIMIT_TOTAL
    assert not (tmp_path / "file-limit").exists()
    assert not (tmp_path / "total-limit").exists()
    _no_staging(tmp_path)


def test_file_count_limit(tmp_path: Path) -> None:
    with pytest.raises(ExtractionError) as error:
        extract_zip(
            _zip({"js/a.js": b"a", "js/b.js": b"b"}),
            tmp_path / "pkg",
            max_files=1,
        )
    assert error.value.code == X_LIMIT_FILES
    assert not (tmp_path / "pkg").exists()
    _no_staging(tmp_path)


def test_crc_mismatch_is_rejected(tmp_path: Path) -> None:
    data = bytearray(_zip({"js/game.js": b"payload"}, compression=zipfile.ZIP_STORED))
    offset = data.find(b"payload")
    assert offset >= 0
    data[offset] ^= 0xFF
    with pytest.raises(ExtractionError) as error:
        extract_zip(bytes(data), tmp_path / "pkg")
    assert error.value.code == X_CRC_MISMATCH
    assert not (tmp_path / "pkg").exists()
    _no_staging(tmp_path)


def test_prefix_conflict_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ExtractionError) as error:
        extract_zip(
            _zip({"a.js": b"a", "a.js/b.js": b"b"}),
            tmp_path / "pkg",
        )
    assert error.value.code == X_PREFIX_CONFLICT

    with pytest.raises(ExtractionError) as error:
        extract_zip(
            _zip({"a.js": b"a", "a.js/b/": b""}),
            tmp_path / "pkg-dir",
        )
    assert error.value.code == X_PREFIX_CONFLICT
    assert not (tmp_path / "pkg").exists()
    assert not (tmp_path / "pkg-dir").exists()
    _no_staging(tmp_path)


def test_existing_destination_is_not_overwritten(tmp_path: Path) -> None:
    destination = tmp_path / "pkg"
    destination.mkdir()
    (destination / "keep.txt").write_text("keep")
    with pytest.raises(ExtractionError) as error:
        extract_zip(_zip({"index.html": b"x"}), destination)
    assert error.value.code == X_DESTINATION_EXISTS
    assert (destination / "keep.txt").read_text() == "keep"
    _no_staging(tmp_path)


def test_deadline_and_cleanup(tmp_path: Path) -> None:
    with pytest.raises(ExtractionError) as error:
        extract_zip(
            _zip({"index.html": b"x"}),
            tmp_path / "pkg",
            deadline=time.monotonic() - 1,
        )
    assert error.value.code == X_TIMEOUT
    assert not (tmp_path / "pkg").exists()
    _no_staging(tmp_path)


def test_deep_path_and_directory_entries_are_limited(tmp_path: Path) -> None:
    deep = "/".join(["a"] * 65) + "/f.js"
    with pytest.raises(ExtractionError) as error:
        extract_zip(_zip({deep: b"x"}), tmp_path / "deep")
    assert error.value.code == X_PATH_UNSAFE
    assert not (tmp_path / "deep").exists()

    with pytest.raises(ExtractionError) as error:
        extract_zip(
            _zip({"a/": b"", "b/": b""}),
            tmp_path / "dirs",
            max_files=1,
        )
    assert error.value.code == X_LIMIT_FILES
    assert not (tmp_path / "dirs").exists()
    _no_staging(tmp_path)


def test_mutable_input_is_copied(tmp_path: Path) -> None:
    data = bytearray(_zip({"index.html": b"hello"}))
    result = extract_zip(cast(bytes, data), tmp_path / "pkg")
    assert (result.root / "index.html").read_bytes() == b"hello"
