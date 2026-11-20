"""Общая тестовая инфраструктура.

``django_db(transaction=True)`` тесты в teardown делают flush всех таблиц.
С ``--reuse-db`` тестовая БД осталась бы без данных data-миграций (языки,
строки интерфейса), и публичные страницы отвечали бы 503. Для transaction-
тестов seed-данные восстанавливаются перед тестом и после teardown.
"""

from __future__ import annotations

import importlib
from collections.abc import Generator

import pytest


def _is_transaction_test(item: pytest.Item | None) -> bool:
    if item is None:
        return False
    marker = item.get_closest_marker("django_db")
    return marker is not None and bool(marker.kwargs.get("transaction"))


def _reseed_i18n_if_empty() -> None:
    from django.apps import apps as django_apps
    from django.db import connection

    from apps.i18n.models import Language

    try:
        if Language.objects.exists():
            return
        languages = importlib.import_module("apps.i18n.migrations.0002_seed_languages")
        languages.seed_languages(django_apps, None)
        strings = importlib.import_module("apps.i18n.migrations.0003_seed_ui_strings")
        strings.seed_strings(django_apps, None)
    finally:
        connection.close()


@pytest.fixture(autouse=True)
def _ensure_seed_data(request: pytest.FixtureRequest, django_db_blocker) -> Generator[None]:
    if _is_transaction_test(request.node):
        with django_db_blocker.unblock():
            _reseed_i18n_if_empty()
    yield


@pytest.hookimpl(hookwrapper=True, trylast=True)
def pytest_runtest_teardown(
    item: pytest.Item,
    nextitem: pytest.Item | None,
) -> Generator[None]:
    del nextitem
    yield
    if not _is_transaction_test(item):
        return
    from pytest_django.plugin import blocking_manager_key

    blocker = item.config.stash[blocking_manager_key]
    with blocker.unblock():
        _reseed_i18n_if_empty()
