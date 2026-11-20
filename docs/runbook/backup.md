# Резервное копирование

Нормативная основа: BA-PLAT-4.2 §2.5. В dev доступен полный `pg_dump`;
WAL/PITR и внешнее хранение относятся к staging/production и пока не
настроены.

## 1. Ручной бэкап

```bash
make backup
```

Команда запускает профиль `backup` и `python manage.py backup_run`:

- `pg_dump --format=custom --compress=9`;
- файл `ba-<UTC timestamp>.dump` в `BACKUP_DIR` (по умолчанию
  `/app/var/backups`);
- SHA-256 файла и запись `BackupRun` в БД;
- ротация старше `BACKUP_RETENTION_DAYS` (по умолчанию 30 дней).

Не выводить содержимое `.env` или пароль БД. `pg_dump` использует
`DATABASE_URL`/`POSTGRES_*` из окружения.

## 2. Проверка наличия и целостности

Внутри `web`:

```bash
docker compose -f compose.yml -f compose.dev-lite.yml exec -T web \
  python manage.py shell -c "from apps.crm.models.backup import BackupRun; print(list(BackupRun.objects.filter(type='full').order_by('-started_at').values('status','size_bytes','sha256','file_path')[:5]))"
```

Ожидается успешная запись с непустыми `size_bytes`, `sha256`, `file_path`.
Хэш файла можно пересчитать через `sha256sum`.

## 3. Ограничения

- Полный бэкап в S3, WAL-архив, immutable storage и внешний регион не
  реализованы; это не production DR.
- `BackupRun` статус `missing` в `/readyz` не делает dev неготовым, но
  production-алерты должны различать отсутствие бэкапа.
- Восстановление проверяется отдельным runbook `restore.md`.
