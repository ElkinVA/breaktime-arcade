from __future__ import annotations

import pytest
from django.test import Client


@pytest.fixture
def anon_client() -> Client:
    return Client()
