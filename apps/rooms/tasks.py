"""Live Room lifecycle tasks."""

from __future__ import annotations

from apps.rooms.services.rooms import cleanup_rooms, expire_rooms
from celery import shared_task


@shared_task(name="apps.rooms.tasks.expire_rooms")
def expire_rooms_task() -> dict[str, int]:
    return {"expired": expire_rooms(), "cleaned": cleanup_rooms()}
