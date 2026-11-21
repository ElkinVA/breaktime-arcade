from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("breaktime")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# R-036 Phase 1: structured redelivery/failure/worker-shutdown logs.
from apps.core import celery_observability  # noqa: E402, F401
