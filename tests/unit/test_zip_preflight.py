from __future__ import annotations

import io
import stat
import zipfile

from apps.pipeline.validation.codes import (
    V_ARCHIVE_BAD,
    V_ARCHIVE_EMPTY,
    V_ARCHIVE_ENCRYPTED,
    V_ARCHIVE_HEADER_MISMATCH,
    V_ARCHIVE_TOO_LARGE,
    V_ARCHIVE_TOO_MANY_FILES,
    V_ARCHIVE_UNCOMPRESSED_TOO_LARGE,
    V_COMPRESSION_RATIO,
    V_EXT_UNSUPPORTED,
    V_FILE_TOO_LARGE,
    V_METHOD_UNSUPPORTED,
    V_PATH_ABSOLUTE,
    V_PATH_BACKSLASH,
    V_PATH_COLLISION,
    V_PATH_DUPLICATE,
    V_PATH_INVALID,
    V_PATH_TRAVERSAL,
    V_SERVICE_FILE,
    V_SPECIAL_ENTRY,
    V_SYMLINK,
)
from apps.pipeline.validation.structure import preflight_zip


def _zip(entries: dict[str, bytes], *, compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=compression) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _codes(data: bytes) -> set[str]:
    return {item.code for item in preflight_zip(data).diagnostics}


def test_unsupported_compression_method_is_blocked() -> None:
    data = _zip({"index.html": b"x"}, compression=zipfile.ZIP_BZIP2)
    assert V_METHOD_UNSUPPORTED in _codes(data)


def test_valid_package_passes_without_extraction(monkeypatch) -> None:
    data = _zip(
        {
            "index.html": b"<!doctype html>",
            "css/style.css": b"body{}",
            "js/game.js": b"console.log(1)",
            "assets/cover.png": b"png",
            "locales/en.json": b"{}",
        }
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("preflight must not extract")

    monkeypatch.setattr(zipfile.ZipFile, "extract", forbidden)
    monkeypatch.setattr(zipfile.ZipFile, "extractall", forbidden)
    report = preflight_zip(data)
    assert report.ok
    assert report.file_count == 5
    assert len(report.package_hash) == 64


def test_archive_level_rejections() -> None:
    assert V_ARCHIVE_BAD in _codes(b"not a zip")
    assert V_ARCHIVE_EMPTY in _codes(_zip({}))
    assert V_ARCHIVE_TOO_LARGE in _codes(b"x" * (25 * 1024 * 1024 + 1))
    many = _zip({f"js/f{index}.js": b"x" for index in range(2001)})
    assert V_ARCHIVE_TOO_MANY_FILES in _codes(many)


def test_path_attacks_are_blocked() -> None:
    assert V_PATH_TRAVERSAL in _codes(_zip({"../evil.js": b"x"}))
    assert V_PATH_ABSOLUTE in _codes(_zip({"/etc/passwd": b"x"}))
    assert V_PATH_BACKSLASH in _codes(_zip({"js\\evil.js": b"x"}))
    assert V_PATH_INVALID in _codes(_zip({"js/\x01evil.js": b"x"}))
    assert V_PATH_INVALID in _codes(_zip({"js/‮evil.js": b"x"}))


def _symlink_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo("link.js")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "index.html")
    return buffer.getvalue()


def test_symlink_and_special_entries_are_blocked() -> None:
    assert V_SYMLINK in _codes(_symlink_zip())


def test_duplicate_and_case_collision_are_blocked() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("js/game.js", b"a")
        archive.writestr("js/game.js", b"b")
    assert V_PATH_DUPLICATE in _codes(buffer.getvalue())
    assert V_PATH_COLLISION in _codes(_zip({"js/Game.js": b"a", "js/game.js": b"b"}))
    assert V_PATH_DUPLICATE in _codes(_zip({"js//game.js": b"a", "js/game.js": b"b"}))
    assert V_PATH_DUPLICATE in _codes(_zip({"a/": b"", "a": b"x"}))
    assert V_PATH_INVALID in _codes(_zip({"./js/game.js": b"a"}))
    assert V_SERVICE_FILE in _codes(_zip({".git/": b"", "node_modules/": b""}))


def test_extensions_and_service_files_are_blocked() -> None:
    assert V_EXT_UNSUPPORTED in _codes(_zip({"js/run.exe": b"x"}))
    assert V_EXT_UNSUPPORTED in _codes(_zip({"js/README": b"x"}))
    for name in (".git/config", ".DS_Store", "js/app.js.map", "node_modules/x.js"):
        assert V_SERVICE_FILE in _codes(_zip({name: b"x"})), name


