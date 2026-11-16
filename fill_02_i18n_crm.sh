#!/usr/bin/env bash
# =============================================================================
#  fill_02_i18n_crm.sh — этап 1, блок 2: i18n, тема, шаблоны, каркас CRM,
#  контент и каталог (BA-PLAT-4.2 §2.6, §2.7, §2.15, §2.16, §2.17, §2.19)
#  Запуск: bash fill_02_i18n_crm.sh [КАТАЛОГ] [--force] [--dry-run]
# =============================================================================
set -euo pipefail

TARGET="$PWD"; FORCE=0; DRY=0
for arg in "$@"; do
  case "$arg" in
    --force)   FORCE=1 ;;
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    -*) printf 'Неизвестный ключ: %s\n' "$arg" >&2; exit 2 ;;
    *) TARGET="$arg" ;;
  esac
done
cd "$TARGET"
if [[ ! -d apps/core || ! -d config/settings ]]; then
  printf 'Каталог %s не содержит ядра. Сначала выполните fill_01_core.sh\n' "$TARGET" >&2
  exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR=".backups/$STAMP"
filled=0; skipped=0; backed=0

write_file() {
  local rel="$1" tmp
  tmp="$(mktemp)"
  cat > "$tmp"
  if [[ -e "$rel" && -s "$rel" && $FORCE -eq 0 ]]; then
    printf '  SKIP  %s\n' "$rel"; skipped=$((skipped+1)); rm -f "$tmp"; return
  fi
  if (( DRY )); then
    printf '  FILL  %s\n' "$rel"; filled=$((filled+1)); rm -f "$tmp"; return
  fi
  mkdir -p -- "$(dirname -- "$rel")"
  if [[ -e "$rel" && -s "$rel" ]]; then
    mkdir -p -- "$BACKUP_DIR/$(dirname -- "$rel")"
    cp -p -- "$rel" "$BACKUP_DIR/$rel"; backed=$((backed+1))
  fi
  mv -f -- "$tmp" "$rel"
  case "$rel" in *.sh) chmod 755 "$rel" ;; *) chmod 644 "$rel" ;; esac
  printf '  OK    %s\n' "$rel"; filled=$((filled+1))
}

# =============================================================================
#  i18n: модели
# =============================================================================
write_file apps/i18n/apps.py <<'BA_EOF'
from django.apps import AppConfig


class I18nConfig(AppConfig):
    name = "apps.i18n"
    label = "i18n"
    verbose_name = "Интернационализация"
BA_EOF

write_file apps/i18n/models/language.py <<'BA_EOF'
from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7, CitextField
from apps.core.ids import uuid7


class Language(models.Model):
    """Активный язык портала. Источник для URL-префиксов, sitemap и hreflang."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    code = CitextField(max_length=8, unique=True, help_text="ISO 639-1, например 'en', 'de', 'nl'.")
    name = models.CharField(max_length=64, help_text="Отображаемое название на самом языке.")
    native_name = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_rtl = models.BooleanField(default=False)
    sort_order = models.PositiveSmallIntegerField(default=0)
    plural_rule = models.CharField(
        max_length=16,
        default="other",
        help_text="CLDR plural rule: one, few, many, other и т.д.",
    )
    fts_config = models.CharField(
        max_length=64,
        blank=True,
        help_text="PostgreSQL FTS конфигурация. Пусто = simple + unaccent + pg_trgm.",
    )
    ui_ready_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Момент, когда 100% строк интерфейса переведено и опубликовано.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "i18n_language"
        ordering = ["sort_order", "code"]
        verbose_name = "Язык"
        verbose_name_plural = "Языки"

    def __str__(self) -> str:
        return f"{self.code} ({self.name})"

    @property
    def is_fully_ready(self) -> bool:
        return self.is_active and self.ui_ready_at is not None
BA_EOF

write_file apps/i18n/models/entry.py <<'BA_EOF'
from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7, CitextField
from apps.core.ids import uuid7


class TranslationEntry(models.Model):
    """Строка интерфейса портала. namespace+key+language уникальны."""

    STATUS_DRAFT = "draft"
    STATUS_REVIEW = "review"
    STATUS_APPROVED = "approved"
    STATUS_PUBLISHED = "published"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Черновик"),
        (STATUS_REVIEW, "На проверке"),
        (STATUS_APPROVED, "Проверено"),
        (STATUS_PUBLISHED, "Опубликовано"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    namespace = CitextField(max_length=64, db_index=True)
    key = CitextField(max_length=128)
    language = models.ForeignKey(
        "i18n.Language",
        on_delete=models.CASCADE,
        related_name="translations",
    )
    value = models.TextField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    is_machine_translated = models.BooleanField(default=False)
    updated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="translation_edits",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "i18n_translation_entry"
        unique_together = [("namespace", "key", "language")]
        verbose_name = "Перевод интерфейса"
        verbose_name_plural = "Переводы интерфейса"

    def __str__(self) -> str:
        return f"{self.namespace}.{self.key} [{self.language.code}]"
BA_EOF

write_file apps/i18n/models/game_override.py <<'BA_EOF'
from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7, CitextField
from apps.core.ids import uuid7


class GameLocaleOverride(models.Model):
    """Переопределение строки игры из CRM. Приоритетнее пакета."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    game = models.ForeignKey(
        "catalog.Game",
        on_delete=models.CASCADE,
        related_name="locale_overrides",
    )
    language = models.ForeignKey(
        "i18n.Language",
        on_delete=models.CASCADE,
        related_name="game_overrides",
    )
    key = CitextField(max_length=128)
    value = models.TextField()
    status = models.CharField(max_length=16, default="published")
    updated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "i18n_game_locale_override"
        unique_together = [("game", "language", "key")]
        verbose_name = "Переопределение локали игры"
        verbose_name_plural = "Переопределения локалей игр"

    def __str__(self) -> str:
        return f"{self.game} [{self.language.code}] {self.key}"
BA_EOF

write_file apps/i18n/models/__init__.py <<'BA_EOF'
from .entry import TranslationEntry
from .game_override import GameLocaleOverride
from .language import Language

__all__ = ["Language", "TranslationEntry", "GameLocaleOverride"]
BA_EOF

# =============================================================================
#  i18n: сервисы
# =============================================================================
write_file apps/i18n/services/dictionary.py <<'BA_EOF'
"""Сборка словаря интерфейса для шаблонов. Кеш Redis, инвалидация по сигналу."""
from __future__ import annotations

from typing import Any

from django.core.cache import cache

from apps.i18n.models import Language, TranslationEntry

CACHE_KEY = "i18n:dictionary:{code}"
CACHE_TTL = 3600


def get_dictionary(language: Language) -> dict[str, dict[str, str]]:
    """Возвращает {namespace: {key: value}} для опубликованных переводов."""
    key = CACHE_KEY.format(code=language.code)
    cached = cache.get(key)
    if cached is not None:
        return cached

    entries = TranslationEntry.objects.filter(
        language=language,
        status=TranslationEntry.STATUS_PUBLISHED,
    ).values_list("namespace", "key", "value")

    result: dict[str, dict[str, str]] = {}
    for namespace, entry_key, value in entries:
        result.setdefault(namespace, {})[entry_key] = value

    cache.set(key, result, CACHE_TTL)
    return result


