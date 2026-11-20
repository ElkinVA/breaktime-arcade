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
    run.save(
        update_fields=[
            "finished_at",
            "status",
            "size_bytes",
            "sha256",
            "file_path",
            "remote_uri",
            "error_message",
            "verified_at",
            "meta",
        ]
    )


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
        "-h",
        p["host"],
        "-p",
        p["port"],
        "-U",
        p["user"],
        "--format=custom",
        "--compress=9",
        "-f",
        str(out),
        p["db"],
    ]
    logger.info("backup.start run=%s", run.id)

    try:
        # Команда собрана из фиксированных аргументов и DATABASE_URL, не из ввода пользователя.
        subprocess.run(  # noqa: S603
            cmd, env=_pg_env(), check=True, capture_output=True, text=True
        )
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
    run = BackupRun.objects.create(
        type=BackupRun.TYPE_RESTORE_CHECK, status=BackupRun.STATUS_RUNNING
    )

    if backup_path is None:
        last = (
            BackupRun.objects.filter(type=BackupRun.TYPE_FULL, status=BackupRun.STATUS_SUCCESS)
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
        [
            "pg_restore",
            "-h",
            p["host"],
            "-p",
            p["port"],
            "-U",
            p["user"],
            "-d",
            target_db,
            "--no-owner",
            "--no-privileges",
            "--exit-on-error",
            str(backup_path),
        ],
        [
            "psql",
            "-h",
            p["host"],
            "-p",
            p["port"],
            "-U",
            p["user"],
            "-d",
            target_db,
            "-t",
            "-c",
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';",
        ],
    ]

    try:
        for c in commands:
            # Команды фиксированы в коде; значения БД приходят из конфигурации.
            subprocess.run(  # noqa: S603
                c, env=env, check=True, capture_output=True, text=True
            )
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
        subprocess.run(  # noqa: S603
            base_psql + ["-c", f'DROP DATABASE IF EXISTS "{target_db}";'],
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        # Очистка не должна скрывать результат самой проверки восстановления.
        logger.warning("restore-check: не удалось удалить %s: %s", target_db, exc)

    _finish(run)
    return run


def latest_backup_age_hours() -> float | None:
    """Возраст последнего успешного full-бэкапа в часах (None если нет)."""
    last = (
        BackupRun.objects.filter(type=BackupRun.TYPE_FULL, status=BackupRun.STATUS_SUCCESS)
        .order_by("-started_at")
        .first()
    )
    if last is None:
        return None
    return (timezone.now() - last.started_at).total_seconds() / 3600.0
