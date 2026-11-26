"""Live Room lifecycle tasks."""

from __future__ import annotations

import logging
import time

from apps.rooms.services.rooms import cleanup_rooms, expire_rooms
from celery import shared_task

logger = logging.getLogger("apps.rooms")


@shared_task(name="apps.rooms.tasks.expire_rooms")
def expire_rooms_task() -> dict[str, int]:
    started = time.perf_counter()
    expired = expire_rooms()
    cleaned = cleanup_rooms()
    logger.info(
        "room.expire_task",
        extra={
            "event": "room.expire_task",
            "outcome": "completed",
            "expired_count": expired,
            "cleaned_count": cleaned,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    )
    return {"expired": expired, "cleaned": cleaned}