def translate(
    namespace: str,
    key: str,
    language: Language,
    params: dict[str, Any] | None = None,
    fallback: Language | None = None,
) -> str:
    """Перевод с резервным языком. Ключ никогда не показывается (§2.15)."""
    dictionary = get_dictionary(language)
    value = dictionary.get(namespace, {}).get(key)

    if value is None and fallback is not None and fallback.code != language.code:
        dictionary = get_dictionary(fallback)
        value = dictionary.get(namespace, {}).get(key)

    if value is None:
        # Логируем отсутствие перевода, но ключ не показываем.
        return ""

    if params:
        for param_key, param_value in params.items():
            value = value.replace(f"{{{param_key}}}", str(param_value))

    return value


def invalidate_language(language: Language) -> None:
    cache.delete(CACHE_KEY.format(code=language.code))
BA_EOF

write_file apps/i18n/services/coverage.py <<'BA_EOF'
"""Процент покрытия переводами для языка или игры."""
from __future__ import annotations

from apps.i18n.models import Language, TranslationEntry


def language_coverage(language: Language) -> tuple[int, int]:
    """Возвращает (переведено, всего) для всех ключей всех namespace."""
    total = (
        TranslationEntry.objects.filter(language__is_active=True)
        .values("namespace", "key")
        .distinct()
        .count()
    )
    translated = (
        TranslationEntry.objects.filter(
            language=language,
            status=TranslationEntry.STATUS_PUBLISHED,
        )
        .values("namespace", "key")
        .distinct()
        .count()
    )
    return translated, total


def language_coverage_percent(language: Language) -> int:
    translated, total = language_coverage(language)
    if total == 0:
        return 100
    return int(translated * 100 / total)
BA_EOF

write_file apps/i18n/services/plural.py <<'BA_EOF'
"""Плюрализация по CLDR через Babel."""
from __future__ import annotations

from babel.plural import to_python


def plural_form(count: int, language_code: str) -> str:
    """Возвращает CLDR-форму: one, few, many, other."""
    try:
        func = to_python(language_code)
        return func(count)
    except Exception:
        return "other"
BA_EOF

write_file apps/i18n/services/__init__.py <<'BA_EOF'
from .coverage import language_coverage, language_coverage_percent
from .dictionary import get_dictionary, invalidate_language, translate
from .plural import plural_form

__all__ = [
    "get_dictionary",
    "translate",
    "invalidate_language",
    "language_coverage",
    "language_coverage_percent",
    "plural_form",
]
BA_EOF

