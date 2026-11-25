from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILES = ("compose.yml", "compose.dev-lite.yml", "compose.staging.yml")

ZIP_WORKER_ENV = {
    "DJANGO_SETTINGS_MODULE": "${DJANGO_SETTINGS_MODULE:-config.settings.prod}",
    "CELERY_BROKER_URL": "${CELERY_BROKER_URL:-redis://redis-broker:6379/2}",
    "RUN_MIGRATIONS": "0",
    "RUN_COLLECTSTATIC": "0",
    "ZIP_QUOTA_STATE_ROOT": "${ZIP_QUOTA_STATE_ROOT:-/var/ba/zip/quota}",
    "ZIP_STORAGE_QUOTA_BYTES": "${ZIP_STORAGE_QUOTA_BYTES:-2147483648}",
    "ZIP_STORAGE_MIN_FREE_BYTES": "${ZIP_STORAGE_MIN_FREE_BYTES:-157286400}",
    "ZIP_QUOTA_RESERVATION_TTL_SECONDS": "${ZIP_QUOTA_RESERVATION_TTL_SECONDS:-3600}",
    "ZIP_DISK_RESERVE_BYTES": "${ZIP_DISK_RESERVE_BYTES:-157286400}",
    "ZIP_JOB_DEADLINE_SECONDS": "${ZIP_JOB_DEADLINE_SECONDS:-50}",
    "ZIP_JOB_MAX_BYTES": "${ZIP_JOB_MAX_BYTES:-125829120}",
    "ZIP_STAGING_TTL_SECONDS": "${ZIP_STAGING_TTL_SECONDS:-3600}",
    "ZIP_COMPLETED_TTL_SECONDS": "${ZIP_COMPLETED_TTL_SECONDS:-86400}",
}
SECRET_NAME = re.compile(
    r"(?i)(password|secret|token|passphrase|dsn|hmac|signing|credential|access[_-]?key|api[_-]?key)"
)
SECRET_ENV_NAMES = {
    "ANON_SIGNING_KEY",
    "BACKUP_PASSPHRASE",
    "BACKUP_TARGET_URI",
    "DATABASE_URL",
    "DJANGO_SECRET_KEY",
    "EMAIL_PASSWORD",
    "NICKNAME_HMAC_KEY",
    "POSTGRES_PASSWORD",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
    "SENTRY_DSN",
    "SESSION_BINDING_KEY",
    "TOTP_ISSUER",
}
INTERPOLATION = re.compile(r"^\$\{[A-Z_]+:-(?P<default>.*)\}$")

# The secret-free sandbox runner copies only application/test roots, so these
# infrastructure files are absent there. CI/`make test` run from the repository
# root and must execute every assertion below.
pytestmark = pytest.mark.skipif(
    not all((ROOT / name).is_file() for name in COMPOSE_FILES),
    reason="compose files are not present in the sandbox copy",
)


def _load(name: str) -> dict[str, Any]:
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))


def _default(value: str) -> str:
    match = INTERPOLATION.fullmatch(value)
    assert match is not None, value
    return match.group("default")


def _int_product(expression: str) -> int:
    result = 1
    for factor in expression.split("*"):
        result *= int(factor.strip())
    return result


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


def test_zip_worker_has_no_env_file_and_exact_allowlist() -> None:
    service = _load("compose.yml")["services"]["zip-worker"]

    assert "env_file" not in service
    assert service["environment"] == ZIP_WORKER_ENV


def test_zip_worker_environment_has_no_secret_names() -> None:
    environment = _load("compose.yml")["services"]["zip-worker"]["environment"]

    assert not set(environment) & SECRET_ENV_NAMES
    assert not [name for name in environment if SECRET_NAME.search(name)]


def test_zip_worker_env_defaults_match_settings() -> None:
    source = (ROOT / "config/settings/base.py").read_text(encoding="utf-8")
    environment = _load("compose.yml")["services"]["zip-worker"]["environment"]

    for name, value in ZIP_WORKER_ENV.items():
        if name in {"RUN_MIGRATIONS", "RUN_COLLECTSTATIC", "ZIP_QUOTA_STATE_ROOT"}:
            continue
        if name == "DJANGO_SETTINGS_MODULE":
            assert _default(value) == "config.settings.prod"
            continue
        if name == "CELERY_BROKER_URL":
            assert _default(value) == "redis://redis-broker:6379/2"
            assert '"redis://redis-broker:6379/2"' in source
            continue
        match = re.search(rf'env_int\("{name}", ([^)\n]+)\)', source)
        assert match is not None, name
        expression = match.group(1).strip()
        if expression == "ZIP_DISK_RESERVE_BYTES":
            assert _default(value) == _default(environment["ZIP_DISK_RESERVE_BYTES"])
        else:
            assert int(_default(value)) == _int_product(expression)


def test_zip_quota_environment_matches_web_exactly() -> None:
    data = _load("compose.yml")
    web = data["services"]["web"]["environment"]
    zip_worker = data["services"]["zip-worker"]["environment"]

    for name in (
        "ZIP_QUOTA_STATE_ROOT",
        "ZIP_STORAGE_QUOTA_BYTES",
        "ZIP_STORAGE_MIN_FREE_BYTES",
        "ZIP_QUOTA_RESERVATION_TTL_SECONDS",
    ):
        assert zip_worker[name] == web[name]


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
    dev_zip = dev["services"]["zip-worker"]
    assert dev_zip["environment"]["DJANGO_SETTINGS_MODULE"] == "config.settings.dev"
    assert "env_file" not in dev_zip
    assert "default,celery" in dev["services"]["worker"]["command"]

    staging = _load("compose.staging.yml")
    staging_zip = staging["services"]["zip-worker"]
    assert "env_file" not in staging_zip
    assert staging_zip["environment"]["DJANGO_SETTINGS_MODULE"] == "config.settings.staging"
    # The staging overlay must not weaken base isolation or widen the env.
    for key in ("networks", "security_opt", "cap_drop", "read_only", "tmpfs", "volumes", "user"):
        assert key not in staging_zip
    assert set(staging_zip["environment"]) == {"DJANGO_SETTINGS_MODULE"}
