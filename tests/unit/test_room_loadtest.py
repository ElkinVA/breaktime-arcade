"""Guardrails for the dev-only Live Room load diagnostic."""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings


def test_room_loadtest_is_refused_when_debug_is_off() -> None:
    with override_settings(DEBUG=False), pytest.raises(CommandError, match="dev-only"):
        call_command("room_loadtest")
