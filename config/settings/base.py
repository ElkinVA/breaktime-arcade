"""Базовые настройки. Норматив: BA-PLAT-4.2, Приложение B."""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from kombu import Exchange, Queue

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


def env_float(name: str, default: float) -> float:
    try:
        return float(env(name, str(default)))
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
    "apps.core.middleware.ClientIPMiddleware",
    "apps.core.middleware.RequestIDMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "apps.i18n.middleware.LanguagePrefixMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.accounts.middleware.StaffTwoFactorMiddleware",
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
                "apps.crm.context_processors.crm",
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
    # Throttle counters must not be evicted by cache pressure (OD-REDIS-001).
    # Separate Redis instance with noeviction; counters are ephemeral.
    "throttle": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("REDIS_THROTTLE_URL", "redis://redis-throttle:6379/0"),
        "KEY_PREFIX": "ba-throttle",
        "TIMEOUT": 300,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            # JSON keeps integer counters INCR-compatible; the default pickle
            # serializer makes django-redis fall back to non-atomic GET/SET.
            "SERIALIZER": "django_redis.serializers.json.JSONSerializer",
            # A blackholed host must fail the limit check, not stall requests.
            "SOCKET_CONNECT_TIMEOUT": 1,
            "SOCKET_TIMEOUT": 1,
        },
    },
}

# --- Аутентификация -----------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
PASSWORD_HASHERS = [
    "apps.accounts.hashers.BAArgon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_RESET_TIMEOUT = 1800
SESSION_ENGINE = "django.contrib.sessions.backends.db"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "account:profile"
LOGOUT_REDIRECT_URL = "catalog:home"

# --- Аккаунты и юридические версии --------------------------------------
# Текст документов и утверждённые версии ведутся отдельно (CRM/юрист).
# В dev допускается draft; production должен задать реальные версии.
TERMS_VERSION = env("TERMS_VERSION", "draft")
PRIVACY_VERSION = env("PRIVACY_VERSION", "draft")
LEGAL_TERMS_URL = env("LEGAL_TERMS_URL", "/legal/terms/")
LEGAL_PRIVACY_URL = env("LEGAL_PRIVACY_URL", "/legal/privacy/")
TOTP_ISSUER = env("TOTP_ISSUER", "Breaktime Arcade")
NICKNAME_HMAC_KEY = env("NICKNAME_HMAC_KEY", SECRET_KEY or "")
NICKNAME_CHANGE_INTERVAL_DAYS = 30
ACCOUNT_DELETION_WINDOW_DAYS = 7
LOGIN_EVENT_RETENTION_DAYS = env_int("LOGIN_EVENT_RETENTION_DAYS", 365)
NICKNAME_RESERVATION_DAYS = env_int("NICKNAME_RESERVATION_DAYS", 730)
HIBP_ENABLED = env_bool("HIBP_ENABLED", False)
HIBP_TIMEOUT_SECONDS = env_int("HIBP_TIMEOUT_SECONDS", 3)
EMAIL_VERIFICATION_TIMEOUT = 24 * 60 * 60

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
CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS", env("PORTAL_ORIGIN", "https://portal.test:8443")
)

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

# nginx overwrites X-Forwarded-For; accept it only from these proxy networks.
BA_TRUSTED_PROXY_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in env_list(
        "TRUSTED_PROXY_IPS",
        "127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16",
    )
)

