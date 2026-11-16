"""Пробы живучести и готовности (§2.23)."""
from __future__ import annotations

import redis
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import HttpRequest, JsonResponse


def healthz(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


def readyz(request: HttpRequest) -> JsonResponse:
    checks: dict[str, str] = {}

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["db"] = "ok"
    except Exception:
        checks["db"] = "fail"

    try:
        cache.set("ba:readyz", "1", 10)
        checks["cache"] = "ok" if cache.get("ba:readyz") == "1" else "fail"
    except Exception:
        checks["cache"] = "fail"

    try:
        client = redis.from_url(settings.CELERY_BROKER_URL, socket_timeout=3)
        checks["broker"] = "ok" if client.ping() else "fail"
    except Exception:
        checks["broker"] = "fail"

    if getattr(settings, "BA_BACKUP_CHECK_ENABLED", False):
        try:
            from apps.crm.services.backup import latest_backup_age_hours
            age = latest_backup_age_hours()
            stale_hours = getattr(settings, "BA_BACKUP_STALE_HOURS", 48)
            if age is None:
                checks["backup"] = "missing"
            elif age > stale_hours:
                checks["backup"] = "stale"
            else:
                checks["backup"] = "ok"
        except Exception:
            checks["backup"] = "fail"

    ready = all(v in ("ok", "missing") for v in checks.values())
    return JsonResponse({"status": "ready" if ready else "degraded", "checks": checks},
                        status=200 if ready else 503)
