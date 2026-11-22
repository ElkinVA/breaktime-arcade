from __future__ import annotations

import subprocess
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.crm.models.backup import BackupRun
from apps.crm.services.backup import (
    _db_params,
    _pg_env,
    _rotate,
    _sha256,
    latest_backup_age_hours,
    run_full_backup,
    run_restore_check,
)
from apps.crm.views import dashboard, login_view, logout_view


@pytest.mark.django_db
def test_db_params_from_database_url(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgres://user:secret@dbhost:6543/mydb")
    params = _db_params()
    assert params == {
        "host": "dbhost",
        "port": "6543",
        "user": "user",
        "password": "secret",
        "db": "mydb",
    }
    assert _pg_env()["PGPASSWORD"] == "secret"


def test_sha256_and_rotation(tmp_path: Path) -> None:
    path = tmp_path / "ba-old.dump"
    path.write_bytes(b"abc")
    assert _sha256(path) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

    old = tmp_path / "ba-old.dump"
    new = tmp_path / "ba-new.dump"
    new.write_bytes(b"x")
    old_time = 1
    new_time = timezone.now().timestamp()
    import os

    os.utime(old, (old_time, old_time))
    os.utime(new, (new_time, new_time))
    _rotate(tmp_path, retention_days=30)
    assert not old.exists()
    assert new.exists()


@pytest.mark.django_db
def test_run_full_backup_success(monkeypatch, tmp_path: Path) -> None:
    def fake_run(cmd, **_kwargs):
        Path(cmd[cmd.index("-f") + 1]).write_bytes(b"dump")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr("apps.crm.services.backup.subprocess.run", fake_run)
    run = run_full_backup(tmp_path)

    assert run.status == BackupRun.STATUS_SUCCESS
    assert run.size_bytes == 4
    assert run.sha256
    assert Path(run.file_path).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("error", ["called", "missing"])
def test_run_full_backup_failures(monkeypatch, tmp_path: Path, error: str) -> None:
    def fake_run(cmd, **_kwargs):
        if error == "called":
            raise subprocess.CalledProcessError(1, cmd, stderr="boom")
        raise FileNotFoundError("pg_dump")

    monkeypatch.setattr("apps.crm.services.backup.subprocess.run", fake_run)
    run = run_full_backup(tmp_path)

    assert run.status == BackupRun.STATUS_FAILED
    assert run.error_message


@pytest.mark.django_db
def test_restore_check_requires_backup(monkeypatch) -> None:
    run = run_restore_check()
    assert run.status == BackupRun.STATUS_FAILED
    assert "Нет успешных" in run.error_message


@pytest.mark.django_db
def test_restore_check_missing_file(monkeypatch, tmp_path: Path) -> None:
    run = run_restore_check(tmp_path / "missing.dump")
    assert run.status == BackupRun.STATUS_FAILED
    assert "Файл не найден" in run.error_message


@pytest.mark.django_db
def test_restore_check_success(monkeypatch, tmp_path: Path) -> None:
    backup = tmp_path / "ba.dump"
    backup.write_bytes(b"dump")
    monkeypatch.setattr(
        "apps.crm.services.backup.subprocess.run",
        lambda cmd, **_kwargs: subprocess.CompletedProcess(cmd, 0),
    )

    run = run_restore_check(backup)

    assert run.status == BackupRun.STATUS_SUCCESS
    assert run.verified_at is not None
    assert run.meta["backup_path"] == str(backup)


@pytest.mark.django_db
def test_restore_check_failure(monkeypatch, tmp_path: Path) -> None:
    backup = tmp_path / "ba.dump"
    backup.write_bytes(b"dump")

    def fake_run(cmd, **_kwargs):
        if cmd[0] == "pg_restore":
            raise subprocess.CalledProcessError(1, cmd, stderr="restore failed")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr("apps.crm.services.backup.subprocess.run", fake_run)

    run = run_restore_check(backup)

    assert run.status == BackupRun.STATUS_FAILED
    assert "restore failed" in run.error_message


@pytest.mark.django_db
def test_latest_backup_age(monkeypatch) -> None:
    assert latest_backup_age_hours() is None
    run = BackupRun.objects.create(type=BackupRun.TYPE_FULL, status=BackupRun.STATUS_SUCCESS)
    BackupRun.objects.filter(pk=run.pk).update(started_at=timezone.now() - timedelta(hours=3))
    age = latest_backup_age_hours()
    assert age is not None
    assert 2.9 < age < 3.1


@pytest.mark.django_db
def test_crm_tasks(monkeypatch) -> None:
    from apps.crm import tasks

    monkeypatch.setattr(
        tasks,
        "run_full_backup",
        lambda _path: SimpleNamespace(status="success", id="run-id"),
    )
    assert tasks.backup_full() == "success run=run-id"
    monkeypatch.setattr(
        tasks,
        "run_restore_check",
        lambda: SimpleNamespace(status="success", id="restore-id"),
    )
    assert tasks.restore_check() == "success run=restore-id"

    monkeypatch.setattr(tasks, "latest_backup_age_hours", lambda: None)
    assert tasks.backup_status_alert() == {"status": "no_backup"}
    monkeypatch.setattr(tasks, "latest_backup_age_hours", lambda: 30.0)
    assert tasks.backup_status_alert()["status"] == "stale"
    monkeypatch.setattr(tasks, "latest_backup_age_hours", lambda: 1.0)
    assert tasks.backup_status_alert()["status"] == "ok"


def test_backup_commands(monkeypatch, tmp_path: Path) -> None:
    from apps.crm.management.commands import backup_run, restore_check

    monkeypatch.setattr(
        backup_run,
        "run_full_backup",
        lambda _path, _days: SimpleNamespace(
            status="success", id="id", size_bytes=1, sha256="a" * 64
        ),
    )
    call_command("backup_run", output_dir=str(tmp_path), retention_days=1)

    monkeypatch.setattr(
        backup_run,
        "run_full_backup",
        lambda _path, _days: SimpleNamespace(status="failed", error_message="boom"),
    )
    with pytest.raises(CommandError):
        call_command("backup_run", output_dir=str(tmp_path))

    monkeypatch.setattr(
        restore_check,
        "run_restore_check",
        lambda _path: SimpleNamespace(status="success", verified_at="now"),
    )
    call_command("restore_check")

    monkeypatch.setattr(
        restore_check,
        "run_restore_check",
        lambda _path: SimpleNamespace(status="failed", error_message="boom"),
    )
    with pytest.raises(CommandError):
        call_command("restore_check")


@pytest.mark.django_db
def test_crm_views(monkeypatch) -> None:
    request = RequestFactory().get("/crm/login/")
    request.user = SimpleNamespace(is_authenticated=False, is_staff=False)
    login_response = login_view(request)
    assert login_response.status_code == 302
    assert login_response.url.startswith(reverse("accounts:login"))
    assert "next=" in login_response.url

    logout_request = RequestFactory().post("/crm/logout/")
    SessionMiddleware(lambda _request: None).process_request(logout_request)
    logout_request.session.save()
    assert logout_view(logout_request).status_code == 302

    anonymous = RequestFactory().get("/crm/")
    anonymous.user = SimpleNamespace(is_authenticated=False, is_staff=False)
    assert dashboard(anonymous).status_code == 302

    monkeypatch.setattr(
        "apps.crm.views.dashboard_stats",
        lambda: SimpleNamespace(
            published_games=0,
            total_accounts=0,
            active_accounts_30d=0,
            sessions_today=0,
            top_games=(),
            average_rating=0.0,
            new_votes_today=0,
            latest_backup=None,
        ),
    )
    staff = RequestFactory().get("/crm/")
    staff.user = SimpleNamespace(is_authenticated=True, is_staff=True)
    response = dashboard(staff)
    assert response.template_name == "crm/dashboard.html"
