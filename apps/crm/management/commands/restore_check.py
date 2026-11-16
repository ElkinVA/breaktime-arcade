from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.crm.services.backup import run_restore_check


class Command(BaseCommand):
    help = "Восстановить последний бэкап в ba_restore_check и проверить"

    def add_arguments(self, parser):
        parser.add_argument("--file", default=None, help="Путь к .dump (по умолчанию последний)")

    def handle(self, *args, **opts):
        path = Path(opts["file"]) if opts["file"] else None
        run = run_restore_check(path)
        if run.status == "success":
            self.stdout.write(self.style.SUCCESS(f"OK verified_at={run.verified_at}"))
            return
        raise CommandError(f"Restore check failed: {run.error_message}")
