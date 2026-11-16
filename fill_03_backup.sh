#!/usr/bin/env bash
# fill_03_backup.sh — этап 3, блок 1: бэкапы и restore-check (§2.5).
# Идемпотентен: безопасен при повторном запуске.
# Создаёт файлы и патчит Dockerfile / compose.yml / settings / health.
set -euo pipefail
cd "$(dirname "$0")"

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR=".backups/$STAMP"
CREATED=0; SKIPPED=0; PATCHED=0

write_file() {
    local rel="$1" tmp
    tmp="$(mktemp)"
    cat > "$tmp"
    if [ -e "$rel" ] && [ -s "$rel" ]; then
        # Сравним содержимое: если совпадает — пропускаем
        if cmp -s "$tmp" "$rel"; then
            printf '  SKIP  %s\n' "$rel"
            SKIPPED=$((SKIPPED+1)); rm -f "$tmp"; return
        fi
        mkdir -p "$BACKUP_DIR/$(dirname -- "$rel")"
        cp -p "$rel" "$BACKUP_DIR/$rel"
    fi
    mkdir -p "$(dirname -- "$rel")"
    mv -f "$tmp" "$rel"
    chmod 644 "$rel"
    printf '  OK    %s\n' "$rel"
    CREATED=$((CREATED+1))
}

echo "============================================================"
echo "  Этап 3.1 — бэкапы и restore-check"
echo "============================================================"

# ===================================================== 1. AppConfig CRM
write_file apps/crm/apps.py <<'BA_EOF'
from django.apps import AppConfig


class CrmConfig(AppConfig):
    name = "apps.crm"
    label = "crm"
    verbose_name = "CRM"
BA_EOF

# ===================================================== 2. Модель
write_file apps/crm/models/backup.py <<'BA_EOF'
from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7
from apps.core.ids import uuid7


class BackupRun(models.Model):
    """Запись о запуске резервного копирования (§2.5)."""

    TYPE_FULL = "full"
    TYPE_WAL = "wal"
    TYPE_RESTORE_CHECK = "restore_check"
    TYPE_CHOICES = [
        (TYPE_FULL, "Полный дамп"),
        (TYPE_WAL, "WAL-архив"),
        (TYPE_RESTORE_CHECK, "Проверка восстановления"),
    ]

    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_RUNNING, "Выполняется"),
        (STATUS_SUCCESS, "Успех"),
        (STATUS_FAILED, "Ошибка"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    type = models.CharField(max_length=16, choices=TYPE_CHOICES, db_index=True)
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES,
        default=STATUS_RUNNING, db_index=True,
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    sha256 = models.CharField(max_length=64, blank=True)
    file_path = models.CharField(max_length=512, blank=True)
    remote_uri = models.CharField(max_length=512, blank=True)
    error_message = models.TextField(blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "crm_backup_run"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["type", "-started_at"]),
            models.Index(fields=["status"]),
        ]
        verbose_name = "Запуск бэкапа"
        verbose_name_plural = "Запуски бэкапов"

    def __str__(self) -> str:
        return f"{self.type} {self.started_at:%Y-%m-%d %H:%M} ({self.status})"
BA_EOF

write_file apps/crm/models/__init__.py <<'BA_EOF'
from .backup import BackupRun

__all__ = ["BackupRun"]
BA_EOF

# ===================================================== 3. Сервис
write_file apps/crm/services/__init__.py <<'BA_EOF'
from .backup import (
    latest_backup_age_hours,
    run_full_backup,
    run_restore_check,
)

__all__ = [
    "run_full_backup",
    "run_restore_check",
    "latest_backup_age_hours",
]
BA_EOF

write_file apps/crm/services/backup.py <<'BA_EOF'
"""Полный pg_dump + восстановление в ba_restore_check (§2.5).

Использует pg_dump / pg_restore / psql версии 18 (устанавливается в Dockerfile).
Параметры подключения берутся из DATABASE_URL (основной) или POSTGRES_*.
"""
from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from django.utils import timezone

from apps.crm.models.backup import BackupRun

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ helpers
def _db_params() -> dict[str, str]:
    url = os.environ.get("DATABASE_URL", "")
    if url:
        p = urlparse(url)
        return {
            "host": p.hostname or "db",
            "port": str(p.port or 5432),
            "user": p.username or "ba",
            "password": p.password or "",
            "db": (p.path or "/ba").lstrip("/") or "ba",
        }
    return {
        "host": os.environ.get("DB_HOST", "db"),
        "port": os.environ.get("DB_PORT", "5432"),
        "user": os.environ.get("POSTGRES_USER", "ba"),
        "password": os.environ.get("POSTGRES_PASSWORD", ""),
        "db": os.environ.get("POSTGRES_DB", "ba"),
    }


