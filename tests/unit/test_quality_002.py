from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest
from django.core.management import call_command
from django.db import connection
from django.test import RequestFactory, override_settings

from apps.accounts.services.hibp import HIBPUnavailable, password_is_pwned
from apps.catalog.models import Game
from apps.core.storage import BAStaticFilesStorage
from apps.core.views import index
from apps.i18n.services.coverage import language_coverage, language_coverage_percent
from apps.i18n.templatetags import ba_i18n
from apps.pipeline.services.worker import JobOutcome, WorkerError
from apps.pipeline.tasks import (
    cleanup_zip_staging,
    enqueue_extraction,
    extract_zip_task,
)
from apps.theme.views import theme_css


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_args: object) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


def _hibp_suffix(password: str) -> str:
    return hashlib.sha1(password.encode("utf-8")).hexdigest().upper()[5:]  # noqa: S324


@override_settings(HIBP_ENABLED=False)
def test_hibp_disabled_does_not_use_network() -> None:
    assert password_is_pwned("password") is False


@override_settings(HIBP_ENABLED=True, HIBP_TIMEOUT_SECONDS=3)
def test_hibp_detects_and_handles_payload(monkeypatch) -> None:
    suffix = _hibp_suffix("password")
    payloads = {
        f"{suffix}:3": True,
        f"{suffix}:0": False,
        f"{suffix}:not-a-number": True,
        "0000000000000000000000000000000000:9": False,
    }
    for line, expected in payloads.items():
        monkeypatch.setattr(
            "apps.accounts.services.hibp.urlopen",
            lambda _request, timeout, line=line: _FakeResponse(line.encode()),
        )
        assert password_is_pwned("password") is expected


@override_settings(HIBP_ENABLED=True, HIBP_TIMEOUT_SECONDS=3)
@pytest.mark.parametrize(
    "error",
    [
        URLError("down"),
        HTTPError("https://example.invalid", 500, "err", None, None),
        TimeoutError("slow"),
    ],
)
def test_hibp_fail_closed(monkeypatch, error: Exception) -> None:
    def failing(*_args: object, **_kwargs: object) -> None:
        raise error

    monkeypatch.setattr("apps.accounts.services.hibp.urlopen", failing)
    with pytest.raises(HIBPUnavailable):
        password_is_pwned("password")


def test_core_index_returns_service_metadata() -> None:
    response = index(RequestFactory().get("/"))
    assert response.status_code == 200
    assert json.loads(response.content)["service"] == "breaktime-arcade"


def test_theme_css_serves_active_hash_only(monkeypatch) -> None:
    monkeypatch.setattr(
        "apps.theme.views.get_active_theme_css", lambda: ("abc123", "body{color:red}")
    )
    request = RequestFactory().get("/theme-abc123.css")

    response = theme_css(request, "abc123")

    assert response.status_code == 200
    assert response["Cache-Control"] == "public, max-age=31536000, immutable"
    assert response.content == b"body{color:red}"
    assert theme_css(request, "other").status_code == 404


def test_static_storage_falls_back_for_external_imports() -> None:
    storage = BAStaticFilesStorage()

    assert storage.hashed_name("missing.css") == "missing.css"

    def failing_hashed_name(*_args: object, **_kwargs: object) -> str:
        raise ValueError("external import")

    assert storage._url(failing_hashed_name, "missing.css") == "missing.css"


@pytest.mark.django_db
def test_language_coverage_counts_published_entries() -> None:
    from apps.i18n.models import Language, TranslationEntry

    language, _ = Language.objects.get_or_create(
        code="xx", defaults={"name": "Test", "is_active": True}
    )
    TranslationEntry.objects.update_or_create(
        namespace="quality002",
        key="hello",
        language=language,
        defaults={"value": "Hi", "status": TranslationEntry.STATUS_PUBLISHED},
    )

    translated, total = language_coverage(language)

    assert translated >= 1
    assert total >= translated
    assert 0 <= language_coverage_percent(language) <= 100


def test_coverage_percent_zero_total(monkeypatch) -> None:
    monkeypatch.setattr("apps.i18n.services.coverage.language_coverage", lambda _language: (0, 0))
    assert language_coverage_percent(SimpleNamespace()) == 100


def test_ba_t_and_lang_switcher(monkeypatch) -> None:
    languages = [
        SimpleNamespace(code="en", name="English"),
        SimpleNamespace(code="de", name="Deutsch"),
    ]
    monkeypatch.setattr(ba_i18n, "get_active_languages", lambda: languages)
    monkeypatch.setattr(
        ba_i18n,
        "translate",
        lambda namespace, key, language, params=None, fallback=None: (
            f"{namespace}.{key}:{language.code}:{params}"
        ),
    )
    request = SimpleNamespace(LANGUAGE_CODE="en", path_info="/en/games/")

    assert ba_i18n.ba_t({}, "ns.key") == ""
    assert ba_i18n.ba_t({"request": request}, "bad-key") == ""
    assert ba_i18n.ba_t({"request": request}, "ns.key", x=1) == "ns.key:en:{'x': 1}"
    missing_current = SimpleNamespace(LANGUAGE_CODE="fr", path_info="/fr/")
    assert ba_i18n.ba_t({"request": missing_current}, "ns.key") == ""

    html = ba_i18n.ba_lang_switcher({"request": request})
    assert "/de/games/" in html
    assert "active" in html
    assert ba_i18n.ba_lang_switcher({}) == ""


