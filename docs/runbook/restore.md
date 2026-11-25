# Проверка и восстановление БД

Нормативная основа: BA-PLAT-4.2 §2.5. В dev доступна проверка последнего
полного дампа в отдельную БД. Полноценный production restore и PITR не
реализованы.

## 1. Проверка последнего бэкапа

```bash
make backup
make restore-check
```

`restore-check`:

1. находит последний успешный `BackupRun(type=full)` (или явный `--file`,
   для которого есть запись `BackupRun` с непустым `sha256`);
2. отклоняет отсутствующий, пустой (0 байт) или недоступный дамп;
3. сверяет SHA-256 файла с `BackupRun.sha256` **до** любых операций с БД и
   повторно после `pg_restore`, чтобы обнаружить подмену во время restore;
4. создаёт отдельную БД `ba_restore_check` (`DROP ... WITH (FORCE)` для
   зависших подключений);
5. выполняет `pg_restore --no-owner --no-privileges --exit-on-error` и
   проверяет exit code каждой команды;
6. проверяет, что в `public` есть таблицы, присутствуют обязательные таблицы
   (`django_migrations`, `accounts_user/profile`, `catalog_game`,
   `catalog_game_version/translation`, `gameplay_session/result`,
   `gameplay_leaderboard_entry`, `crm_backup_run`) и `django_migrations`
   непуста;
7. сохраняет в `BackupRun.meta` путь, id полного прогона, SHA-256,
   `table_count`, `required_tables`, `migration_count`;
8. удаляет `ba_restore_check` (best-effort) и сохраняет
   `BackupRun(type=restore_check)` и `verified_at` только при успехе.

Успех означает структурную проверку восстановления, а не проверку
целостности всех данных: пустой по содержимому, но структурно корректный
дамп пройдёт. Полноценный production restore и PITR не реализованы.

Команда не восстанавливает основную БД и не должна выполняться на
staging/production. Она требует права создавать/удалять БД.

## 2. Ручное восстановление в отдельную БД

Для расследования можно использовать `pg_restore` в **новую** БД, не
перезаписывая `ba`:

```bash
psql -h db -U ba -d postgres -c 'CREATE DATABASE ba_restore_manual;'
pg_restore -h db -U ba -d ba_restore_manual --no-owner --no-privileges /path/to/backup.dump
```

После проверки временную БД удалить только по согласованию. Не выполнять
`DROP DATABASE ba` и не использовать `--clean` на рабочей БД.

## 3. Ограничения

- `infra/scripts/restore.sh` пуст; полноценный автоматизированный restore
  всего окружения не реализован.
- WAL/PITR, S3 и внешняя копия не настроены.
- Проверка restore требует отдельного согласования, если затрагивает
  staging/production или существующие данные.