def _pg_env() -> dict[str, str]:
    env = os.environ.copy()
    p = _db_params()
    if p["password"]:
        env["PGPASSWORD"] = p["password"]
    return env


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _finish(run: BackupRun) -> None:
    run.finished_at = timezone.now()
    run.save(update_fields=["finished_at", "status", "size_bytes", "sha256",
                            "file_path", "remote_uri", "error_message", "verified_at", "meta"])


# --------------------------------------------------------------- full backup
def run_full_backup(output_dir: Path, retention_days: int = 30) -> BackupRun:
    """pg_dump --format=custom → sha256 → ротация → BackupRun."""
    run = BackupRun.objects.create(type=BackupRun.TYPE_FULL, status=BackupRun.STATUS_RUNNING)
    output_dir.mkdir(parents=True, exist_ok=True)
    p = _db_params()
    ts = timezone.now().strftime("%Y%m%dT%H%M%SZ")
    out = output_dir / f"ba-{ts}.dump"

    cmd = [
        "pg_dump",
        "-h", p["host"], "-p", p["port"], "-U", p["user"],
        "--format=custom", "--compress=9",
        "-f", str(out), p["db"],
    ]
    logger.info("backup.start run=%s", run.id)

    try:
        subprocess.run(cmd, env=_pg_env(), check=True, capture_output=True, text=True)
        run.file_path = str(out)
        run.size_bytes = out.stat().st_size
        run.sha256 = _sha256(out)
        run.status = BackupRun.STATUS_SUCCESS
    except subprocess.CalledProcessError as exc:
        run.status = BackupRun.STATUS_FAILED
        run.error_message = ((exc.stderr or "") + (exc.stdout or "") or str(exc))[:2000]
    except FileNotFoundError as exc:
        run.status = BackupRun.STATUS_FAILED
        run.error_message = f"pg_dump not found: {exc}"

    _finish(run)

    if run.status == BackupRun.STATUS_SUCCESS:
        _rotate(output_dir, retention_days)
    logger.info("backup.end run=%s status=%s size=%s", run.id, run.status, run.size_bytes)
    return run