class _FakeCursor:
    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *_args: object) -> bool:
        return False

    def execute(self, *_args: object) -> None:
        return None

    def fetchone(self) -> tuple[int]:
        return (1,)


class _FakeConnection:
    def cursor(self) -> _FakeCursor:
        return _FakeCursor()


class _FakeCache:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def set(self, key: str, value: str, _ttl: int) -> None:
        self.data[key] = value

    def get(self, key: str) -> str | None:
        return self.data.get(key)


class _FakeRedis:
    def __init__(self, healthy: bool = True) -> None:
        self.healthy = healthy

    def ping(self) -> bool:
        return self.healthy


def _health_dependencies(monkeypatch, *, backup_age: float | None = 1.0, healthy=True):
    monkeypatch.setattr("apps.core.health.connection", _FakeConnection())
    monkeypatch.setattr("apps.core.health.cache", _FakeCache())
    monkeypatch.setattr(
        "apps.core.health.redis.from_url", lambda *_args, **_kwargs: _FakeRedis(healthy)
    )
    monkeypatch.setattr(
        "apps.i18n.services.accept_language.is_fallback_language_active", lambda: True
    )
    monkeypatch.setattr("apps.crm.services.backup.latest_backup_age_hours", lambda: backup_age)


@override_settings(BA_BACKUP_CHECK_ENABLED=True, BA_BACKUP_STALE_HOURS=48)
def test_readyz_healthy_and_degraded(monkeypatch) -> None:
    from apps.core.health import readyz

    _health_dependencies(monkeypatch, backup_age=1.0)
    response = readyz(RequestFactory().get("/readyz"))
    assert response.status_code == 200
    assert json.loads(response.content)["checks"] == {
        "db": "ok",
        "cache": "ok",
        "broker": "ok",
        "i18n": "ok",
        "backup": "ok",
    }

    _health_dependencies(monkeypatch, backup_age=50.0)
    response = readyz(RequestFactory().get("/readyz"))
    assert response.status_code == 503
    assert json.loads(response.content)["checks"]["backup"] == "stale"

    _health_dependencies(monkeypatch, backup_age=None)
    response = readyz(RequestFactory().get("/readyz"))
    assert response.status_code == 200
    assert json.loads(response.content)["checks"]["backup"] == "missing"

    _health_dependencies(monkeypatch, healthy=False)
    response = readyz(RequestFactory().get("/readyz"))
    assert response.status_code == 503
    assert json.loads(response.content)["checks"]["broker"] == "fail"


def test_pipeline_task_wrappers(monkeypatch) -> None:
    outcome = JobOutcome(job_id="job", status="completed", total_bytes=1)
    monkeypatch.setattr("apps.pipeline.tasks.run_extraction", lambda _job_id: outcome)
    assert extract_zip_task("job")["status"] == "completed"

    monkeypatch.setattr(
        "apps.pipeline.tasks.run_extraction",
        lambda _job_id: (_ for _ in ()).throw(WorkerError("X_JOB", "bad")),
    )
    assert extract_zip_task("job")["error_code"] == "X_JOB"

    from celery.exceptions import SoftTimeLimitExceeded

    monkeypatch.setattr(
        "apps.pipeline.tasks.run_extraction",
        lambda _job_id: (_ for _ in ()).throw(SoftTimeLimitExceeded()),
    )
    assert extract_zip_task("job")["status"] == "timeout"

    monkeypatch.setattr(
        "apps.pipeline.tasks.cleanup_expired_jobs",
        lambda: {"removed": 2, "skipped": 1},
    )
    assert cleanup_zip_staging() == {"removed": 2, "skipped": 1}

    from apps.pipeline import tasks as pipeline_tasks

    monkeypatch.setattr(
        pipeline_tasks,
        "send_zip_task",
        lambda *args, **kwargs: "task-id",
    )
    assert enqueue_extraction("job") == "task-id"


@pytest.mark.django_db
def test_catalog_benchmark_baseline_smoke(capsys: pytest.CaptureFixture[str]) -> None:
    call_command("catalog_benchmark", "--games", "10", "--no-candidate-index")

    assert "baseline" in capsys.readouterr().out
    assert not Game.objects.filter(technical_id__startswith="bench").exists()


@pytest.mark.django_db(transaction=True)
def test_catalog_benchmark_candidate_smoke(capsys: pytest.CaptureFixture[str]) -> None:
    call_command("catalog_benchmark", "--games", "10", "--query", "puzzle game")

    output = capsys.readouterr().out
    assert "candidate indexes" in output
    assert "not IMMUTABLE" in output
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM pg_indexes WHERE indexname LIKE 'bench_%'")
        assert cursor.fetchone()[0] == 0
