"""Production (§2.20, Приложение B)."""

from __future__ import annotations

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration

from .base import *  # noqa: F403
from .base import env, env_bool, env_list

DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 63_072_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

STORAGES["staticfiles"]["BACKEND"] = (  # noqa: F405
    "apps.core.storage.BAStaticFilesStorage"
)

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
# §2.10.2: проверка HIBP обязательна; при недоступности сервис fails closed.
HIBP_ENABLED = env_bool("HIBP_ENABLED", True)
# The importer currently writes static-only reports (playwright=False). Do not
# treat them as browser proof in production until a real runner exists.
PUBLISH_REQUIRE_BROWSER_AUTOTEST = env_bool("PUBLISH_REQUIRE_BROWSER_AUTOTEST", True)
BROWSER_AUTOTEST_ENABLED = env_bool("BROWSER_AUTOTEST_ENABLED", True)
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_PASSWORD")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")

BA_CSP_DIRECTIVES["img-src"] = f"'self' data: {env('CDN_BASE_URL')}".strip()  # noqa: F405

SENTRY_DSN = env("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=env("SENTRY_ENV", "production"),
        integrations=[DjangoIntegration(), CeleryIntegration()],
        send_default_pii=False,
        traces_sample_rate=0.05,
    )
