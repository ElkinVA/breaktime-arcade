"""Dev-only game seed command guard."""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings


@override_settings(DEBUG=False)
def test_seed_dev_game_refuses_outside_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    with pytest.raises(CommandError, match="dev-only"):
        call_command("seed_dev_game", "whatever.zip")
