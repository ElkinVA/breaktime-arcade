from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "publish_runtime",
    ROOT / "scripts" / "publish_runtime.py",
)
assert SPEC is not None and SPEC.loader is not None
publish_runtime_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publish_runtime_module)


def test_publish_runtime_injects_origin_and_sdk(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "js").mkdir(parents=True)
    (source / "index.html").write_text("<html><head></head><body></body></html>")
    (source / "js" / "game.js").write_text("// game")
    sdk = tmp_path / "sdk.js"
    sdk.write_text("// sdk")
    target = tmp_path / "target"

    result = publish_runtime_module.publish_runtime(
        source=source,
        target=target,
        portal_origin="https://portal.test:8443",
        sdk=sdk,
    )

    assert result == target
    index = (target / "index.html").read_text()
    assert 'meta name="ba-portal-origin" content="https://portal.test:8443"' in index
    assert (target / "js" / "ba-sdk.js").read_text() == "// sdk"
    assert (target / "js" / "game.js").read_text() == "// game"


def test_publish_runtime_replaces_existing_pin_idempotently(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "index.html").write_text(
        '<html><head><meta name="ba-portal-origin" content="https://old.test"></head></html>'
    )
    sdk = tmp_path / "sdk.js"
    sdk.write_text("// sdk")
    target = tmp_path / "target"

    publish_runtime_module.publish_runtime(
        source=source,
        target=target,
        portal_origin="https://portal.test:8443",
        sdk=sdk,
    )
    publish_runtime_module.publish_runtime(
        source=source,
        target=target,
        portal_origin="https://portal.test:8443",
        sdk=sdk,
    )

    assert (target / "index.html").read_text().count("ba-portal-origin") == 1


def test_publish_runtime_rejects_invalid_origin(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "index.html").write_text("<html><head></head></html>")
    sdk = tmp_path / "sdk.js"
    sdk.write_text("// sdk")
    with pytest.raises(ValueError):
        publish_runtime_module.publish_runtime(
            source=source,
            target=tmp_path / "target",
            portal_origin="javascript:alert(1)",
            sdk=sdk,
        )