# --- Интернационализация ------------------------------------------------
LANGUAGE_CODE = "en"
LANGUAGES = [
    ("en", "English"),
    ("de", "Deutsch"),
    ("nl", "Nederlands"),
    ("ru", "Русский"),
    ("fr", "Français"),
    ("es", "Español"),
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
# BA-ZIP-WORKER-001: the regular worker consumes only default/celery; the
# isolated zip-worker consumes only the `zip` queue (see compose.yml).
CELERY_TASK_QUEUES = (
    Queue("default", Exchange("default", type="direct"), routing_key="default"),
    Queue("celery", Exchange("celery", type="direct"), routing_key="celery"),
    Queue("zip", Exchange("zip", type="direct"), routing_key="zip"),
)
CELERY_TASK_ROUTES = {
    "apps.pipeline.tasks.extract_zip_task": {"queue": "zip"},
    "apps.pipeline.tasks.cleanup_zip_staging": {"queue": "zip"},
}
CELERY_TASK_ANNOTATIONS = {
    "apps.pipeline.tasks.extract_zip_task": {
        "acks_late": True,
        "reject_on_worker_lost": True,
        "soft_time_limit": 55,
        "time_limit": 60,
    },
    "apps.pipeline.tasks.cleanup_zip_staging": {
        "acks_late": True,
        "reject_on_worker_lost": True,
        "soft_time_limit": 240,
        "time_limit": 300,
    },
    "apps.pipeline.tasks.cleanup_zip_uploads": {
        "acks_late": True,
        "reject_on_worker_lost": True,
        "soft_time_limit": 240,
        "time_limit": 300,
    },
    "apps.pipeline.tasks.reap_stale_zip_jobs": {
        "acks_late": True,
        "reject_on_worker_lost": True,
        "soft_time_limit": 240,
        "time_limit": 300,
    },
    "apps.pipeline.tasks.cleanup_orphan_runtimes": {
        "acks_late": True,
        "reject_on_worker_lost": True,
        "soft_time_limit": 240,
        "time_limit": 300,
    },
}
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
    "accounts-anonymize-due": {
        "task": "accounts.anonymize_due_accounts",
        "schedule": 60 * 60 * 24,
        "options": {"expires": 60 * 60},
    },
    "accounts-cleanup-expired": {
        "task": "accounts.cleanup_expired_account_records",
        "schedule": 60 * 60 * 24,
        "options": {"expires": 60 * 60},
    },
    "gameplay-cleanup-retention": {
        "task": "apps.gameplay.tasks.cleanup_gameplay_retention",
        "schedule": 60 * 60 * 24,
        "options": {"expires": 60 * 60},
    },
    "gameplay-expire-stale-sessions": {
        "task": "apps.gameplay.tasks.expire_stale_sessions",
        "schedule": 60 * 5,
        "options": {"expires": 60 * 4},
    },
    "pipeline-cleanup-retention": {
        "task": "apps.pipeline.tasks.cleanup_pipeline_retention",
        "schedule": 60 * 60 * 24,
        "options": {"expires": 60 * 60},
    },
    "catalog-refresh-search-vectors": {
        "task": "catalog.refresh_catalog_search_vectors",
        "schedule": 60 * 60 * 24,
        "options": {"expires": 60 * 60},
    },
    "pipeline-cleanup-zip-staging": {
        "task": "apps.pipeline.tasks.cleanup_zip_staging",
        "schedule": 60 * 60,
        "options": {"queue": "zip", "expires": 60 * 10},
    },
    "pipeline-cleanup-zip-uploads": {
        "task": "apps.pipeline.tasks.cleanup_zip_uploads",
        "schedule": 60 * 60,
        "options": {"expires": 60 * 10},
    },
    "pipeline-reap-stale-zip-jobs": {
        "task": "apps.pipeline.tasks.reap_stale_zip_jobs",
        "schedule": 60 * 5,
        "options": {"expires": 60 * 4},
    },
    "pipeline-cleanup-orphan-runtimes": {
        "task": "apps.pipeline.tasks.cleanup_orphan_runtimes",
        "schedule": 60 * 60 * 24,
        "options": {"expires": 60 * 60},
    },
}

# --- DRF ----------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    # Deny-by-default (§2.20, §2.23): публичные endpoint'ы должны явно
    # объявлять AllowAny, а не получать его из глобальной настройки.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        # §2.12 / Приложение E: subject primary, IP secondary.
        # Создание сессий ограничено 30/час; activate/close имеют отдельные
        # бакеты с той же ставкой, чтобы не расходовать лимит создания.
        "sessions": "30/hour",
        "sessions_ip": "600/hour",
        "sessions_activate": "30/hour",
        "sessions_close": "30/hour",
        "results": "60/hour",
        "results_ip": "1200/hour",
        "heartbeat": "3/min",
        "storage": "600/hour",
        "storage_session": "60/min",
        # Read hardening for public leaderboards (Приложение E не задаёт ставку).
        "leaderboard_read": "120/min",
        "rating": "20/day",
        "rating_read": "120/min",
        # Жалобы: 5/сутки на субъект, 30/сутки на IP (Приложение E).
        "reports": "5/day",
        "reports_ip": "30/day",
    },
    "UNAUTHENTICATED_USER": "django.contrib.auth.models.AnonymousUser",
}

# --- Рейтинг: формула WR (§2.8) -----------------------------------------
# WR = (v / (v + m)) * R + (m / (v + m)) * C
RATING_WR_M = env_int("RATING_WR_M", 20)
RATING_WR_C = env_float("RATING_WR_C", 3.5)