# =============================================================================
#  i18n: middleware, context_processors, templatetags
# =============================================================================
write_file apps/i18n/middleware.py <<'BA_EOF'
"""Языковой префикс URL из активных языков БД (§2.6, §2.15)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.utils import translation

if TYPE_CHECKING:
    from collections.abc import Callable

    from apps.i18n.models import Language

CACHE_KEY = "i18n:active_codes"
CACHE_TTL = 600

GetResponse = Callable[[HttpRequest], HttpResponse]


def get_active_language_codes() -> list[str]:
    codes = cache.get(CACHE_KEY)
    if codes is not None:
        return codes
    from apps.i18n.models import Language

    codes = list(
        Language.objects.filter(is_active=True)
        .order_by("sort_order", "code")
        .values_list("code", flat=True)
    )
    cache.set(CACHE_KEY, codes, CACHE_TTL)
    return codes


def get_active_languages() -> list[Language]:
    from apps.i18n.models import Language

    return list(Language.objects.filter(is_active=True).order_by("sort_order", "code"))


class LanguagePrefixMiddleware:
    """Определяет язык из URL-префикса /<lang>/, выставляет translation и request.language."""

    def __init__(self, get_response: GetResponse) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        path = request.path_info
        codes = get_active_language_codes()
        language_code = settings.LANGUAGE_CODE

        # Проверяем префикс /<lang>/
        if path.startswith("/"):
            parts = path[1:].split("/", 1)
            if parts and parts[0] in codes:
                language_code = parts[0]

        translation.activate(language_code)
        request.LANGUAGE_CODE = language_code  # type: ignore[attr-defined]

        response = self.get_response(request)
        translation.deactivate()
        return response


def invalidate_language_cache() -> None:
    cache.delete(CACHE_KEY)
BA_EOF

write_file apps/i18n/context_processors.py <<'BA_EOF'
"""Контекст для шаблонов: активные языки, текущий язык."""
from __future__ import annotations

from django.http import HttpRequest

from apps.i18n.middleware import get_active_languages


def i18n(request: HttpRequest) -> dict[str, object]:
    current_code = getattr(request, "LANGUAGE_CODE", "en")
    languages = get_active_languages()
    current = next((lang for lang in languages if lang.code == current_code), None)

    return {
        "active_languages": languages,
        "current_language": current,
        "current_language_code": current_code,
    }
BA_EOF

write_file apps/i18n/templatetags/__init__.py <<'BA_EOF'
BA_EOF

write_file apps/i18n/templatetags/ba_i18n.py <<'BA_EOF'
"""Шаблонный тег {% ba_t "namespace.key" param=value %} (§2.15)."""
from __future__ import annotations

from typing import Any

from django import template
from django.http import HttpRequest

from apps.i18n.middleware import get_active_languages
from apps.i18n.services import translate

register = template.Library()


@register.simple_tag(takes_context=True)
def ba_t(context: dict[str, Any], full_key: str, **params: Any) -> str:
    """Перевод строки интерфейса. Ключ никогда не показывается."""
    request: HttpRequest | None = context.get("request")
    if request is None:
        return ""

    parts = full_key.split(".", 1)
    if len(parts) != 2:
        return ""
    namespace, key = parts

    current_code = getattr(request, "LANGUAGE_CODE", "en")
    languages = get_active_languages()
    current = next((lang for lang in languages if lang.code == current_code), None)
    fallback = next((lang for lang in languages if lang.code == "en"), None)

    if current is None:
        return ""

    return translate(namespace, key, current, params=params, fallback=fallback)


@register.simple_tag(takes_context=True)
def ba_lang_switcher(context: dict[str, Any]) -> str:
    """HTML-разметка переключателя языков."""
    request: HttpRequest | None = context.get("request")
    if request is None:
        return ""

    languages = get_active_languages()
    current_code = getattr(request, "LANGUAGE_CODE", "en")

    items = []
    for lang in languages:
        active = "active" if lang.code == current_code else ""
        items.append(
            f'<a href="/{lang.code}/{request.path_info.lstrip("/").lstrip(current_code + "/")}" '
            f'class="lang-switcher__item {active}" lang="{lang.code}">{lang.name}</a>'
        )

    return f'<div class="lang-switcher">{"".join(items)}</div>'
BA_EOF

# =============================================================================
#  i18n: миграция с начальными языками
# =============================================================================
write_file apps/i18n/migrations/0001_initial.py <<'BA_EOF'
"""Начальные языки портала (§2.15)."""
from django.db import migrations, models

INITIAL_LANGUAGES = [
    ("en", "English", "English", False, 1, "english"),
    ("de", "Deutsch", "Deutsch", False, 2, "german"),
    ("nl", "Nederlands", "Nederlands", False, 3, "dutch"),
    ("ru", "Русский", "Русский", False, 4, "russian"),
    ("fr", "Français", "Français", False, 5, "french"),
    ("es", "Español", "Español", False, 6, "spanish"),
]


def create_initial_languages(apps, schema_editor):
    Language = apps.get_model("i18n", "Language")
    for code, name, native_name, is_rtl, sort_order, fts_config in INITIAL_LANGUAGES:
        Language.objects.create(
            code=code,
            name=name,
            native_name=native_name,
            is_active=True,
            is_rtl=is_rtl,
            sort_order=sort_order,
            plural_rule="other",
            fts_config=fts_config,
            ui_ready_at=None,
        )


class Migration(migrations.Migration):
    initial = True
    dependencies = [("i18n", "0000_initial")]
    operations = [migrations.RunPython(create_initial_languages, migrations.RunPython.noop)]
BA_EOF

write_file apps/i18n/migrations/0000_initial.py <<'BA_EOF'
from django.db import migrations, models
import django.db.models.deletion
import apps.core.fields
import apps.core.ids


class Migration(migrations.Migration):
    initial = True
    dependencies = [("accounts", "0001_initial"), ("catalog", "0000_initial")]
    operations = [
        migrations.CreateModel(
            name="Language",
            fields=[
                ("id", models.UUIDField(db_default=apps.core.fields.UUID7(), default=apps.core.ids.uuid7, editable=False, primary_key=True, serialize=False)),
                ("code", apps.core.fields.CitextField(help_text="ISO 639-1, например 'en', 'de', 'nl'.", max_length=8, unique=True)),
                ("name", models.CharField(help_text="Отображаемое название на самом языке.", max_length=64)),
                ("native_name", models.CharField(blank=True, max_length=64)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("is_rtl", models.BooleanField(default=False)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("plural_rule", models.CharField(default="other", help_text="CLDR plural rule: one, few, many, other и т.д.", max_length=16)),
                ("fts_config", models.CharField(blank=True, help_text="PostgreSQL FTS конфигурация. Пусто = simple + unaccent + pg_trgm.", max_length=64)),
                ("ui_ready_at", models.DateTimeField(blank=True, help_text="Момент, когда 100% строк интерфейса переведено и опубликовано.", null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "i18n_language", "ordering": ["sort_order", "code"], "verbose_name": "Язык", "verbose_name_plural": "Языки"},
        ),
        migrations.CreateModel(
            name="TranslationEntry",
            fields=[
                ("id", models.UUIDField(db_default=apps.core.fields.UUID7(), default=apps.core.ids.uuid7, editable=False, primary_key=True, serialize=False)),
                ("namespace", apps.core.fields.CitextField(db_index=True, max_length=64)),
                ("key", apps.core.fields.CitextField(max_length=128)),
                ("value", models.TextField()),
                ("status", models.CharField(choices=[("draft", "Черновик"), ("review", "На проверке"), ("approved", "Проверено"), ("published", "Опубликовано")], default="draft", max_length=16)),
                ("is_machine_translated", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("language", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="translations", to="i18n.language")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="translation_edits", to="accounts.user")),
            ],
            options={"db_table": "i18n_translation_entry", "unique_together": {("namespace", "key", "language")}, "verbose_name": "Перевод интерфейса", "verbose_name_plural": "Переводы интерфейса"},
        ),
        migrations.CreateModel(
            name="GameLocaleOverride",
            fields=[
                ("id", models.UUIDField(db_default=apps.core.fields.UUID7(), default=apps.core.ids.uuid7, editable=False, primary_key=True, serialize=False)),
                ("key", apps.core.fields.CitextField(max_length=128)),
                ("value", models.TextField()),
                ("status", models.CharField(default="published", max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("language", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="game_overrides", to="i18n.language")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="accounts.user")),
            ],
            options={"db_table": "i18n_game_locale_override", "unique_together": {("game", "language", "key")}, "verbose_name": "Переопределение локали игры", "verbose_name_plural": "Переопределения локалей игр"},
        ),
    ]
BA_EOF

# =============================================================================
#  Тема: модели
# =============================================================================
write_file apps/theme/apps.py <<'BA_EOF'
from django.apps import AppConfig


class ThemeConfig(AppConfig):
    name = "apps.theme"
    label = "theme"
    verbose_name = "Тема и дизайн-система"
BA_EOF

write_file apps/theme/models/tokens.py <<'BA_EOF'
from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7
from apps.core.ids import uuid7


class ThemeTokenSet(models.Model):
    """Набор дизайн-токенов из CRM. Генерирует /theme-<hash>.css (§2.7)."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    version = models.PositiveIntegerField(default=1)
    tokens = models.JSONField(help_text="CSS-переменные: {--ba-bg: '#0f1115', ...}")
    hash = models.CharField(max_length=16, unique=True, db_index=True)
    is_active = models.BooleanField(default=False)
    updated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "theme_token_set"
        verbose_name = "Набор токенов темы"
        verbose_name_plural = "Наборы токенов темы"

    def __str__(self) -> str:
        return f"Theme v{self.version} ({self.hash})"
BA_EOF

write_file apps/theme/models/site_settings.py <<'BA_EOF'
from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7
from apps.core.ids import uuid7


