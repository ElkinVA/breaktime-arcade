#!/usr/bin/env bash
# =============================================================================
#  fix_static_storage.sh — исправление ошибки ManifestStaticFilesStorage
#  с Tailwind v4 bare-импортами (@import "tailwindcss")
#
#  Запуск: bash fix_static_storage.sh [КАТАЛОГ] [--force] [--dry-run] [--rebuild]
# =============================================================================
set -euo pipefail

TARGET="$PWD"; FORCE=0; DRY=0; REBUILD=0
for arg in "$@"; do
  case "$arg" in
    --force)    FORCE=1 ;;
    --dry-run)  DRY=1 ;;
    --rebuild)  REBUILD=1 ;;
    -h|--help)  sed -n '2,7p' "$0"; exit 0 ;;
    -*) printf 'Неизвестный ключ: %s\n' "$arg" >&2; exit 2 ;;
    *) TARGET="$arg" ;;
  esac
done
cd "$TARGET"
if [[ ! -d apps/core || ! -d config/settings ]]; then
  printf 'Каталог %s не содержит ядра. Сначала выполните bootstrap_structure.sh\n' "$TARGET" >&2
  exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR=".backups/$STAMP"
filled=0; skipped=0; backed=0; updated=0

write_file() {
  local rel="$1" tmp
  tmp="$(mktemp)"
  cat > "$tmp"
  if [[ -e "$rel" && -s "$rel" && $FORCE -eq 0 ]]; then
    printf '  SKIP  %s (не пустой)\n' "$rel"; skipped=$((skipped+1)); rm -f "$tmp"; return
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
  chmod 644 "$rel"
  printf '  OK    %s\n' "$rel"; filled=$((filled+1))
}

# Патч существующего файла: замена строки по точному совпадению
patch_file() {
  local rel="$1" from="$2" to="$3" tmp
  if [[ ! -f "$rel" ]]; then
    printf '  MISS  %s (файл не найден)\n' "$rel"; return 1
  fi
  if ! grep -qF -- "$from" "$rel"; then
    if grep -qF -- "$to" "$rel"; then
      printf '  ALREADY %s (патч уже применён)\n' "$rel"; return 0
    fi
    printf '  NOTFOUND %s (искомая строка не найдена)\n' "$rel"; return 1
  fi
  if (( DRY )); then
    printf '  PATCH %s\n' "$rel"; updated=$((updated+1)); return 0
  fi
  tmp="$(mktemp)"
  awk -v from="$from" -v to="$to" '{
    if (index($0, from) > 0) { gsub(from, to); }
    print
  }' "$rel" > "$tmp"
  mkdir -p -- "$BACKUP_DIR/$(dirname -- "$rel")"
  cp -p -- "$rel" "$BACKUP_DIR/$rel"; backed=$((backed+1))
  mv -f -- "$tmp" "$rel"
  chmod 644 "$rel"
  printf '  PATCH %s\n' "$rel"; updated=$((updated+1))
}

# =============================================================================
#  1. Кастомное хранилище статики
# =============================================================================
write_file apps/core/storage.py <<'BA_EOF'
"""Кастомное хранилище статики для совместимости с Tailwind v4.

ManifestStaticFilesStorage Django парсит CSS и пытается найти все @import
как локальные файлы. Tailwind v4 использует bare-импорт @import "tailwindcss"
(без расширения), что вызывает ValueError. Это хранилище корректно игнорирует
такие импорты, возвращая исходное имя вместо хешированного.

Норматив: BA-PLAT-4.2 §2.7, §2.20.
"""
from __future__ import annotations

import logging
from typing import Any

from django.contrib.staticfiles.storage import ManifestStaticFilesStorage

logger = logging.getLogger(__name__)


class BAStaticFilesStorage(ManifestStaticFilesStorage):
    """Хранилище статики с безопасной обработкой внешних CSS-импортов."""

    def hashed_name(
        self,
        name: str,
        content: Any | None = None,
        filename: str | None = None,
    ) -> str:
        try:
            return super().hashed_name(name, content, filename)
        except ValueError as exc:
            # Внешние импорты (например, @import "tailwindcss") не должны хешироваться.
            # Возвращаем исходное имя и логируем для диагностики.
            logger.debug(
                "Static file %s skipped hashing (external import or missing): %s",
                name,
                exc,
            )
            return name

    def _url(
        self,
        hashed_name_func: Any,
        name: str,
        force: bool = False,
        hashed_files: dict[str, str] | None = None,
    ) -> str:
        try:
            return super()._url(hashed_name_func, name, force, hashed_files)
        except ValueError:
            # Fallback для ссылок из CSS, указывающих на внешние ресурсы.
            return name
BA_EOF

# =============================================================================
#  2. Патч settings/base.py: dev/staging используют это же хранилище
# =============================================================================
patch_file \
  config/settings/base.py \
  '"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},' \
  '"staticfiles": {"BACKEND": "apps.core.storage.BAStaticFilesStorage"},' \
  || printf '  ! base.py: статика уже настроена или структура отличается; проверьте вручную\n'

# =============================================================================
#  3. Патч settings/prod.py: ManifestStaticFilesStorage → BAStaticFilesStorage
# =============================================================================
patch_file \
  config/settings/prod.py \
  '"django.contrib.staticfiles.storage.ManifestStaticFilesStorage"' \
  '"apps.core.storage.BAStaticFilesStorage"' \
  || printf '  ! prod.py: статика уже настроена или структура отличается; проверьте вручную\n'

# =============================================================================
#  4. Итог
# =============================================================================
printf '\nИсправление ManifestStaticFilesStorage\n'
printf '  Каталог:          %s\n' "$PWD"
printf '  Создано файлов:   %d\n' "$filled"
printf '  Патчей применено: %d\n' "$updated"
printf '  Пропущено:        %d\n' "$skipped"
if (( backed > 0 )); then printf '  Резервные копии:  %s (%d)\n' "$BACKUP_DIR" "$backed"; fi
if (( DRY )); then printf '  Режим dry-run: изменения не внесены\n'; exit 0; fi

if (( REBUILD )); then
  cat <<'BA_EOF'

Пересобираю образ и перезапускаю контейнеры...
BA_EOF
  docker compose -f compose.yml -f compose.dev-lite.yml build --no-cache
  docker compose -f compose.yml -f compose.dev-lite.yml --profile beat up -d
  cat <<'BA_EOF'

Контейнеры перезапущены. Следующие шаги:
  make makemigrations
  make migrate
  make superuser
  curl -k https://portal.test:8443/healthz
BA_EOF
else
  cat <<'BA_EOF'

Следующие шаги (выполните вручную):
  make build          # пересобрать образ
  make up             # перезапустить контейнеры
  make makemigrations
  make migrate
  make superuser
  curl -k https://portal.test:8443/healthz

Или одной командой с автопересборкой:
  bash fix_static_storage.sh --rebuild
BA_EOF
fi
