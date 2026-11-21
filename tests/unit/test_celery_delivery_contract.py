from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from apps.crm.tasks import backup_full, backup_status_alert, restore_check
from apps.pipeline.tasks import cleanup_zip_staging, extract_zip_task


def test_delivery_contract_matrix() -> None:
    from apps.accounts.tasks import anonymize_due_accounts, cleanup_expired_account_records
    from apps.catalog.tasks import refresh_catalog_search_vectors
    from config.celery import app

    side_effect = (
        backup_full,
        restore_check,
        backup_status_alert,
        cleanup_expired_account_records,
        anonymize_due_accounts,
        refresh_catalog_search_vectors,
    )
    for task in side_effect:
        assert task.acks_late is True
        assert task.reject_on_worker_lost in (None, False)
        assert task.acks_on_failure_or_timeout is True

    for task in (extract_zip_task, cleanup_zip_staging):
        assert task.acks_late is True
        assert task.reject_on_worker_lost is True
        assert task.acks_on_failure_or_timeout is True

    assert app.conf.task_acks_late is True
    assert app.conf.task_reject_on_worker_lost in (None, False)
    assert app.conf.task_acks_on_failure_or_timeout is True
    assert app.conf.broker_transport_options.get("visibility_timeout", 3600) == 3600


def test_redelivery_and_failure_signals(monkeypatch) -> None:
    from apps.core import celery_observability as obs

    logger = Mock()
    monkeypatch.setattr(obs, "logger", logger)

    obs.on_task_received(
        sender=None,
        request=SimpleNamespace(
            id="task-1",
            task="crm.backup_full",
            delivery_info={"routing_key": "celery", "redelivered": True},
            retries=1,
        ),
    )
    extra = logger.info.call_args.kwargs["extra"]
    assert extra == {
        "event": "celery.task.received",
        "task_id": "task-1",
        "task_name": "crm.backup_full",
        "queue": "celery",
        "redelivered": True,
        "retries": 1,
    }

    obs.on_task_failure(
        sender=SimpleNamespace(name="crm.backup_full"),
        task_id="task-1",
        exception=ValueError("secret-value-must-not-be-logged"),
    )
    failure_extra = logger.warning.call_args.kwargs["extra"]
    assert failure_extra["exception_type"] == "ValueError"
    assert "secret-value-must-not-be-logged" not in str(logger.warning.call_args)

    obs.on_task_retry(
        sender=SimpleNamespace(name="crm.backup_full"),
        request=SimpleNamespace(id="task-1", retries=2),
        reason=TimeoutError("slow"),
    )
    retry_extra = logger.warning.call_args.kwargs["extra"]
    assert retry_extra["retries"] == 2
    assert retry_extra["exception_type"] == "TimeoutError"

    obs.on_worker_process_shutdown(sender="child@host", pid=42, exitcode=-9)
    shutdown_extra = logger.warning.call_args.kwargs["extra"]
    assert shutdown_extra["worker"] == "child@host"
    assert shutdown_extra["worker_pid"] == 42
    assert shutdown_extra["exitcode"] == -9

    obs.on_worker_shutdown(sender=SimpleNamespace(hostname="celery@host"))
    assert logger.info.call_args.kwargs["extra"]["worker"] == "celery@host"


def test_task_name_prefers_request_and_ignores_non_string_sender_name(monkeypatch) -> None:
    from apps.core import celery_observability as obs

    logger = Mock()
    monkeypatch.setattr(obs, "logger", logger)

    obs.on_task_received(
        sender=SimpleNamespace(name=backup_status_alert),
        request=SimpleNamespace(
            id="task-1",
            task="crm.backup_status_alert",
            delivery_info={"routing_key": "celery", "redelivered": False},
            retries=0,
        ),
    )
    assert logger.info.call_args.kwargs["extra"]["task_name"] == "crm.backup_status_alert"


def test_logging_formatter_includes_delivery_fields() -> None:
    import json
    import logging

    from apps.core.logging import JsonFormatter

    record = logging.LogRecord(
        "apps.core.celery",
        logging.INFO,
        __file__,
        1,
        "celery.task.received",
        (),
        None,
    )
    record.event = "celery.task.received"
    record.task_name = "crm.backup_full"
    record.redelivered = True
    record.retries = 1
    record.queue = "celery"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["task_name"] == "crm.backup_full"
    assert payload["redelivered"] is True
    assert payload["retries"] == 1
    assert payload["queue"] == "celery"


def test_handlers_do_not_log_task_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.core import celery_observability as obs

    logger = Mock()
    monkeypatch.setattr(obs, "logger", logger)

    obs.on_task_received(
        sender=SimpleNamespace(name="crm.backup_full"),
        request=SimpleNamespace(
            id="task-1",
            args=("secret-token",),
            kwargs={"password": "secret"},
            delivery_info={},
            retries=0,
        ),
    )
    assert "secret-token" not in str(logger.info.call_args)
    assert "password" not in str(logger.info.call_args)
