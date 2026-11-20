"""Staging: обезличенные данные, noindex, отдельные секреты (§2.5)."""

from __future__ import annotations

from .base import env
from .prod import *  # noqa: F403

SENTRY_ENV = env("SENTRY_ENV", "staging")
BA_NOINDEX = True
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
