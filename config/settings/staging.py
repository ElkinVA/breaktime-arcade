"""Staging: обезличенные данные, noindex, отдельные секреты (§2.5)."""

from __future__ import annotations

from .base import env, env_bool
from .prod import *  # noqa: F403

SENTRY_ENV = env("SENTRY_ENV", "staging")
BA_NOINDEX = True
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
# Staging nginx enforces Basic Auth on every location and exposes the portal on
# an external port while listening on 8443 internally; the current browser
# harness cannot authenticate or reach that topology. Keeping the gate enabled
# would make every staging import unpublishable. Production remains fail-closed;
# revisit when staging gets a game server block and harness credentials
# (owner decision).
BROWSER_AUTOTEST_ENABLED = env_bool("BROWSER_AUTOTEST_ENABLED", False)
PUBLISH_REQUIRE_BROWSER_AUTOTEST = env_bool("PUBLISH_REQUIRE_BROWSER_AUTOTEST", False)
