from __future__ import annotations

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_no_missing_migrations() -> None:
    """Fail when a model change lacks a migration (makemigrations --check)."""
    call_command("makemigrations", "--check", "--dry-run", verbosity=0)
