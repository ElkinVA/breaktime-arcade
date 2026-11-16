from __future__ import annotations

import uuid

import pytest
from django.test import Client, override_settings

from apps.core.ids import uuid7


def test_healthz(anon_client: Client) -> None:
    response = anon_client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_security_headers(anon_client: Client) -> None:
    response = anon_client.get("/healthz")
    assert "nonce-" in response["Content-Security-Policy"]
    assert response["X-Request-ID"]
    assert response["X-Frame-Options"] == "DENY"


def test_uuid7_monotonic_and_version() -> None:
    values = [uuid7() for _ in range(1000)]
    assert all(isinstance(v, uuid.UUID) and v.version == 7 for v in values)
    assert values == sorted(values)
    assert len(set(values)) == len(values)


@pytest.mark.django_db
@override_settings(BA_BACKUP_CHECK_ENABLED=False)
def test_readyz(anon_client: Client) -> None:
    response = anon_client.get("/readyz")
    assert response.status_code in {200, 503}
    assert set(response.json()["checks"]) == {"db", "cache", "broker"}
