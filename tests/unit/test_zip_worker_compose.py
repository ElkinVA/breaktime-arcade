from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILES = ("compose.yml", "compose.dev-lite.yml", "compose.staging.yml")

# The secret-free sandbox runner copies only application/test roots, so these
# infrastructure files are absent there. CI/`make test` run from the repository
# root and must execute every assertion below.
pytestmark = pytest.mark.skipif(
    not all((ROOT / name).is_file() for name in COMPOSE_FILES),
    reason="compose files are not present in the sandbox copy",
)


def _load(name: str) -> dict[str, Any]:
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))


def test_zip_worker_isolation() -> None:
    data = _load("compose.yml")
    service = data["services"]["zip-worker"]

    assert service["networks"] == ["zipnet"]
    assert data["networks"]["zipnet"] == {"internal": True}
    assert "zipnet" in data["services"]["redis-broker"]["networks"]
    assert service["read_only"] is True
    assert service["pids_limit"] == 64
    assert service["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert service["mem_limit"] == "512m"
    assert service["cpus"] == "1.0"
    assert "/tmp:rw,size=64m,mode=1777" in service["tmpfs"]
    assert "zip" in service["command"]
    assert "-Q" in service["command"]
    assert "--pool=prefork" in service["command"]
    assert service["entrypoint"] == ["/app/infra/scripts/entrypoint-zip-worker.sh"]
    assert service["volumes"] == [
        "zip_uploads:/var/ba/zip/uploads:ro",
        "zip_artifacts:/var/ba/zip/artifacts",
        "zip_quota:/var/ba/zip/quota",
    ]
    assert service["depends_on"] == {
        "zip-volume-init": {"condition": "service_completed_successfully"},
        "redis-broker": {"condition": "service_healthy"},
    }


def test_regular_worker_does_not_consume_zip() -> None:
    service = _load("compose.yml")["services"]["worker"]
    command = service["command"]

    assert "-Q" in command
    assert "default,celery" in command
    assert "zip" not in command
    # The default worker, not the read-only zip-worker, owns upload cleanup;
    # its inherited media/app_var/static mounts must survive the override.
    assert service["volumes"] == [
        "static_data:/app/staticfiles",
        "media_data:/app/media",
        "app_var:/app/var",
        "runtime_data:/app/runtime",
        "zip_uploads:/var/ba/zip/uploads",
    ]
    assert service["environment"]["ZIP_PUBLIC_RUNTIME_ROOT"] == "/app/runtime"


def test_web_volume_access() -> None:
    data = _load("compose.yml")
    service = data["services"]["web"]

    assert "zip_uploads:/var/ba/zip/uploads" in service["volumes"]
    assert "zip_artifacts:/var/ba/zip/artifacts:ro" in service["volumes"]
    assert "zip_quota:/var/ba/zip/quota" in service["volumes"]
    assert "runtime_data:/app/runtime" in service["volumes"]
    assert service["environment"]["ZIP_PUBLIC_RUNTIME_ROOT"] == "/app/runtime"
    assert "runtime_data:/app/runtime:ro" in data["services"]["nginx"]["volumes"]


def test_zip_volume_init_hands_roots_to_shared_uid() -> None:
    data = _load("compose.yml")
    service = data["services"]["zip-volume-init"]
    command = " ".join(service["command"])

    assert service["user"] == "0:0"
    assert "10001:10001" in command
    assert "chmod 700" in command
    assert "/var/ba/zip/quota" in command
    assert service["cap_drop"] == ["ALL"]
    assert set(service["cap_add"]) == {"CHOWN", "DAC_OVERRIDE", "FOWNER"}
    assert service["network_mode"] == "none"
    assert service["volumes"] == [
        "zip_uploads:/var/ba/zip/uploads",
        "zip_artifacts:/var/ba/zip/artifacts",
        "zip_quota:/var/ba/zip/quota",
        "runtime_data:/app/runtime",
    ]
    assert data["services"]["web"]["depends_on"]["zip-volume-init"] == {
        "condition": "service_completed_successfully"
    }


def test_system_wide_quota_is_shared_and_configured() -> None:
    data = _load("compose.yml")
    web_env = data["services"]["web"]["environment"]
    zip_env = data["services"]["zip-worker"]["environment"]

    for environment in (web_env, zip_env):
        # Raw YAML keeps the compose interpolation expression; the default
        # must point at the shared volume and be non-zero.
        assert "/var/ba/zip/quota" in environment["ZIP_QUOTA_STATE_ROOT"]
        assert "2147483648" in environment["ZIP_STORAGE_QUOTA_BYTES"]
        assert "157286400" in environment["ZIP_STORAGE_MIN_FREE_BYTES"]
        assert "3600" in environment["ZIP_QUOTA_RESERVATION_TTL_SECONDS"]
    # The quota state must be a real shared volume, not a path inside the
    # read-only zip_uploads mount.
    assert "zip_quota" in data["volumes"]
    assert "zip_quota:/var/ba/zip/quota" in data["services"]["web"]["volumes"]
    assert "zip_quota:/var/ba/zip/quota" in data["services"]["zip-worker"]["volumes"]
    # Published runtimes are never included in the quota roots/mounts.
    assert "zip_quota:/app/runtime" not in data["services"]["web"]["volumes"]


def test_dev_lite_and_staging_overlays() -> None:
    dev = _load("compose.dev-lite.yml")
    assert dev["services"]["zip-worker"]["environment"]["DJANGO_SETTINGS_MODULE"] == (
        "config.settings.dev"
    )
    assert "default,celery" in dev["services"]["worker"]["command"]

    staging = _load("compose.staging.yml")
    staging_zip = staging["services"]["zip-worker"]
    assert staging_zip["env_file"] == [".env.staging"]
    # The staging overlay must not weaken base isolation.
    for key in ("networks", "security_opt", "cap_drop", "read_only", "tmpfs", "volumes", "user"):
        assert key not in staging_zip
