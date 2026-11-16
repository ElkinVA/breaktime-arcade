#!/usr/bin/env bash
# backup.sh — обёртка для запуска бэкапа из контейнера.
# Полная логика — в apps/crm/services/backup.py.
set -euo pipefail
cd /app
exec python manage.py backup_run "$@"
