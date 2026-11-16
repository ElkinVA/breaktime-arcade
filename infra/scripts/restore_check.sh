#!/usr/bin/env bash
# restore_check.sh — обёртка для проверки восстановления из контейнера.
set -euo pipefail
cd /app
exec python manage.py restore_check "$@"
