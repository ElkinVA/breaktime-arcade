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

1. находит последний успешный `BackupRun(type=full)`;
2. создаёт отдельную БД `ba_restore_check`;
3. выполняет `pg_restore --no-owner --no-privileges --exit-on-error`;
4. считает таблицы в `public`;
5. удаляет `ba_restore_check`;
6. сохраняет `BackupRun(type=restore_check)` и `verified_at`.

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