class SiteSettings(models.Model):
    """Глобальные настройки портала."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    logo = models.ImageField(upload_to="site/logo/", blank=True)
    favicon = models.ImageField(upload_to="site/favicon/", blank=True)
    contacts = models.JSONField(default=dict, blank=True)
    counter_config = models.JSONField(default=dict, blank=True)
    default_theme = models.CharField(max_length=16, default="dark")
    reserved_host_labels = models.JSONField(
        default=list,
        blank=True,
        help_text="Зарезервированные метки игровых хостов (§2.4.1).",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "theme_site_settings"
        verbose_name = "Настройки сайта"
        verbose_name_plural = "Настройки сайта"

    def __str__(self) -> str:
        return "SiteSettings"
BA_EOF

write_file apps/theme/models/__init__.py <<'BA_EOF'
from .site_settings import SiteSettings
from .tokens import ThemeTokenSet

__all__ = ["ThemeTokenSet", "SiteSettings"]
BA_EOF

# =============================================================================
#  Тема: сервисы
# =============================================================================
write_file apps/theme/services/compiler.py <<'BA_EOF'
"""Генерация CSS-файла темы из токенов (§2.7)."""
from __future__ import annotations

import hashlib
import json

from apps.theme.models import ThemeTokenSet


def compile_theme_css(tokens: dict[str, str]) -> str:
    """Возвращает CSS с :root { ... } из словаря токенов."""
    lines = [":root {"]
    for key, value in sorted(tokens.items()):
        if not key.startswith("--"):
            key = f"--{key}"
        lines.append(f"  {key}: {value};")
    lines.append("}")
    return "\n".join(lines)


def compute_theme_hash(css: str) -> str:
    """SHA-256 первых 16 символов."""
    return hashlib.sha256(css.encode("utf-8")).hexdigest()[:16]


def get_active_theme_css() -> tuple[str, str]:
    """Возвращает (hash, css) активной темы."""
    theme = ThemeTokenSet.objects.filter(is_active=True).first()
    if theme is None:
        # Значения по умолчанию из static/src/css/tokens.css
        default_tokens = {
            "--ba-bg": "#0f1115",
            "--ba-surface": "#171a21",
            "--ba-text": "#e8eaf0",
            "--ba-muted": "#9aa3b2",
            "--ba-accent": "#39ff88",
            "--ba-danger": "#ff5c72",
            "--ba-radius-card": "14px",
            "--ba-space-unit": "4px",
            "--ba-font-body": 'system-ui, "Segoe UI", Roboto, sans-serif',
            "--ba-font-display": '"Segoe UI", system-ui, sans-serif',
        }
        css = compile_theme_css(default_tokens)
        return compute_theme_hash(css), css

    return theme.hash, compile_theme_css(theme.tokens)
BA_EOF

write_file apps/theme/services/__init__.py <<'BA_EOF'
from .compiler import compile_theme_css, compute_theme_hash, get_active_theme_css

__all__ = ["compile_theme_css", "compute_theme_hash", "get_active_theme_css"]
BA_EOF

# =============================================================================
#  Тема: views
# =============================================================================
write_file apps/theme/views.py <<'BA_EOF'
"""Раздача /theme-<hash>.css с immutable-кешем (§2.7)."""
from __future__ import annotations

from django.http import HttpRequest, HttpResponse, HttpResponseNotFound

from apps.theme.services import get_active_theme_css


def theme_css(request: HttpRequest, hash: str) -> HttpResponse:
    """Возвращает CSS темы с кешем public, max-age=31536000, immutable."""
    active_hash, css = get_active_theme_css()

    if hash != active_hash:
        return HttpResponseNotFound("Theme not found")

    response = HttpResponse(css, content_type="text/css; charset=utf-8")
    response["Cache-Control"] = "public, max-age=31536000, immutable"
    return response
BA_EOF

write_file apps/theme/urls.py <<'BA_EOF'
from django.urls import path

from apps.theme import views

app_name = "theme"

urlpatterns = [
    path("theme-<str:hash>.css", views.theme_css, name="theme_css"),
]
BA_EOF

write_file apps/theme/context_processors.py <<'BA_EOF'
"""Контекст для шаблонов: URL файла темы."""
from __future__ import annotations

from django.http import HttpRequest

from apps.theme.services import get_active_theme_css


def theme(request: HttpRequest) -> dict[str, object]:
    active_hash, _ = get_active_theme_css()
    return {
        "theme_css_url": f"/theme-{active_hash}.css",
    }
BA_EOF

# =============================================================================
#  Шаблоны: base.html
# =============================================================================
write_file templates/base.html <<'BA_EOF'
<!DOCTYPE html>
<html lang="{{ current_language_code }}" {% if current_language.is_rtl %}dir="rtl"{% endif %}>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="theme-color" content="#0f1115">
    <title>{% block title %}Breaktime Arcade{% endblock %}</title>

    <link rel="stylesheet" href="{{ theme_css_url }}">
    <link rel="stylesheet" href="/static/dist/app.css">

    {% block extra_head %}{% endblock %}

    <script nonce="{{ csp_nonce }}">
        // Тема из cookie до загрузки DOM
        const theme = document.cookie.split('; ').find(row => row.startsWith('ba_theme='));
        if (theme) {
            document.documentElement.dataset.theme = theme.split('=')[1];
        }
    </script>
</head>
<body class="bg-bg text-text font-body">
    <a href="#main-content" class="sr-only focus:not-sr-only">
        {% load ba_i18n %}{% ba_t "ui.skip_to_content" %}
    </a>

    {% include "partials/header.html" %}

    <main id="main-content" class="min-h-[calc(100dvh-8rem)]">
        {% include "partials/messages.html" %}
        {% block content %}{% endblock %}
    </main>

    {% include "partials/footer.html" %}

    <script src="/static/dist/vendor/htmx.min.js" nonce="{{ csp_nonce }}"></script>
    <script type="module" src="/static/src/js/main.js" nonce="{{ csp_nonce }}"></script>
    {% block extra_js %}{% endblock %}
</body>
</html>
BA_EOF

write_file templates/partials/header.html <<'BA_EOF'
<header class="bg-surface border-b border-text/10">
    <div class="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
        <div class="flex items-center gap-6">
            <a href="/{{ current_language_code }}/" class="text-xl font-display font-bold text-accent">
                Breaktime Arcade
            </a>
            <nav class="hidden md:flex gap-4">
                <a href="/{{ current_language_code }}/games/" class="hover:text-accent">
                    {% load ba_i18n %}{% ba_t "nav.games" %}
                </a>
                <a href="/{{ current_language_code }}/genres/" class="hover:text-accent">
                    {% ba_t "nav.genres" %}
                </a>
            </nav>
        </div>

        <div class="flex items-center gap-4">
            {% include "partials/language_switcher.html" %}
            {% include "partials/theme_toggle.html" %}

            {% if user.is_authenticated %}
                <a href="/{{ current_language_code }}/account/" class="hover:text-accent">
                    {{ user.profile.nickname }}
                </a>
            {% else %}
                <a href="/{{ current_language_code }}/auth/login/" class="hover:text-accent">
                    {% ba_t "auth.login" %}
                </a>
                <a href="/{{ current_language_code }}/auth/register/" class="btn btn-primary">
                    {% ba_t "auth.register" %}
                </a>
            {% endif %}
        </div>
    </div>
</header>
BA_EOF

write_file templates/partials/footer.html <<'BA_EOF'
<footer class="bg-surface border-t border-text/10 mt-auto">
    <div class="max-w-7xl mx-auto px-4 py-8">
        <div class="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div>
                <h3 class="font-display font-bold mb-4">Breaktime Arcade</h3>
                <p class="text-muted text-sm">
                    {% load ba_i18n %}{% ba_t "footer.tagline" %}
                </p>
            </div>
            <div>
                <h4 class="font-semibold mb-2">{% ba_t "footer.legal" %}</h4>
                <ul class="space-y-1 text-sm">
                    <li><a href="/{{ current_language_code }}/legal/terms/" class="hover:text-accent">{% ba_t "legal.terms" %}</a></li>
                    <li><a href="/{{ current_language_code }}/legal/privacy/" class="hover:text-accent">{% ba_t "legal.privacy" %}</a></li>
                    <li><a href="/{{ current_language_code }}/legal/cookies/" class="hover:text-accent">{% ba_t "legal.cookies" %}</a></li>
                </ul>
            </div>
            <div>
                <h4 class="font-semibold mb-2">{% ba_t "footer.contact" %}</h4>
                <p class="text-muted text-sm">
                    {% ba_t "footer.email" %}
                </p>
            </div>
        </div>
        <div class="mt-8 pt-4 border-t border-text/10 text-center text-muted text-sm">
            © 2026 Breaktime Arcade. {% ba_t "footer.rights" %}
        </div>
    </div>
</footer>
BA_EOF

write_file templates/partials/language_switcher.html <<'BA_EOF'
<div class="relative">
    <button type="button" class="flex items-center gap-2 hover:text-accent" data-dropdown-toggle="lang-menu">
        {{ current_language.name }}
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
        </svg>
    </button>
    <div id="lang-menu" class="hidden absolute right-0 mt-2 w-40 bg-surface border border-text/10 rounded-lg shadow-lg z-50">
        {% for lang in active_languages %}
            <a href="/{{ lang.code }}/{{ request.path_info|slice:'4:' }}"
               class="block px-4 py-2 hover:bg-text/5 {% if lang.code == current_language_code %}text-accent{% endif %}">
                {{ lang.name }}
            </a>
        {% endfor %}
    </div>
</div>
BA_EOF

write_file templates/partials/theme_toggle.html <<'BA_EOF'
<button type="button"
        data-theme-toggle
        class="p-2 hover:text-accent"
        aria-label="Toggle theme">
    <svg class="w-5 h-5 hidden dark:block" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"/>
    </svg>
    <svg class="w-5 h-5 block dark:hidden" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/>
    </svg>
</button>
BA_EOF

write_file templates/partials/messages.html <<'BA_EOF'
{% if messages %}
    <div class="max-w-7xl mx-auto px-4 py-4 space-y-2">
        {% for message in messages %}
            <div class="p-4 rounded-lg bg-surface border border-text/10 {% if message.tags %}border-{{ message.tags }}{% endif %}">
                {{ message }}
            </div>
        {% endfor %}
    </div>
{% endif %}
BA_EOF

write_file templates/components/button.html <<'BA_EOF'
<button type="{{ type|default:'button' }}"
        class="btn {% if variant %}btn-{{ variant }}{% else %}btn-primary{% endif %} {% if size %}btn-{{ size }}{% endif %} {{ class }}"
        {% if disabled %}disabled{% endif %}>
    {{ slot }}
</button>
BA_EOF

write_file templates/components/field.html <<'BA_EOF'
<div class="field">
    {% if label %}
        <label for="{{ id }}" class="field__label">{{ label }}</label>
    {% endif %}
    <input type="{{ type|default:'text' }}"
           id="{{ id }}"
           name="{{ name }}"
           value="{{ value|default:'' }}"
           class="field__input {% if error %}field__input--error{% endif %}"
           {% if required %}required{% endif %}
           {% if placeholder %}placeholder="{{ placeholder }}"{% endif %}>
    {% if error %}
        <p class="field__error">{{ error }}</p>
    {% endif %}
    {% if help_text %}
        <p class="field__help">{{ help_text }}</p>
    {% endif %}
</div>
BA_EOF

write_file templates/components/table.html <<'BA_EOF'
<div class="overflow-x-auto">
    <table class="table w-full">
        <thead>
            <tr>
                {% for header in headers %}
                    <th class="table__th">{{ header }}</th>
                {% endfor %}
            </tr>
        </thead>
        <tbody>
            {% for row in rows %}
                <tr class="table__tr">
                    {% for cell in row %}
                        <td class="table__td">{{ cell }}</td>
                    {% endfor %}
                </tr>
            {% empty %}
                <tr>
                    <td colspan="{{ headers|length }}" class="table__td text-center text-muted">
                        {% load ba_i18n %}{% ba_t "ui.no_data" %}
                    </td>
                </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
BA_EOF

write_file templates/components/modal.html <<'BA_EOF'
<div class="modal" id="{{ id }}" role="dialog" aria-modal="true" aria-labelledby="{{ id }}-title">
    <div class="modal__overlay"></div>
    <div class="modal__content">
        <div class="modal__header">
            <h2 id="{{ id }}-title" class="modal__title">{{ title }}</h2>
            <button type="button" class="modal__close" data-modal-close>&times;</button>
        </div>
        <div class="modal__body">
            {{ slot }}
        </div>
        {% if footer %}
            <div class="modal__footer">
                {{ footer }}
            </div>
        {% endif %}
    </div>
</div>
BA_EOF

write_file templates/components/toast.html <<'BA_EOF'
<div class="toast toast-{{ variant|default:'info' }}" role="alert">
    <div class="toast__content">
        {% if icon %}
            <span class="toast__icon">{{ icon }}</span>
        {% endif %}
        <p class="toast__message">{{ message }}</p>
    </div>
    <button type="button" class="toast__close" data-toast-close>&times;</button>
</div>
BA_EOF

write_file templates/components/skeleton.html <<'BA_EOF'
<div class="skeleton {% if variant %}skeleton-{{ variant }}{% endif %}"
     style="{% if width %}width: {{ width }};{% endif %} {% if height %}height: {{ height }};{% endif %}">
</div>
BA_EOF

write_file templates/components/game_card.html <<'BA_EOF'
<a href="/{{ current_language_code }}/games/{{ game.slug }}/" class="game-card group">
    <div class="game-card__image">
        {% if game.cover %}
            <img src="{{ game.cover.url }}"
                 alt="{{ game.cover_alt }}"
                 loading="lazy"
                 class="w-full h-full object-cover">
        {% else %}
            <div class="w-full h-full bg-text/10 flex items-center justify-center">
                <span class="text-muted">{% load ba_i18n %}{% ba_t "ui.no_cover" %}</span>
            </div>
        {% endif %}
    </div>
    <div class="game-card__body">
        <h3 class="game-card__title group-hover:text-accent">{{ game.name }}</h3>
        <p class="game-card__description">{{ game.short_description }}</p>
        <div class="game-card__meta">
            <span class="game-card__genre">{{ game.primary_genre.name }}</span>
            {% if game.avg_rating %}
                <span class="game-card__rating">★ {{ game.avg_rating|floatformat:1 }}</span>
            {% endif %}
        </div>
    </div>
</a>
BA_EOF

write_file templates/components/stepper.html <<'BA_EOF'
<div class="stepper">
    {% for step in steps %}
        <div class="stepper__step {% if step.active %}stepper__step--active{% endif %} {% if step.completed %}stepper__step--completed{% endif %}">
            <div class="stepper__indicator">
                {% if step.completed %}
                    <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/>
                    </svg>
                {% else %}
                    {{ forloop.counter }}
                {% endif %}
            </div>
            <div class="stepper__label">{{ step.label }}</div>
        </div>
        {% if not forloop.last %}
            <div class="stepper__connector"></div>
        {% endif %}
    {% endfor %}
</div>
BA_EOF

write_file templates/components/validation_row.html <<'BA_EOF'
<div class="validation-row validation-row-{{ severity }}">
    <div class="validation-row__icon">
        {% if severity == 'blocker' %}
            <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>
            </svg>
        {% elif severity == 'warning' %}
            <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>
            </svg>
        {% else %}
            <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/>
            </svg>
        {% endif %}
    </div>
    <div class="validation-row__content">
        <div class="validation-row__header">
            <span class="validation-row__code">{{ code }}</span>
            {% if file %}
                <span class="validation-row__file">{{ file }}</span>
            {% endif %}
        </div>
        <p class="validation-row__message">{{ message }}</p>
        {% if hint %}
            <p class="validation-row__hint">{{ hint }}</p>
        {% endif %}
    </div>
</div>
BA_EOF

write_file templates/components/diff_row.html <<'BA_EOF'
<div class="diff-row {% if conflict %}diff-row--conflict{% endif %}">
    <div class="diff-row__field">{{ field }}</div>
    <div class="diff-row__current">{{ current_value|default:"—" }}</div>
    <div class="diff-row__new">{{ new_value|default:"—" }}</div>
    <div class="diff-row__actions">
        {% if conflict %}
            <button type="button" class="btn btn-sm" data-diff-action="accept">
                {% load ba_i18n %}{% ba_t "crm.accept" %}
            </button>
            <button type="button" class="btn btn-sm" data-diff-action="keep">
                {% ba_t "crm.keep" %}
            </button>
        {% endif %}
    </div>
</div>
BA_EOF

write_file templates/components/pagination.html <<'BA_EOF'
{% if page_obj.has_other_pages %}
    <nav class="pagination" aria-label="Pagination">
        {% if page_obj.has_previous %}
            <a href="?page={{ page_obj.previous_page_number }}" class="pagination__link">
                {% load ba_i18n %}{% ba_t "ui.previous" %}
            </a>
        {% endif %}

        {% for num in page_obj.paginator.page_range %}
            {% if page_obj.number == num %}
                <span class="pagination__current">{{ num }}</span>
            {% elif num > page_obj.number|add:'-3' and num < page_obj.number|add:'3' %}
                <a href="?page={{ num }}" class="pagination__link">{{ num }}</a>
            {% endif %}
        {% endfor %}

        {% if page_obj.has_next %}
            <a href="?page={{ page_obj.next_page_number }}" class="pagination__link">
                {% ba_t "ui.next" %}
            </a>
        {% endif %}
    </nav>
{% endif %}
BA_EOF

write_file templates/errors/400.html <<'BA_EOF'
{% extends "base.html" %}
{% load ba_i18n %}

{% block title %}{% ba_t "error.400.title" %} — Breaktime Arcade{% endblock %}

{% block content %}
<div class="max-w-2xl mx-auto px-4 py-16 text-center">
    <h1 class="text-6xl font-display font-bold text-accent mb-4">400</h1>
    <h2 class="text-2xl font-semibold mb-4">{% ba_t "error.400.title" %}</h2>
    <p class="text-muted mb-8">{% ba_t "error.400.message" %}</p>
    <a href="/{{ current_language_code }}/" class="btn btn-primary">
        {% ba_t "ui.go_home" %}
    </a>
</div>
{% endblock %}
BA_EOF

write_file templates/errors/403.html <<'BA_EOF'
{% extends "base.html" %}
{% load ba_i18n %}

{% block title %}{% ba_t "error.403.title" %} — Breaktime Arcade{% endblock %}

{% block content %}
<div class="max-w-2xl mx-auto px-4 py-16 text-center">
    <h1 class="text-6xl font-display font-bold text-accent mb-4">403</h1>
    <h2 class="text-2xl font-semibold mb-4">{% ba_t "error.403.title" %}</h2>
    <p class="text-muted mb-8">{% ba_t "error.403.message" %}</p>
    <a href="/{{ current_language_code }}/" class="btn btn-primary">
        {% ba_t "ui.go_home" %}
    </a>
</div>
{% endblock %}
BA_EOF

write_file templates/errors/404.html <<'BA_EOF'
{% extends "base.html" %}
{% load ba_i18n %}

{% block title %}{% ba_t "error.404.title" %} — Breaktime Arcade{% endblock %}

{% block content %}
<div class="max-w-2xl mx-auto px-4 py-16 text-center">
    <h1 class="text-6xl font-display font-bold text-accent mb-4">404</h1>
    <h2 class="text-2xl font-semibold mb-4">{% ba_t "error.404.title" %}</h2>
    <p class="text-muted mb-8">{% ba_t "error.404.message" %}</p>
    <a href="/{{ current_language_code }}/" class="btn btn-primary">
        {% ba_t "ui.go_home" %}
    </a>
</div>
{% endblock %}
BA_EOF

write_file templates/errors/410.html <<'BA_EOF'
{% extends "base.html" %}
{% load ba_i18n %}

{% block title %}{% ba_t "error.410.title" %} — Breaktime Arcade{% endblock %}

{% block content %}
<div class="max-w-2xl mx-auto px-4 py-16 text-center">
    <h1 class="text-6xl font-display font-bold text-accent mb-4">410</h1>
    <h2 class="text-2xl font-semibold mb-4">{% ba_t "error.410.title" %}</h2>
    <p class="text-muted mb-8">{% ba_t "error.410.message" %}</p>
    <a href="/{{ current_language_code }}/" class="btn btn-primary">
        {% ba_t "ui.go_home" %}
    </a>
</div>
{% endblock %}
BA_EOF

write_file templates/errors/500.html <<'BA_EOF'
{% extends "base.html" %}
{% load ba_i18n %}

{% block title %}{% ba_t "error.500.title" %} — Breaktime Arcade{% endblock %}

{% block content %}
<div class="max-w-2xl mx-auto px-4 py-16 text-center">
    <h1 class="text-6xl font-display font-bold text-accent mb-4">500</h1>
    <h2 class="text-2xl font-semibold mb-4">{% ba_t "error.500.title" %}</h2>
    <p class="text-muted mb-8">{% ba_t "error.500.message" %}</p>
    <a href="/{{ current_language_code }}/" class="btn btn-primary">
        {% ba_t "ui.go_home" %}
    </a>
</div>
{% endblock %}
BA_EOF

write_file templates/emails/base.html <<'BA_EOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: system-ui, sans-serif; line-height: 1.6; color: #14161c; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background: #39ff88; padding: 20px; text-align: center; }
        .content { padding: 20px; background: #ffffff; }
        .footer { padding: 20px; text-align: center; font-size: 12px; color: #5a6270; }
        .btn { display: inline-block; padding: 12px 24px; background: #39ff88; color: #14161c; text-decoration: none; border-radius: 6px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Breaktime Arcade</h1>
        </div>
        <div class="content">
            {% block content %}{% endblock %}
        </div>
        <div class="footer">
            © 2026 Breaktime Arcade
        </div>
    </div>
</body>
</html>
BA_EOF

write_file templates/emails/confirm_email.html <<'BA_EOF'
{% extends "emails/base.html" %}

{% block content %}
<h2>Confirm your email</h2>
<p>Click the button below to confirm your email address:</p>
<p><a href="{{ confirmation_url }}" class="btn">Confirm Email</a></p>
<p>This link expires in 24 hours.</p>
<p>If you didn't request this, you can safely ignore this email.</p>
{% endblock %}
BA_EOF

write_file templates/emails/password_reset.html <<'BA_EOF'
{% extends "emails/base.html" %}

{% block content %}
<h2>Reset your password</h2>
<p>Click the button below to reset your password:</p>
<p><a href="{{ reset_url }}" class="btn">Reset Password</a></p>
<p>This link expires in 30 minutes.</p>
<p>If you didn't request this, you can safely ignore this email.</p>
{% endblock %}
BA_EOF

write_file templates/emails/security_alert.html <<'BA_EOF'
{% extends "emails/base.html" %}

{% block content %}
<h2>Security Alert</h2>
<p>{{ message }}</p>
<p>If this wasn't you, please change your password immediately.</p>
<p><a href="{{ account_url }}" class="btn">Go to Account</a></p>
{% endblock %}
BA_EOF

# =============================================================================
#  Каталог: модели
# =============================================================================
write_file apps/catalog/apps.py <<'BA_EOF'
from django.apps import AppConfig


class CatalogConfig(AppConfig):
    name = "apps.catalog"
    label = "catalog"
    verbose_name = "Каталог игр"
BA_EOF

write_file apps/catalog/models/game.py <<'BA_EOF'
from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7, CitextField
from apps.core.ids import uuid7


class Game(models.Model):
    """Игра-картридж. technical_id и host_label неизменяемы (§2.4.1)."""

    STATUS_DRAFT = "draft"
    STATUS_REVIEW = "review"
    STATUS_PUBLISHED = "published"
    STATUS_HIDDEN = "hidden"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Черновик"),
        (STATUS_REVIEW, "На проверке"),
        (STATUS_PUBLISHED, "Опубликована"),
        (STATUS_HIDDEN, "Скрыта"),
        (STATUS_ARCHIVED, "Архив"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    technical_id = CitextField(
        max_length=40,
        unique=True,
        help_text="Неизменяемый код из манифеста. Regex: ^[a-z][a-z0-9_]{1,38}[a-z0-9]$",
    )
    host_label = CitextField(
        max_length=63,
        unique=True,
        help_text="DNS-метка игрового origin. Неизменяема.",
    )
    slug = CitextField(
        max_length=128,
        unique=True,
        help_text="Публичный адрес игры на портале. Локализуется.",
    )
    primary_genre = models.ForeignKey(
        "catalog.Genre",
        on_delete=models.PROTECT,
        related_name="primary_games",
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    current_version = models.ForeignKey(
        "catalog.GameVersion",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="current_for_games",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    publish_at = models.DateTimeField(null=True, blank=True, help_text="Запланированная публикация")

    # Настройки из манифеста (P — платформа, только чтение)
    min_session_seconds = models.PositiveIntegerField(default=15)
    max_session_seconds = models.PositiveIntegerField(default=1800)
    pause_on_blur = models.BooleanField(default=True)
    mobile_support = models.BooleanField(default=True)
    orientation = models.CharField(max_length=16, default="any")
    estimated_play_minutes = models.PositiveSmallIntegerField(default=5)
    default_language = models.CharField(max_length=8, default="en")
    accent_color = models.CharField(max_length=7, default="#39ff88")
    capabilities = models.JSONField(default=dict, blank=True)
    verification_profile = models.JSONField(default=dict, blank=True)

    # Правила счёта
    score_type = models.CharField(max_length=16, default="integer")
    score_unit = models.CharField(max_length=16, default="points")
    score_direction = models.CharField(max_length=16, default="higher_is_better")
    score_min_value = models.IntegerField(default=0)
    score_max_value = models.IntegerField(default=100000)
    score_schema_version = models.PositiveSmallIntegerField(default=1)

    # Таблица рекордов
    leaderboard_epoch = models.PositiveSmallIntegerField(default=1)
    leaderboard_enabled = models.BooleanField(default=True)
    leaderboard_only_verified = models.BooleanField(default=False)

    # Настройки доверия и голосования (C — только CRM)
    rating_min_playtime_seconds = models.PositiveIntegerField(default=120)
    verifier_slug = models.CharField(max_length=64, blank=True)
    trust_level_max = models.CharField(max_length=32, default="heuristic_validated")

    # Поля, переопределённые в CRM (не затираются при импорте)
    overridden_fields = models.JSONField(default=list, blank=True)
    credits = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "catalog_game"
        verbose_name = "Игра"
        verbose_name_plural = "Игры"

    def __str__(self) -> str:
        return self.technical_id
BA_EOF

write_file apps/catalog/models/translation.py <<'BA_EOF'
from __future__ import annotations

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models

from apps.core.fields import UUID7, CitextField
from apps.core.ids import uuid7


class GameTranslation(models.Model):
    """Локализованные данные игры."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    game = models.ForeignKey(
        "catalog.Game",
        on_delete=models.CASCADE,
        related_name="translations",
    )
    language = models.ForeignKey(
        "i18n.Language",
        on_delete=models.CASCADE,
        related_name="game_translations",
    )
    name = models.CharField(max_length=128)
    slug = CitextField(max_length=128, help_text="Уникален в рамках языка")
    short_description = models.CharField(max_length=160)
    description = models.TextField(max_length=1600)
    instructions = models.TextField(max_length=600, blank=True)
    controls = models.TextField(max_length=400, blank=True)
    seo_title = models.CharField(max_length=60, blank=True)
    seo_description = models.CharField(max_length=160, blank=True)
    search_vector = SearchVectorField(null=True, blank=True)
    overridden_fields = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "catalog_game_translation"
        unique_together = [("game", "language"), ("slug", "language")]
        indexes = [GinIndex(fields=["search_vector"])]
        verbose_name = "Перевод игры"
        verbose_name_plural = "Переводы игр"

    def __str__(self) -> str:
        return f"{self.game} [{self.language.code}] {self.name}"