# --- Константы пайплайна (§2.14.2) --------------------------------------
BA_SDK_DEFAULT_VERSION = env("BA_SDK_DEFAULT_VERSION", "1.1.0")
SDK_SOURCE_ROOT = Path(env("SDK_SOURCE_ROOT", str(BASE_DIR / "sdk")))
ZIP_MAX_BYTES = env_int("ZIP_MAX_BYTES", 26_214_400)
ZIP_PIPELINE_STORAGE_ROOT = Path(
    env("ZIP_PIPELINE_STORAGE_ROOT", str(BASE_DIR / "var" / "pipeline"))
)
ZIP_PUBLIC_RUNTIME_ROOT = Path(env("ZIP_PUBLIC_RUNTIME_ROOT", str(BASE_DIR / "var" / "runtime")))
CRITICAL_PATH_WARN_BYTES = env_int("CRITICAL_PATH_WARN_BYTES", 2_097_152)
CRITICAL_PATH_MAX_BYTES = env_int("CRITICAL_PATH_MAX_BYTES", 4_194_304)
ADMIN_URL_PREFIX = env("ADMIN_URL_PREFIX", "crm/")

# --- CRM step-up (§2.16.1, ADR-APPF-001 D11) ----------------------------
# Template window for password + TOTP elevation; a technical parameter until
# the product setting is approved.
CRM_STEP_UP_TTL_SECONDS = env_int("CRM_STEP_UP_TTL_SECONDS", 15 * 60)

# --- Резервное копирование (§2.5) --------------------------------------
BACKUP_DIR = env("BACKUP_DIR", "/app/var/backups")

# --- ZIP extraction worker (BA-ZIP-WORKER-001) --------------------------
# uploads: written by web (source ZIP + CANCEL), read-only in zip-worker.
# artifacts: written by zip-worker, read-only in web.
ZIP_UPLOADS_ROOT = Path(env("ZIP_UPLOADS_ROOT", "/var/ba/zip/uploads"))
ZIP_ARTIFACTS_ROOT = Path(env("ZIP_ARTIFACTS_ROOT", "/var/ba/zip/artifacts"))
ZIP_JOB_DEADLINE_SECONDS = env_int("ZIP_JOB_DEADLINE_SECONDS", 50)
ZIP_JOB_STALE_SECONDS = env_int("ZIP_JOB_STALE_SECONDS", 600)
ZIP_RUNTIME_ORPHAN_TTL_SECONDS = env_int("ZIP_RUNTIME_ORPHAN_TTL_SECONDS", 60 * 60 * 24)
ZIP_STAGING_TTL_SECONDS = env_int("ZIP_STAGING_TTL_SECONDS", 60 * 60)
ZIP_COMPLETED_TTL_SECONDS = env_int("ZIP_COMPLETED_TTL_SECONDS", 60 * 60 * 24)
ZIP_DISK_RESERVE_BYTES = env_int("ZIP_DISK_RESERVE_BYTES", 150 * 1024 * 1024)
ZIP_JOB_MAX_BYTES = env_int("ZIP_JOB_MAX_BYTES", 120 * 1024 * 1024)
# System-wide ZIP quota (ARCADE-P4-STORAGE-001, R-033/R-043). The quota covers
# uploads + artifacts + the private original-package store; published runtimes
# are explicitly excluded. State lives on a volume shared by web and
# zip-worker (compose.dev/staging/prod). Empty value = state under uploads
# (tests/dev single-container fallback).
_zip_quota_state = env("ZIP_QUOTA_STATE_ROOT", "")
ZIP_QUOTA_STATE_ROOT: Path | None = Path(_zip_quota_state) if _zip_quota_state else None
ZIP_STORAGE_QUOTA_BYTES = env_int("ZIP_STORAGE_QUOTA_BYTES", 2 * 1024 * 1024 * 1024)
ZIP_STORAGE_MIN_FREE_BYTES = env_int("ZIP_STORAGE_MIN_FREE_BYTES", ZIP_DISK_RESERVE_BYTES)
ZIP_QUOTA_RESERVATION_TTL_SECONDS = env_int("ZIP_QUOTA_RESERVATION_TTL_SECONDS", 60 * 60)
# Web-side poll budget for one import. It exceeds the worker's soft limit so
# worker timeouts surface as their own stable code instead of a client timeout.
ZIP_IMPORT_WAIT_SECONDS = env_int("ZIP_IMPORT_WAIT_SECONDS", 75)
ZIP_IMPORT_POLL_INTERVAL_SECONDS = env_float("ZIP_IMPORT_POLL_INTERVAL_SECONDS", 0.5)
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
