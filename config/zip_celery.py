"""Publisher-only Celery app for the isolated ZIP broker.

The default app consumes `default`/`celery`; the zip-worker consumes `zip`
from `redis-zip`. Web and the default worker publish only the two zip task
types through this app, so a compromised zip-worker cannot reach the default
queue and a default-queue producer cannot silently land on the zip broker.

Celery's settings object gives the legacy `CELERY_BROKER_URL` environment
variable precedence over ``broker=``. Publishers therefore send over an
explicit Kombu connection to the configured ZIP broker.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from kombu import Connection

from celery import Celery

zip_app = Celery(
    "ba-zip-publisher",
    broker=settings.CELERY_ZIP_BROKER_URL,
    set_as_current=False,
)
zip_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    broker_connection_retry_on_startup=True,
)


def send_zip_task(
    name: str,
    *,
    args: tuple[Any, ...] = (),
    queue: str = "zip",
) -> str:
    """Publish one task to the isolated ZIP broker; return its task id."""
    with Connection(settings.CELERY_ZIP_BROKER_URL) as connection:
        result = zip_app.send_task(name, args=args, queue=queue, connection=connection)
    return str(result.id)


__all__ = ["send_zip_task", "zip_app"]
