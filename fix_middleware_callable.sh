#!/usr/bin/env bash
# =============================================================================
#  fix_middleware_callable.sh — исправление NameError: Callable not defined
#
#  Проблема: Callable импортируется внутри if TYPE_CHECKING, но используется
#  вне этого блока для определения GetResponse.
#
#  Запуск: bash fix_middleware_callable.sh [КАТАЛОГ] [--dry-run]
# =============================================================================
set -euo pipefail

TARGET="${1:-.}"
DRY=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) TARGET="$arg" ;;
  esac
done
cd "$TARGET"

printf '\n=== ИСПРАВЛЕНИЕ Callable В MIDDLEWARE ===\n\n'

FILE="apps/i18n/middleware.py"

if [[ ! -f "$FILE" ]]; then
  printf '✗ Файл %s не найден\n' "$FILE"
  exit 1
fi

printf '== 1. Текущее содержимое (первые 25 строк) ==\n'
head -25 "$FILE" | nl
printf '\n'

printf '== 2. Исправление: перемещение GetResponse внутрь TYPE_CHECKING ==\n'

if (( DRY )); then
  printf '  DRY: исправление %s\n' "$FILE"
else
  # Создаём исправленную версию
  cat > "$FILE" <<'BA_EOF'
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

    GetResponse = Callable[[HttpRequest], HttpResponse]

CACHE_KEY = "i18n:active_codes"
CACHE_TTL = 600


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

  chmod 644 "$FILE"
  printf '  ✓ Файл исправлен\n'
fi

printf '\n== 3. Проверка синтаксиса ==\n'
if python3 -m py_compile "$FILE" 2>&1; then
  printf '  ✓ Синтаксис корректен\n'
else
  printf '  ✗ Ошибка синтаксиса\n'
  exit 1
fi

printf '\n== 4. Проверка импорта ==\n'
if python3 -c "import sys; sys.path.insert(0, '.'); from apps.i18n.middleware import LanguagePrefixMiddleware; print('  ✓ Модуль импортирован успешно')" 2>&1; then
  :
else
  printf '  ✗ Ошибка импорта\n'
  exit 1
fi

printf '\n=== ГОТОВО ===\n'
printf '\nСледующие шаги:\n'
printf '  docker compose -f compose.yml -f compose.dev-lite.yml --profile beat up -d --force-recreate\n'
printf '  docker compose -f compose.yml -f compose.dev-lite.yml exec -T web python manage.py check\n'
