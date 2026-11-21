"""Structured Celery delivery events (R-036 Phase 1, no behavior change).

The handlers only log task name/id, queue, redelivery flag, retry count and
exception *type*; task arguments, results and exception messages are never
logged, so secrets cannot leak through this channel.

``apps.core.celery`` is a dedicated fd-2 structured-events channel: it does
not propagate to the regular ``apps`` console handler, because Django
``dictConfig``/Celery replace or clear that handler in the worker consumer.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

from celery.signals import (
    task_failure,
    task_received,
    task_retry,
    worker_process_shutdown,
    worker_shutdown,
)

from apps.core.logging import JsonFormatter


class _FdStderrHandler(logging.Handler):
    """Write to fd 2 directly: Celery replaces ``sys.stderr`` in workers."""

    _ba_observability = True

    def emit(self, record: logging.LogRecord) -> None:
        try:
            data = memoryview((self.format(record) + "\n").encode("utf-8"))
            while data:
                written = os.write(2, data)
                if written <= 0:
                    return
                data = data[written:]
        except OSError:
            self.handleError(record)


logger = logging.getLogger("apps.core.celery")
_handler_lock = threading.Lock()


def _ensure_handler() -> None:
    """Re-attach the fd handler after Django/Celery logging reconfiguration."""
    with _handler_lock:
        handlers = getattr(logger, "handlers", None)
        if not isinstance(handlers, list):
            return
        if any(getattr(handler, "_ba_observability", False) for handler in handlers):
            return
        handler = _FdStderrHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.propagate = False


def _task_name(sender: Any, request: Any = None) -> str | None:
    for value in (
        getattr(request, "task", None),
        getattr(request, "name", None),
        getattr(sender, "name", None),
    ):
        if isinstance(value, str) and value:
            return value
    return None


def _exception_type(value: Any) -> str | None:
    if isinstance(value, BaseException):
        return type(value).__name__
    return None


@task_received.connect(dispatch_uid="ba.celery.task_received")
def on_task_received(sender: Any = None, request: Any = None, **_kwargs: Any) -> None:
    _ensure_handler()
    delivery = getattr(request, "delivery_info", None) or {}
    logger.info(
        "celery.task.received",
        extra={
            "event": "celery.task.received",
            "task_id": getattr(request, "id", None),
            "task_name": _task_name(sender, request),
            "queue": delivery.get("routing_key"),
            "redelivered": bool(delivery.get("redelivered")),
            "retries": getattr(request, "retries", 0),
        },
    )


@task_failure.connect(dispatch_uid="ba.celery.task_failure")
def on_task_failure(
    sender: Any = None,
    task_id: str | None = None,
    exception: Any = None,
    **_kwargs: Any,
) -> None:
    _ensure_handler()
    logger.warning(
        "celery.task.failure",
        extra={
            "event": "celery.task.failure",
            "task_id": task_id,
            "task_name": _task_name(sender),
            "exception_type": _exception_type(exception),
        },
    )


@task_retry.connect(dispatch_uid="ba.celery.task_retry")
def on_task_retry(
    sender: Any = None,
    request: Any = None,
    reason: Any = None,
    **_kwargs: Any,
) -> None:
    _ensure_handler()
    logger.warning(
        "celery.task.retry",
        extra={
            "event": "celery.task.retry",
            "task_id": getattr(request, "id", None),
            "task_name": _task_name(sender, request),
            "retries": getattr(request, "retries", 0),
            "exception_type": _exception_type(reason),
        },
    )


@worker_process_shutdown.connect(dispatch_uid="ba.celery.worker_process_shutdown")
def on_worker_process_shutdown(
    sender: Any = None,
    pid: int | None = None,
    exitcode: int | None = None,
    **_kwargs: Any,
) -> None:
    _ensure_handler()
    worker = sender if isinstance(sender, str) else getattr(sender, "hostname", None)
    logger.warning(
        "celery.worker.process_shutdown",
        extra={
            "event": "celery.worker.process_shutdown",
            "worker": worker,
            "worker_pid": pid,
            "exitcode": exitcode,
        },
    )


@worker_shutdown.connect(dispatch_uid="ba.celery.worker_shutdown")
def on_worker_shutdown(sender: Any = None, **_kwargs: Any) -> None:
    _ensure_handler()
    logger.info(
        "celery.worker.shutdown",
        extra={
            "event": "celery.worker.shutdown",
            "worker": getattr(sender, "hostname", None),
        },
    )
