from __future__ import annotations

import pytest
from django.test import Client


@pytest.fixture
def anon_client() -> Client:
    return Client()


@pytest.fixture
def inline_zip_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate the isolated ``zip`` queue consumer inside the test process.

    Production code never extracts in the web process; tests explicitly swap
    the enqueue callable for the same ``run_extraction`` service that the
    isolated worker runs.
    """
    from apps.pipeline.services import extraction
    from apps.pipeline.services.worker import run_extraction

    def _run_inline(job_id: str) -> str:
        run_extraction(job_id)
        return f"inline-{job_id}"

    monkeypatch.setattr(extraction, "enqueue_extraction", _run_inline)
