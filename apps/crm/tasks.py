"""Celery-задачи для бэкапов и мониторинга их свежести (§2.5)."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from apps.crm.services.backup import (
    latest_backup_age_hours,
    run_full_backup,
    run_restore_check,
)
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="crm.backup_full")
def backup_full() -> str:
    """Full backup. R-036: at-least-once; reject_on_worker_lost=False;
    non-idempotent (Phase 2 guard pending)."""
    out = Path(os.environ.get("BACKUP_DIR", "/app/var/backups"))
    run = run_full_backup(out)
    return f"{run.status} run={run.id}"


@shared_task(name="crm.restore_check")
def restore_check() -> str:
    """Restore check. R-036: at-least-once; reject_on_worker_lost=False;
    non-idempotent DROP/CREATE (Phase 2 guard pending)."""
    run = run_restore_check()
    return f"{run.status} run={run.id}"


@shared_task(name="crm.backup_status_alert")
def backup_status_alert() -> dict[str, str | float]:
    """Backup freshness alert. R-036: read-only/idempotent; logs only."""
    age = latest_backup_age_hours()
    if age is None:
        logger.error("backup.status: НЕТ успешных бэкапов")
        return {"status": "no_backup"}
    if age > 25:
        logger.error("backup.status: бэкап старше 25 часов (age=%.1fh)", age)
        return {"status": "stale", "age_hours": age}
    return {"status": "ok", "age_hours": age}
