"""Базовые настройки. Норматив: BA-PLAT-4.2, Приложение B."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

BASE_DIR = Path(__file__).resolve().parents[2]


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    return env(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(env(name, str(default)))
    except ValueError:
        return default


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env_bool("DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.postgres",
    "rest_framework",
    "apps.core",
    "apps.accounts",
    "apps.catalog",
    "apps.gameplay",
    "apps.leaderboards",
    "apps.ratings",
    "apps.pipeline",
    "apps.i18n",
    "apps.crm",
    "apps.moderation",
    "apps.analytics",
    "apps.content",
    "apps.theme",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.core.middleware.RequestIDMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "apps.i18n.middleware.LanguagePrefixMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
    "apps.core.middleware.ContentSecurityPolicyMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.i18n",
                "apps.core.context_processors.platform",
                "apps.i18n.context_processors.i18n",
                "apps.theme.context_processors.theme",
            ],
        },
    },
]

# --- Данные -------------------------------------------------------------
_db = urlparse(env("DATABASE_URL", "postgres://ba:ba@db:5432/ba"))
DB_POOL_ENABLED = env_bool("DB_POOL_ENABLED", True)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(_db.path.lstrip("/")) or "ba",
        "USER": unquote(_db.username or "ba"),
        "PASSWORD": unquote(_db.password or ""),
        "HOST": _db.hostname or "db",
        "PORT": str(_db.port or 5432),
        # Пул и CONN_MAX_AGE взаимоисключающи (§2.5).
        "CONN_MAX_AGE": 0 if DB_POOL_ENABLED else 60,
        "CONN_HEALTH_CHECKS": not DB_POOL_ENABLED,
        "OPTIONS": (
            {"pool": {"min_size": env_int("DB_POOL_MIN", 2), "max_size": env_int("DB_POOL_MAX", 8)}}
            if DB_POOL_ENABLED
            else {}
        ),
        "ATOMIC_REQUESTS": False,
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("REDIS_CACHE_URL", "redis://redis-cache:6379/1"),
        "KEY_PREFIX": "ba",
        "TIMEOUT": 300,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    },
}

# --- Аутентификация -----------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
PASSWORD_HASHERS = [
    "apps.accounts.hashers.BAArgon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_RESET_TIMEOUT = 1800
SESSION_ENGINE = "django.contrib.sessions.backends.db"

# --- Безопасность -------------------------------------------------------
SESSION_COOKIE_DOMAIN = None
CSRF_COOKIE_DOMAIN = None
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", env("PORTAL_ORIGIN", "https://portal.test:8443"))

PORTAL_ORIGIN = env("PORTAL_ORIGIN", "https://portal.test:8443")
GAMES_DOMAIN = env("GAMES_DOMAIN", "games.test")
BA_CSP_DIRECTIVES = {
    "default-src": "'self'",
    "script-src": "'self'",
    "style-src": "'self'",
    "img-src": "'self' data:",
    "font-src": "'self'",
    "connect-src": "'self'",
    "frame-src": env("BA_GAMES_FRAME_SRC", f"https://*.{GAMES_DOMAIN}:8443"),
    "frame-ancestors": "'none'",
    "base-uri": "'self'",
    "form-action": "'self'",
    "object-src": "'none'",
}
BA_PERMISSIONS_POLICY = "geolocation=(), microphone=(), camera=(), payment=()"

# --- Интернационализация ------------------------------------------------
LANGUAGE_CODE = "en"
LANGUAGES = [
    ("en", "English"), ("de", "Deutsch"), ("nl", "Nederlands"),
    ("ru", "Русский"), ("fr", "Français"), ("es", "Español"),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True
USE_TZ = True
TIME_ZONE = "UTC"

# --- Статика и загрузки -------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "apps.core.storage.BAStaticFilesStorage"},
}
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024
FILE_UPLOAD_PERMISSIONS = 0o640
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o750

# --- Celery -------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", env("REDIS_BROKER_URL", "redis://redis-broker:6379/2"))
CELERY_RESULT_BACKEND = None
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TIMEZONE = "UTC"
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BEAT_SCHEDULE: dict[str, dict[str, object]] = {
    "backup-full-daily": {
        "task": "crm.backup_full",
        "schedule": 60 * 60 * 24,
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
}

# --- DRF ----------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "sessions": "30/hour",
        "results": "60/hour",
        "heartbeat": "3/min",
        "storage": "600/hour",
    },
    "UNAUTHENTICATED_USER": "django.contrib.auth.models.AnonymousUser",
}

# --- Константы пайплайна (§2.14.2) --------------------------------------
BA_SDK_DEFAULT_VERSION = env("BA_SDK_DEFAULT_VERSION", "1.1.0")
ZIP_MAX_BYTES = env_int("ZIP_MAX_BYTES", 26_214_400)
CRITICAL_PATH_WARN_BYTES = env_int("CRITICAL_PATH_WARN_BYTES", 2_097_152)
CRITICAL_PATH_MAX_BYTES = env_int("CRITICAL_PATH_MAX_BYTES", 4_194_304)
ADMIN_URL_PREFIX = env("ADMIN_URL_PREFIX", "crm/")

# --- Резервное копирование (§2.5) --------------------------------------
BACKUP_DIR = env("BACKUP_DIR", "/app/var/backups")
BACKUP_RETENTION_DAYS = env_int("BACKUP_RETENTION_DAYS", 30)
BA_BACKUP_CHECK_ENABLED = env_bool("BA_BACKUP_CHECK_ENABLED", True)
BA_BACKUP_STALE_HOURS = env_int("BA_BACKUP_STALE_HOURS", 48)


# --- Журналирование (JSON + request-id, §2.24) --------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "apps.core.logging.JsonFormatter"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "json"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "django.db.backends": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "apps": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "celery": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