BA_EOF

write_file apps/catalog/models/genre.py <<'BA_EOF'
from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7, CitextField
from apps.core.ids import uuid7


class Genre(models.Model):
    """Жанр игры. Канонические коды: arcade, puzzle, action, ... (§2.8)."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    code = CitextField(max_length=32, unique=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    image = models.ImageField(upload_to="genres/", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "catalog_genre"
        ordering = ["sort_order", "code"]
        verbose_name = "Жанр"
        verbose_name_plural = "Жанры"

    def __str__(self) -> str:
        return self.code


class GenreTranslation(models.Model):
    """Локализованное название и описание жанра."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    genre = models.ForeignKey(Genre, on_delete=models.CASCADE, related_name="translations")
    language = models.ForeignKey("i18n.Language", on_delete=models.CASCADE, related_name="genre_translations")
    name = models.CharField(max_length=64)
    slug = CitextField(max_length=64, help_text="Уникален в рамках языка")
    description = models.TextField(max_length=500, blank=True)
    seo_title = models.CharField(max_length=60, blank=True)
    seo_description = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "catalog_genre_translation"
        unique_together = [("genre", "language"), ("slug", "language")]
        verbose_name = "Перевод жанра"
        verbose_name_plural = "Переводы жанров"

    def __str__(self) -> str:
        return f"{self.genre.code} [{self.language.code}] {self.name}"