def test_encrypted_entry_is_blocked() -> None:
    data = bytearray(_zip({"js/game.js": b"x"}))
    data[6] |= 0x1  # local header general-purpose flag
    central = data.find(b"PK\x01\x02")
    assert central >= 0
    data[central + 8] |= 0x1  # central directory general-purpose flag
    assert V_ARCHIVE_ENCRYPTED in _codes(bytes(data))


def test_size_and_compression_limits() -> None:
    large_file = _zip({"assets/big.bin": b"\0" * (20 * 1024 * 1024 + 1)})
    codes = _codes(large_file)
    assert V_FILE_TOO_LARGE in codes
    assert V_COMPRESSION_RATIO in codes

    six_big = _zip({f"assets/f{index}.wasm": b"\0" * (19 * 1024 * 1024) for index in range(6)})
    assert V_ARCHIVE_UNCOMPRESSED_TOO_LARGE in _codes(six_big)


def test_directory_with_mode_and_nfc_duplicate() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo("js/")
        info.external_attr = (stat.S_IFDIR | 0o755) << 16
        archive.writestr(info, b"")
        archive.writestr("js/game.js", b"x")
    assert preflight_zip(buffer.getvalue()).ok

    composed = "js/café.js"
    decomposed = "js/café.js"
    assert V_PATH_DUPLICATE in _codes(_zip({composed: b"a", decomposed: b"b"}))


def test_directory_mode_without_slash_is_blocked() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo("payload.exe")
        info.external_attr = (stat.S_IFDIR | 0o755) << 16
        archive.writestr(info, b"MZ")
    codes = _codes(buffer.getvalue())
    assert V_SPECIAL_ENTRY in codes
    assert V_EXT_UNSUPPORTED in codes

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo("app.js.map")
        info.external_attr = (stat.S_IFDIR | 0o755) << 16
        archive.writestr(info, b"map")
        info = zipfile.ZipInfo(".git")
        info.external_attr = (stat.S_IFDIR | 0o755) << 16
        archive.writestr(info, b"")
    codes = _codes(buffer.getvalue())
    assert V_SPECIAL_ENTRY in codes
    assert V_SERVICE_FILE in codes


def test_unicode_normalization_and_windows_paths_are_blocked() -> None:
    assert V_PATH_INVALID in _codes(_zip({"ｊｓ／ｅｖｉｌ.js": b"x"}))
    assert V_PATH_INVALID in _codes(_zip({"js/CON.js": b"x"}))
    assert V_PATH_INVALID in _codes(_zip({"js/trailing. ": b"x"}))


def test_local_central_size_mismatch_is_blocked() -> None:
    data = bytearray(_zip({"js/game.js": b"payload"}))
    # Local header: sig(4) ver(2) flags(2) method(2) time(2) date(2) crc(4)
    # comp(4) uncomp(4) name_len(2) extra_len(2) -> uncompressed at +22.
    data[22:26] = (1).to_bytes(4, "little")
    assert V_ARCHIVE_HEADER_MISMATCH in _codes(bytes(data))


def test_data_descriptor_does_not_false_positive() -> None:
    class _Unseekable(io.BytesIO):
        def seek(self, *args, **kwargs):
            raise OSError("unseekable")

    buffer = _Unseekable()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("js/game.js", b"payload" * 100)
    report = preflight_zip(buffer.getvalue())
    assert report.ok
    assert V_ARCHIVE_HEADER_MISMATCH not in {item.code for item in report.diagnostics}


def test_zip64_marker_and_bad_header_offset() -> None:
    zip64 = bytearray(_zip({"js/game.js": b"x"}))
    zip64[18:26] = b"\xff\xff\xff\xff" * 2
    assert V_ARCHIVE_HEADER_MISMATCH not in _codes(bytes(zip64))

    bad_offset = bytearray(_zip({"js/game.js": b"x"}))
    central = bad_offset.find(b"PK\x01\x02")
    assert central >= 0
    bad_offset[central + 42 : central + 46] = (0xFFFFFF).to_bytes(4, "little")
    assert V_ARCHIVE_HEADER_MISMATCH in _codes(bytes(bad_offset))


def test_uppercase_service_files_are_blocked() -> None:
    assert V_SERVICE_FILE in _codes(_zip({"JS/APP.MAP": b"x"}))
    assert V_SERVICE_FILE in _codes(_zip({".DS_STORE": b"x"}))


def test_diagnostics_are_structured() -> None:
    report = preflight_zip(_zip({"../evil.js": b"x"}))
    payload = report.as_dict()
    assert payload["ok"] is False
    diagnostic = payload["diagnostics"][0]
    assert set(diagnostic) >= {"code", "severity", "message"}
    assert diagnostic["severity"] == "blocker"
