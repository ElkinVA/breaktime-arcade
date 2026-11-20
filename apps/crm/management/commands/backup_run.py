from __future__ import annotations

import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.crm.services.backup import run_full_backup


class Command(BaseCommand):
    help = "Полный pg_dump + sha256 + ротация + запись BackupRun"

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir", default=os.environ.get("BACKUP_DIR", "/app/var/backups")
        )
        parser.add_argument(
            "--retention-days",
            type=int,
            default=int(os.environ.get("BACKUP_RETENTION_DAYS", "30")),
        )

    def handle(self, *args, **opts):
        run = run_full_backup(Path(opts["output_dir"]), opts["retention_days"])
        if run.status == "success":
            self.stdout.write(
                self.style.SUCCESS(
                    f"OK run={run.id} size={run.size_bytes} sha256={run.sha256[:16]}..."
                )
            )
            return
        raise CommandError(f"Backup failed: {run.error_message}")