BA_EOF

write_file apps/catalog/models/tag.py <<'BA_EOF'
from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7, CitextField
from apps.core.ids import uuid7


class Tag(models.Model):
    """Тег игры. Создаётся автоматически при импорте (§2.14.4)."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    code = CitextField(max_length=64, unique=True)
    needs_translation = models.BooleanField(default=True, help_text="Пометка «требует перевода»")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "catalog_tag"
        ordering = ["code"]
        verbose_name = "Тег"
        verbose_name_plural = "Теги"

    def __str__(self) -> str:
        return self.code


class TagTranslation(models.Model):
    """Локализованное название тега."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="translations")
    language = models.ForeignKey("i18n.Language", on_delete=models.CASCADE, related_name="tag_translations")
    name = models.CharField(max_length=64)
    slug = CitextField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "catalog_tag_translation"
        unique_together = [("tag", "language"), ("slug", "language")]
        verbose_name = "Перевод тега"
        verbose_name_plural = "Переводы тегов"

    def __str__(self) -> str:
        return f"{self.tag.code} [{self.language.code}] {self.name}"
BA_EOF

write_file apps/catalog/models/asset.py <<'BA_EOF'
from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7
from apps.core.ids import uuid7


class GameAsset(models.Model):
    """Изображение игры: обложка, скриншот."""

    TYPE_COVER = "cover"
    TYPE_SCREENSHOT = "screenshot"
    TYPE_CHOICES = [
        (TYPE_COVER, "Обложка"),
        (TYPE_SCREENSHOT, "Скриншот"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    game = models.ForeignKey("catalog.Game", on_delete=models.CASCADE, related_name="assets")
    version = models.ForeignKey(
        "catalog.GameVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assets",
    )
    type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    file = models.ImageField(upload_to="games/assets/")
    alt = models.JSONField(default=dict, blank=True, help_text="{lang: text}")
    sort_order = models.PositiveSmallIntegerField(default=0)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    bytes = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "catalog_game_asset"
        ordering = ["sort_order"]
        verbose_name = "Ассет игры"
        verbose_name_plural = "Ассеты игр"

    def __str__(self) -> str:
        return f"{self.game} {self.type} #{self.sort_order}"
BA_EOF

write_file apps/catalog/models/version.py <<'BA_EOF'
from __future__ import annotations

from django.db import models

from apps.core.fields import UUID7
from apps.core.ids import uuid7


class GameVersion(models.Model):
    """Неизменяемая версия игры (§2.14.1)."""

    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    game = models.ForeignKey("catalog.Game", on_delete=models.CASCADE, related_name="versions")
    semver = models.CharField(max_length=32, help_text="Уникален в рамках игры")
    package_hash = models.CharField(max_length=64, help_text="SHA-256 исходного ZIP")
    runtime_hash = models.CharField(max_length=64, help_text="SHA-256 рабочего бандла")
    sdk_version = models.CharField(max_length=32)
    sdk_contract_version = models.CharField(max_length=32, default="1")
    size_bytes = models.PositiveIntegerField()
    manifest = models.JSONField()
    entry_path = models.CharField(max_length=255, default="index.html")
    critical_path_bytes_declared = models.PositiveIntegerField(null=True, blank=True)
    critical_path_bytes_measured = models.PositiveIntegerField(null=True, blank=True)
    supported_languages = models.JSONField(default=list)
    claimed_verification = models.CharField(max_length=32, blank=True)
    validation_report = models.JSONField(default=dict, blank=True)
    import_report = models.JSONField(default=dict, blank=True)
    injection_report = models.JSONField(default=dict, blank=True)
    e2e_report = models.JSONField(default=dict, blank=True)
    manual_review_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="manual_reviews",
    )
    manual_review_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_versions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "catalog_game_version"
        unique_together = [("game", "semver")]
        verbose_name = "Версия игры"
        verbose_name_plural = "Версии игр"

    def __str__(self) -> str:
        return f"{self.game} v{self.semver}"
BA_EOF

write_file apps/catalog/models/__init__.py <<'BA_EOF'
from .asset import GameAsset
from .game import Game
from .genre import Genre, GenreTranslation
from .tag import Tag, TagTranslation
from .translation import GameTranslation
from .version import GameVersion

__all__ = [
    "Game",
    "GameTranslation",
    "GameVersion",
    "GameAsset",
    "Genre",
    "GenreTranslation",
    "Tag",
    "TagTranslation",
]
BA_EOF

# =============================================================================
#  Обновление urls.py с языковыми префиксами
# =============================================================================
write_file config/urls.py <<'BA_EOF'
"""Корневые маршруты с языковыми префиксами (§2.6)."""
from __future__ import annotations

from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.urls import include, path
from django.views.generic import RedirectView

from apps.core import health

urlpatterns = [
    # Пробы живучести без языкового префикса
    path("healthz", health.healthz, name="healthz"),
    path("readyz", health.readyz, name="readyz"),

    # Тема
    path("", include("apps.theme.urls")),

    # CRM (без языкового префикса, с защищённым префиксом)
    path("crm/", include("apps.crm.urls", namespace="crm")),
]

# Языковые префиксы для публичных страниц
urlpatterns += i18n_patterns(
    # Главная страница
    path("", include("apps.catalog.urls", namespace="catalog")),
    prefix_default_language=True,
)

# Редирект корня / по Accept-Language
urlpatterns += [
    path("", RedirectView.as_view(url="/en/", permanent=False)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
BA_EOF

# =============================================================================
#  Обновление settings/base.py
# =============================================================================
write_file config/settings/base.py <<'BA_EOF'
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
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
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
CELERY_BEAT_SCHEDULE: dict[str, dict[str, object]] = {}

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
BA_EOF

# =============================================================================
#  Итоговая подсказка
# =============================================================================
printf '\nЭтап 1, блок 2\n'
printf '  Каталог:   %s\n' "$PWD"
printf '  Заполнено: %d\n' "$filled"
printf '  Пропущено: %d\n' "$skipped"
if (( backed > 0 )); then printf '  Резервные копии: %s (%d)\n' "$BACKUP_DIR" "$backed"; fi
if (( DRY )); then printf '  Режим dry-run: изменения не внесены\n'; exit 0; fi

cat <<'BA_EOF'

Следующие шаги:
  make makemigrations  # i18n.Language, TranslationEntry, ThemeTokenSet, Game, Genre, Tag, ...
  make migrate         # создаст таблицы и начальные языки (en, de, nl, ru, fr, es)
  make up              # перезапуск контейнеров
  curl -k https://portal.test:8443/en/healthz

Проверка:
  - https://portal.test:8443/en/ — английская версия
  - https://portal.test:8443/de/ — немецкая версия
  - https://portal.test:8443/theme-<hash>.css — файл темы с immutable-кешем
  - https://portal.test:8443/crm/ — вход в CRM (пока 404, каркас создан)

Следующий блок (3): бэкапы, restore-check, staging/prod compose, наблюдаемость.
BA_EOF
