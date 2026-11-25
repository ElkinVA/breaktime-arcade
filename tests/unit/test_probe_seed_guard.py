"""The dev-only probe seeder must not run against production settings."""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_probe_seed_refuses_outside_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    with pytest.raises(CommandError, match="dev-only"):
        call_command("probe_seed")