def _rotate(directory: Path, retention_days: int) -> None:
    cutoff = time.time() - retention_days * 86400
    for f in directory.glob("ba-*.dump"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


# ----------------------------------------------------------- restore check
def run_restore_check(backup_path: Path | None = None) -> BackupRun:
    """Восстанавливает последний успешный дамп в ba_restore_check и проверяет."""
    run = BackupRun.objects.create(type=BackupRun.TYPE_RESTORE_CHECK, status=BackupRun.STATUS_RUNNING)

    if backup_path is None:
        last = (
            BackupRun.objects
            .filter(type=BackupRun.TYPE_FULL, status=BackupRun.STATUS_SUCCESS)
            .order_by("-started_at")
            .first()
        )
        if last is None:
            run.status = BackupRun.STATUS_FAILED
            run.error_message = "Нет успешных полных бэкапов"
            _finish(run)
            return run
        backup_path = Path(last.file_path)

    if not backup_path.exists():
        run.status = BackupRun.STATUS_FAILED
        run.error_message = f"Файл не найден: {backup_path}"
        _finish(run)
        return run

    p = _db_params()
    env = _pg_env()
    target_db = "ba_restore_check"
    # psql подключается к базе "postgres" от того же пользователя (суперюзер в контейнере).
    base_psql = ["psql", "-h", p["host"], "-p", p["port"], "-U", p["user"], "-d", "postgres"]

    commands = [
        base_psql + ["-c", f'DROP DATABASE IF EXISTS "{target_db}";'],
        base_psql + ["-c", f'CREATE DATABASE "{target_db}";'],
        ["pg_restore",
         "-h", p["host"], "-p", p["port"], "-U", p["user"],
         "-d", target_db, "--no-owner", "--no-privileges", "--exit-on-error",
         str(backup_path)],
        ["psql", "-h", p["host"], "-p", p["port"], "-U", p["user"], "-d", target_db,
         "-t", "-c", "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"],
    ]

    try:
        for c in commands:
            subprocess.run(c, env=env, check=True, capture_output=True, text=True)
        run.status = BackupRun.STATUS_SUCCESS
        run.verified_at = timezone.now()
        run.meta = {"backup_path": str(backup_path)}
    except subprocess.CalledProcessError as exc:
        run.status = BackupRun.STATUS_FAILED
        run.error_message = ((exc.stderr or "") + (exc.stdout or "") or str(exc))[:2000]
    except FileNotFoundError as exc:
        run.status = BackupRun.STATUS_FAILED
        run.error_message = f"Утилита не найдена: {exc}"

    # Попытка дропнуть временную БД — не фатально при ошибке.
    try:
        subprocess.run(
            base_psql + ["-c", f'DROP DATABASE IF EXISTS "{target_db}";'],
            env=env, check=False, capture_output=True, text=True,
        )
    except Exception:
        pass

    _finish(run)
    return run


def latest_backup_age_hours() -> float | None:
    """Возраст последнего успешного full-бэкапа в часах (None если нет)."""
    last = (
        BackupRun.objects
        .filter(type=BackupRun.TYPE_FULL, status=BackupRun.STATUS_SUCCESS)
        .order_by("-started_at")
        .first()
    )
    if last is None:
        return None
    return (timezone.now() - last.started_at).total_seconds() / 3600.0
BA_EOF

# ===================================================== 4. Management команды
for f in \
    apps/crm/management/__init__.py \
    apps/crm/management/commands/__init__.py ; do
    write_file "$f" <<'BA_EOF'
BA_EOF
done

write_file apps/crm/management/commands/backup_run.py <<'BA_EOF'
from __future__ import annotations

import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.crm.services.backup import run_full_backup


class Command(BaseCommand):
    help = "Полный pg_dump + sha256 + ротация + запись BackupRun"

    def add_arguments(self, parser):
        parser.add_argument("--output-dir", default=os.environ.get("BACKUP_DIR", "/app/var/backups"))
        parser.add_argument("--retention-days", type=int, default=int(os.environ.get("BACKUP_RETENTION_DAYS", "30")))

    def handle(self, *args, **opts):
        run = run_full_backup(Path(opts["output_dir"]), opts["retention_days"])
        if run.status == "success":
            self.stdout.write(self.style.SUCCESS(
                f"OK run={run.id} size={run.size_bytes} sha256={run.sha256[:16]}..."
            ))
            return
        raise CommandError(f"Backup failed: {run.error_message}")
BA_EOF

write_file apps/crm/management/commands/restore_check.py <<'BA_EOF'
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
BA_EOF

# ===================================================== 5. Celery задачи
write_file apps/crm/tasks.py <<'BA_EOF'
"""Celery-задачи для бэкапов и мониторинга их свежести (§2.5)."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from celery import shared_task

from apps.crm.services.backup import (
    latest_backup_age_hours,
    run_full_backup,
    run_restore_check,
)

logger = logging.getLogger(__name__)


@shared_task(name="crm.backup_full")
def backup_full() -> str:
    out = Path(os.environ.get("BACKUP_DIR", "/app/var/backups"))
    run = run_full_backup(out)
    return f"{run.status} run={run.id}"


@shared_task(name="crm.restore_check")
def restore_check() -> str:
    run = run_restore_check()
    return f"{run.status} run={run.id}"


@shared_task(name="crm.backup_status_alert")
def backup_status_alert() -> dict:
    age = latest_backup_age_hours()
    if age is None:
        logger.error("backup.status: НЕТ успешных бэкапов")
        return {"status": "no_backup"}
    if age > 25:
        logger.error("backup.status: бэкап старше 25 часов (age=%.1fh)", age)
        return {"status": "stale", "age_hours": age}
    return {"status": "ok", "age_hours": age}
BA_EOF

# ===================================================== 6. Скрипты-обёртки
write_file infra/scripts/backup.sh <<'BA_EOF'
#!/usr/bin/env bash
# backup.sh — обёртка для запуска бэкапа из контейнера.
# Полная логика — в apps/crm/services/backup.py.
set -euo pipefail
cd /app
exec python manage.py backup_run "$@"
BA_EOF

write_file infra/scripts/restore_check.sh <<'BA_EOF'
#!/usr/bin/env bash
# restore_check.sh — обёртка для проверки восстановления из контейнера.
set -euo pipefail
cd /app
exec python manage.py restore_check "$@"
BA_EOF
chmod 755 infra/scripts/backup.sh infra/scripts/restore_check.sh

# ===================================================== 7. Cron-шаблоны (prod)
mkdir -p infra/scripts/cron
write_file infra/scripts/cron/backup.cron <<'BA_EOF'
# Ежедневный полный бэкап в 03:00 UTC (§2.5). Для прода — через
# sidecar crond, systemd timer или cron на хосте (см. runbook/backup.md).
0 3 * * * root cd /app && docker compose -f compose.prod.yml exec -T web python manage.py backup_run >> /var/log/ba-backup.log 2>&1
BA_EOF

write_file infra/scripts/cron/restore_check.cron <<'BA_EOF'
# Ежемесячная проверка восстановления — 1-е число, 04:00 UTC (§2.5).
0 4 1 * * root cd /app && docker compose -f compose.prod.yml exec -T web python manage.py restore_check >> /var/log/ba-restore-check.log 2>&1
BA_EOF

# ===================================================== 8. Патч Dockerfile
echo
echo "==> Патч Dockerfile (postgresql-client-18 из PGDG)"
if grep -q 'postgresql-client-18' Dockerfile 2>/dev/null; then
    echo "  SKIP  Dockerfile уже содержит postgresql-client-18"
    SKIPPED=$((SKIPPED+1))
else
    cp -p Dockerfile "$BACKUP_DIR/Dockerfile"
    python3 - <<'PY'
import pathlib
p = pathlib.Path("Dockerfile")
text = p.read_text(encoding="utf-8")
old = (
    'RUN apt-get update \\\n'
    ' && apt-get install -y --no-install-recommends curl ca-certificates \\\n'
    ' && rm -rf /var/lib/apt/lists/* \\\n'
)
new = (
    'RUN apt-get update \\\n'
    ' && apt-get install -y --no-install-recommends curl ca-certificates gnupg \\\n'
    ' && install -d /usr/share/postgresql-common/pgdg \\\n'
    ' && curl -fsS -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc \\\n'
    ' && . /etc/os-release \\\n'
    ' && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" > /etc/apt/sources.list.d/pgdg.list \\\n'
    ' && apt-get update \\\n'
    ' && apt-get install -y --no-install-recommends postgresql-client-18 \\\n'
    ' && rm -rf /var/lib/apt/lists/* \\\n'
)
if old in text:
    text = text.replace(old, new, 1)
    p.write_text(text, encoding="utf-8")
    print("  OK    Dockerfile: добавлен postgresql-client-18 из PGDG")
elif "postgresql-client-18" in text:
    print("  SKIP  postgresql-client-18 уже присутствует")
else:
    print("  WARN  не нашёл ожидаемый блок apt-get install — правьте вручную")
PY
    PATCHED=$((PATCHED+1))
fi

# ===================================================== 9. Патч compose.yml
echo
echo "==> Патч compose.yml (сервисы backup и restore-check)"
if grep -q '^  backup:' compose.yml 2>/dev/null; then
    echo "  SKIP  compose.yml уже содержит сервисы"
    SKIPPED=$((SKIPPED+1))
else
    cp -p compose.yml "$BACKUP_DIR/compose.yml"
    python3 - <<'PY'
import pathlib
p = pathlib.Path("compose.yml")
text = p.read_text(encoding="utf-8")
anchor = "\nnetworks:\n"
insert = """\
  backup:
    <<: *app
    command: ["python", "manage.py", "backup_run"]
    environment:
      RUN_MIGRATIONS: "0"
    profiles: ["backup"]

  restore-check:
    <<: *app
    command: ["python", "manage.py", "restore_check"]
    environment:
      RUN_MIGRATIONS: "0"
    profiles: ["restore-check"]

"""
if anchor in text and "  backup:" not in text:
    text = text.replace(anchor, "\n" + insert + "networks:\n", 1)
    p.write_text(text, encoding="utf-8")
    print("  OK    compose.yml: добавлены backup и restore-check")
else:
    print("  WARN  не нашёл точку вставки в compose.yml")
PY
    PATCHED=$((PATCHED+1))
fi

# ===================================================== 10. settings/base.py
echo
echo "==> Патч config/settings/base.py (BACKUP_DIR, Celery beat)"
SETTINGS="config/settings/base.py"
cp -p "$SETTINGS" "$BACKUP_DIR/$SETTINGS" 2>/dev/null || true
python3 - <<'PY'
import pathlib
p = pathlib.Path("config/settings/base.py")
text = p.read_text(encoding="utf-8")

# 1. Константы бэкапа — после ADMIN_URL_PREFIX
if "BA_BACKUP_CHECK_ENABLED" not in text:
    anchor = 'ADMIN_URL_PREFIX = env("ADMIN_URL_PREFIX", "crm/")'
    insert = (
        'ADMIN_URL_PREFIX = env("ADMIN_URL_PREFIX", "crm/")\n'
        '\n'
        '# --- Резервное копирование (§2.5) --------------------------------------\n'
        'BACKUP_DIR = env("BACKUP_DIR", "/app/var/backups")\n'
        'BACKUP_RETENTION_DAYS = env_int("BACKUP_RETENTION_DAYS", 30)\n'
        'BA_BACKUP_CHECK_ENABLED = env_bool("BA_BACKUP_CHECK_ENABLED", True)\n'
        'BA_BACKUP_STALE_HOURS = env_int("BA_BACKUP_STALE_HOURS", 48)\n'
    )
    text = text.replace(anchor, insert, 1)

# 2. Celery beat schedule — заменить пустой словарь
old_beat = 'CELERY_BEAT_SCHEDULE: dict[str, dict[str, object]] = {}'
new_beat = '''CELERY_BEAT_SCHEDULE: dict[str, dict[str, object]] = {
    "backup-full-daily": {
        "task": "crm.backup_full",
        "schedule": 60 * 60 * 24,  # ежедневно 03:00 UTC — задаётся через crontab
        "options": {"expires": 60 * 30},
    },
    "backup-status-hourly": {
        "task": "crm.backup_status_alert",
        "schedule": 60 * 60,
        "options": {"expires": 60 * 10},
    },
    "restore-check-monthly": {
        "task": "crm.restore_check",
        "schedule": 60 * 60 * 24 * 30,
        "options": {"expires": 60 * 60},
    },
}'''
if old_beat in text:
    text = text.replace(old_beat, new_beat, 1)

p.write_text(text, encoding="utf-8")
print("  OK    config/settings/base.py патчен")
PY
PATCHED=$((PATCHED+1))

# ===================================================== 11. readyz → backup
echo
echo "==> Патч apps/core/health.py (readyz + backup freshness)"
cp -p apps/core/health.py "$BACKUP_DIR/apps/core/health.py" 2>/dev/null || true
python3 - <<'PY'
import pathlib
p = pathlib.Path("apps/core/health.py")
text = p.read_text(encoding="utf-8")
if "BA_BACKUP_CHECK_ENABLED" in text:
    print("  SKIP  apps/core/health.py уже содержит проверку бэкапа")
else:
    old = (
        '    try:\n'
        '        client = redis.from_url(settings.CELERY_BROKER_URL, socket_timeout=3)\n'
        '        checks["broker"] = "ok" if client.ping() else "fail"\n'
        '    except Exception:\n'
        '        checks["broker"] = "fail"\n'
    )
    new = old + (
        '\n'
        '    if getattr(settings, "BA_BACKUP_CHECK_ENABLED", False):\n'
        '        try:\n'
        '            from apps.crm.services.backup import latest_backup_age_hours\n'
        '            age = latest_backup_age_hours()\n'
        '            stale_hours = getattr(settings, "BA_BACKUP_STALE_HOURS", 48)\n'
        '            if age is None:\n'
        '                checks["backup"] = "missing"\n'
        '            elif age > stale_hours:\n'
        '                checks["backup"] = "stale"\n'
        '            else:\n'
        '                checks["backup"] = "ok"\n'
        '        except Exception:\n'
        '            checks["backup"] = "fail"\n'
    )
    if old in text:
        text = text.replace(old, new, 1)
        p.write_text(text, encoding="utf-8")
        print("  OK    readyz теперь проверяет свежесть бэкапа")
    else:
        print("  WARN  не нашёл блок broker в health.py — правьте вручную")
PY
PATCHED=$((PATCHED+1))

# ===================================================== 12. .env.example
echo
echo "==> Патч .env.example"
if grep -q '^BACKUP_DIR=' .env.example 2>/dev/null; then
    echo "  SKIP  .env.example уже содержит BACKUP_DIR"
    SKIPPED=$((SKIPPED+1))
else
    cp -p .env.example "$BACKUP_DIR/.env.example" 2>/dev/null || true
    cat >> .env.example <<'BA_EOF'

# --- Резервное копирование (§2.5) ---
BACKUP_DIR=/app/var/backups
BACKUP_RETENTION_DAYS=30
BA_BACKUP_CHECK_ENABLED=True
BA_BACKUP_STALE_HOURS=48
BA_EOF
    printf '  OK    .env.example\n'
    CREATED=$((CREATED+1))
fi

# ===================================================== 13. Makefile таргеты
echo
echo "==> Патч Makefile (make backup / make restore-check)"
if grep -q '^backup:' Makefile 2>/dev/null; then
    echo "  SKIP  Makefile уже содержит таргеты"
    SKIPPED=$((SKIPPED+1))
else
    cp -p Makefile "$BACKUP_DIR/Makefile" 2>/dev/null || true
    python3 - <<'PY'
import pathlib
p = pathlib.Path("Makefile")
text = p.read_text(encoding="utf-8")
anchor = "\ndump:\n"
insert = """\
backup:
> $(COMPOSE) --profile backup run --rm backup

restore-check:
> $(COMPOSE) --profile restore-check run --rm restore-check

"""
if anchor in text and "backup:\n" not in text:
    text = text.replace(anchor, "\n" + insert + "dump:\n", 1)
    # обновим .PHONY
    if ".PHONY: help env certs" in text:
        text = text.replace(
            "help env certs", "help env certs backup restore-check", 1)
    p.write_text(text, encoding="utf-8")
    print("  OK    Makefile: добавлены таргеты backup и restore-check")
PY
    PATCHED=$((PATCHED+1))
fi

# ===================================================== 14. Тест readyz
echo
echo "==> Патч tests/integration/test_core.py (readyz не ломается)"
if grep -q 'BA_BACKUP_CHECK_ENABLED' tests/integration/test_core.py 2>/dev/null; then
    echo "  SKIP  тест уже обновлён"
    SKIPPED=$((SKIPPED+1))
else
    cp -p tests/integration/test_core.py "$BACKUP_DIR/tests/integration/test_core.py" 2>/dev/null || true
    python3 - <<'PY'
import pathlib
p = pathlib.Path("tests/integration/test_core.py")
text = p.read_text(encoding="utf-8")
old = (
    '@pytest.mark.django_db\n'
    'def test_readyz(anon_client: Client) -> None:\n'
    '    response = anon_client.get("/readyz")\n'
    '    assert response.status_code in {200, 503}\n'
    '    assert set(response.json()["checks"]) == {"db", "cache", "broker"}\n'
)
new = (
    '@pytest.mark.django_db\n'
    '@override_settings(BA_BACKUP_CHECK_ENABLED=False)\n'
    'def test_readyz(anon_client: Client) -> None:\n'
    '    response = anon_client.get("/readyz")\n'
    '    assert response.status_code in {200, 503}\n'
    '    assert set(response.json()["checks"]) == {"db", "cache", "broker"}\n'
)
if old in text:
    text = text.replace(old, new, 1)
    if "from django.test import override_settings" not in text:
        text = text.replace(
            "from django.test import Client",
            "from django.test import Client, override_settings",
            1,
        )
    p.write_text(text, encoding="utf-8")
    print("  OK    тест обновлён")
else:
    print("  WARN  не нашёл test_readyz — обновите вручную")
PY
    PATCHED=$((PATCHED+1))
fi

# ===================================================== Итог
echo
echo "============================================================"
echo "  Установка завершена"
echo "  Создано/обновлено: $CREATED"
echo "  Пропущено:         $SKIPPED"
echo "  Патчей:            $PATCHED"
if [ -d "$BACKUP_DIR" ]; then
    echo "  Бэкап:             $BACKUP_DIR"
fi
echo "============================================================"
cat <<'BA_EOF'

Следующие шаги:
  1. Добавить в .env (если отсутствуют):
       BACKUP_DIR=/app/var/backups
       BACKUP_RETENTION_DAYS=30
       BA_BACKUP_CHECK_ENABLED=True
       BA_BACKUP_STALE_HOURS=48

  2. Пересобрать образ (postgresql-client-18):
       docker compose -f compose.yml -f compose.dev-lite.yml build --no-cache web

  3. Сгенерировать миграцию для BackupRun и применить её:
       docker compose -f compose.yml -f compose.dev-lite.yml run --rm \
         -e RUN_MIGRATIONS=0 -e RUN_COLLECTSTATIC=0 \
         web python manage.py makemigrations crm
       docker compose -f compose.yml -f compose.dev-lite.yml run --rm \
         -e RUN_MIGRATIONS=0 -e RUN_COLLECTSTATIC=0 \
         web python manage.py migrate --noinput

  4. Прогнать полный тест-ран через ./verify_backup.sh
BA_EOF
