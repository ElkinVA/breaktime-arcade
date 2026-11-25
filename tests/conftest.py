"""Общая тестовая инфраструктура.

``django_db(transaction=True)`` тесты в teardown делают flush всех таблиц.
С ``--reuse-db`` тестовая БД осталась бы без данных data-миграций (языки,
строки интерфейса), и публичные страницы отвечали бы 503. Для transaction-
тестов seed-данные всех i18n data-миграций восстанавливаются перед тестом
и после teardown.

Список seed-модулей собирается из каталога миграций, поэтому новые
*_seed_*.py подхватываются автоматически; ручной список уже один раз
разошёлся с миграциями (ARCADE-TEST-DB-SEED-001).
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

import pytest

_I18N_MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "apps" / "i18n" / "migrations"


def _is_transaction_test(item: pytest.Item | None) -> bool:
    if item is None:
        return False
    marker = item.get_closest_marker("django_db")
    return marker is not None and bool(marker.kwargs.get("transaction"))


def _i18n_seeders() -> list[Callable[[Any, Any], None]]:
    paths = sorted(_I18N_MIGRATIONS_DIR.glob("[0-9]*_seed_*.py"))
    if not paths:
        raise RuntimeError(f"no i18n seed migrations found in {_I18N_MIGRATIONS_DIR}")
    seeders: list[Callable[[Any, Any], None]] = []
    for path in paths:
        module = importlib.import_module(f"apps.i18n.migrations.{path.stem}")
        seed = getattr(module, "seed_languages", None) or getattr(module, "seed_strings", None)
        if seed is None:
            raise RuntimeError(f"{path.name} defines neither seed_languages nor seed_strings")
        seeders.append(seed)
    return seeders


def _reseed_i18n() -> None:
    from django.apps import apps as django_apps
    from django.db import connection

    try:
        for seed in _i18n_seeders():
            seed(django_apps, None)
    finally:
        connection.close()


@pytest.fixture(autouse=True)
def _ensure_seed_data(request: pytest.FixtureRequest, django_db_blocker) -> Generator[None]:
    if _is_transaction_test(request.node):
        with django_db_blocker.unblock():
            _reseed_i18n()
    yield


@pytest.fixture(autouse=True)
def _isolated_zip_quota_state(tmp_path: Path, settings: Any) -> None:
    """Keep quota locks/state out of the compose volume.

    In the dev-lite web container ``ZIP_QUOTA_STATE_ROOT`` points at the shared
    ``zip_quota`` volume owned by the app UID. Tests run as the developer UID,
    so using the production path would reject every extraction with
    ``X_STORAGE_QUOTA_STATE``. A per-test directory keeps the state isolated
    and writable without weakening the production check.
    """
    settings.ZIP_QUOTA_STATE_ROOT = tmp_path / "zip-quota-state"


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
        _reseed_i18n()
