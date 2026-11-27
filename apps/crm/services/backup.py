# ruff: noqa: S608 - SQL built only from fixed commands and internal constants
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

from django.db import connection
from django.utils import timezone

from apps.crm.models.backup import BackupRun

logger = logging.getLogger(__name__)

RESTORE_CHECK_TARGET_DB = "ba_restore_check"
# Session advisory-lock, сериализующий проверки восстановления: параллельный
# DROP/CREATE временной БД ломает чужой прогон и даёт ложные ошибки.
# Ключ фиксированный (0x5245434B == "RECK"), помещается в signed int64.
RESTORE_CHECK_ADVISORY_LOCK_KEY = 0x5245434B
RESTORE_CHECK_LOCK_BUSY_MESSAGE = (
    "Проверка восстановления уже выполняется другим процессом; повторный запуск пропущен"
)
REQUIRED_TABLES = (
    "django_migrations",
    "accounts_user",
    "accounts_profile",
    "catalog_game",
    "catalog_game_version",
    "catalog_game_translation",
    "gameplay_session",
    "gameplay_result",
    "gameplay_leaderboard_entry",
    "crm_backup_run",
)


class RestoreCheckError(Exception):
    """A restore completed with an unusable or unexpected database."""


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
def _backup_run_for(path: Path) -> BackupRun | None:
    return (
        BackupRun.objects.filter(
            type=BackupRun.TYPE_FULL,
            status=BackupRun.STATUS_SUCCESS,
            file_path=str(path),
        )
        .order_by("-started_at")
        .first()
    )


def _psql_scalar(base: list[str], env: dict[str, str], sql: str) -> int:
    result = subprocess.run(  # noqa: S603
        base + ["-t", "-c", sql],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        return int(result.stdout.strip())
    except ValueError as exc:
        raise RestoreCheckError(f"Неожиданный ответ SQL-проверки: {result.stdout!r}") from exc


def _required_tables_sql() -> str:
    names = ",".join(f"'{name}'" for name in REQUIRED_TABLES)
    return (
        "SELECT count(*) FROM information_schema.tables "
        f"WHERE table_schema='public' AND table_name IN ({names});"
    )


def _try_acquire_restore_lock() -> bool:
    """Пытается взять advisory lock, не блокируя процесс."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [RESTORE_CHECK_ADVISORY_LOCK_KEY])
        row = cursor.fetchone()
    return bool(row and row[0])


def _release_restore_lock() -> None:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [RESTORE_CHECK_ADVISORY_LOCK_KEY])
    except Exception as exc:
        # Снятие блокировки не должно скрывать результат самой проверки.
        logger.warning("restore-check: не удалось освободить advisory lock: %s", exc)


def run_restore_check(backup_path: Path | None = None) -> BackupRun:
    """Восстанавливает дамп в ba_restore_check и проверяет его содержимое.

    Параллельные запуски сериализуются session-level advisory lock: второй
    процесс не трогает ba_restore_check и завершается с явным failed-статусом.
    """
    run = BackupRun.objects.create(
        type=BackupRun.TYPE_RESTORE_CHECK, status=BackupRun.STATUS_RUNNING
    )
    if not _try_acquire_restore_lock():
        run.status = BackupRun.STATUS_FAILED
        run.error_message = RESTORE_CHECK_LOCK_BUSY_MESSAGE
        run.meta = {
            "advisory_lock": "busy",
            "advisory_lock_key": RESTORE_CHECK_ADVISORY_LOCK_KEY,
        }
        _finish(run)
        return run
    try:
        return _run_restore_check_locked(run, backup_path)
    finally:
        _release_restore_lock()


def _run_restore_check_locked(run: BackupRun, backup_path: Path | None) -> BackupRun:
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
    try:
        if backup_path.stat().st_size == 0:
            run.status = BackupRun.STATUS_FAILED
            run.error_message = f"Пустой дамп: {backup_path}"
            _finish(run)
            return run

        backup_run = _backup_run_for(backup_path)
        if backup_run is None or not backup_run.sha256:
            run.status = BackupRun.STATUS_FAILED
            run.error_message = f"Нет записи BackupRun с SHA-256 для {backup_path}"
            _finish(run)
            return run
        actual_sha = _sha256(backup_path)
    except OSError as exc:
        run.status = BackupRun.STATUS_FAILED
        run.error_message = f"Ошибка доступа к дампу: {exc}"[:2000]
        _finish(run)
        return run
    if actual_sha != backup_run.sha256:
        run.status = BackupRun.STATUS_FAILED
        run.error_message = "SHA-256 дампа не совпадает с метаданными BackupRun"
        run.meta = {
            "backup_path": str(backup_path),
            "backup_run_id": str(backup_run.id),
            "sha256": actual_sha,
            "expected_sha256": backup_run.sha256,
        }
        _finish(run)
        return run
    run.meta = {
        "backup_path": str(backup_path),
        "backup_run_id": str(backup_run.id),
        "sha256": actual_sha,
    }

    p = _db_params()
    env = _pg_env()
    target_db = RESTORE_CHECK_TARGET_DB
    # psql подключается к базе "postgres" от того же пользователя (суперюзер в контейнере).
    base_psql = ["psql", "-h", p["host"], "-p", p["port"], "-U", p["user"], "-d", "postgres"]

    commands = [
        base_psql + ["-c", f'DROP DATABASE IF EXISTS "{target_db}" WITH (FORCE);'],
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
    ]

    try:
        for c in commands:
            # Команды фиксированы в коде; значения БД приходят из конфигурации.
            subprocess.run(  # noqa: S603
                c, env=env, check=True, capture_output=True, text=True
            )
        if _sha256(backup_path) != backup_run.sha256:
            raise RestoreCheckError("SHA-256 дампа изменился во время восстановления")
        target_psql = base_psql[:-1] + [target_db]
        table_count = _psql_scalar(
            target_psql,
            env,
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';",
        )
        required_count = _psql_scalar(target_psql, env, _required_tables_sql())
        migration_count = _psql_scalar(target_psql, env, "SELECT count(*) FROM django_migrations;")
        if table_count <= 0:
            raise RestoreCheckError("В восстановленной БД нет таблиц")
        if required_count != len(REQUIRED_TABLES):
            raise RestoreCheckError(
                f"Обязательных таблиц {required_count} из {len(REQUIRED_TABLES)}"
            )
        if migration_count <= 0:
            raise RestoreCheckError("Таблица django_migrations пуста")
        run.status = BackupRun.STATUS_SUCCESS
        run.verified_at = timezone.now()
        run.meta = {
            **run.meta,
            "table_count": table_count,
            "required_tables": required_count,
            "migration_count": migration_count,
        }
    except RestoreCheckError as exc:
        run.status = BackupRun.STATUS_FAILED
        run.error_message = str(exc)[:2000]
    except subprocess.CalledProcessError as exc:
        run.status = BackupRun.STATUS_FAILED
        run.error_message = ((exc.stderr or "") + (exc.stdout or "") or str(exc))[:2000]
    except FileNotFoundError as exc:
        run.status = BackupRun.STATUS_FAILED
        run.error_message = f"Утилита не найдена: {exc}"
    except OSError as exc:
        run.status = BackupRun.STATUS_FAILED
        run.error_message = f"Ошибка доступа к дампу: {exc}"[:2000]

    # Попытка дропнуть временную БД — не фатально при ошибке.
    try:
        subprocess.run(  # noqa: S603
            base_psql + ["-c", f'DROP DATABASE IF EXISTS "{target_db}" WITH (FORCE);'],
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
