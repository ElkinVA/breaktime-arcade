# Staging verification — ARCADE-P4 A4 / R-042

**Дата:** 2026-11-22
**Статус:** PREPARED — live staging **NOT TESTED** (в среде нет
`.env.staging`). Этот runbook не создаёт секреты и не выдаёт статические
проверки за живые.

## 1. Что уже готово статически

- `compose.staging.yml` — отдельный project `ba-staging`, отдельные сети,
  volumes и env-file; Basic Auth + IP allowlist + noindex.
- `compose.yml` — `zip-volume-init` создаёт и владеет `zip_uploads`,
  `zip_artifacts`, `zip_quota`, `runtime_data` (uid 10001); web пишет
  runtime/uploads/quota, nginx читает runtime, zip-worker читает uploads и
  пишет artifacts/quota.
- `.env.staging.example` и `gen_staging_env.sh` содержат несекретные
  значения quota/retention; пароли/сертификаты генерируются отдельно.
- `verify_staging_final.sh` — read-only HTTP/robots/dev-lite проверки.
- `verify_staging_p4.sh` — read-only P4-проверки ownership, `zip_quota`,
  изоляции zip-worker, writable/read-only томов и restore-check; при
  отсутствии `.env.staging` завершается `BLOCKED` (код 3).

## 2. Что требуется от владельца

1. Создать `.env.staging` из `.env.staging.example` (или
   `./infra/scripts/gen_staging_env.sh`) на staging-хосте.
2. Заполнить **только** реальные значения домена, TLS-путей, allowlist IP,
   DB/Redis/secret key, Basic Auth; секреты — в файл/хранилище, не в Git и
   не в переписку.
3. Подтвердить окно запуска staging и ответственного.

Без `.env.staging` нельзя честно проверить live staging; любые `compose
config` проверки — только статические.

## 3. Порядок live-проверки (после появления `.env.staging`)

```bash
# 1. Конфигурация без запуска и без вывода секретов
docker compose -p ba-staging -f compose.yml -f compose.staging.yml \
  --env-file .env.staging config --quiet

# 2. Запуск
make staging-up
make staging-status

# 3. Read-only HTTP/robots/noindex/dev-lite
./verify_staging_final.sh
```

Далее — **только read-only** проверки:

```bash
C=(docker compose -p ba-staging -f compose.yml -f compose.staging.yml --env-file .env.staging)

# 4. Все сервисы healthy; zip-worker в сети zipnet, read_only, лимиты
$C ps
docker inspect "$($C ps -q zip-worker)" \
  --format '{{.HostConfig.ReadonlyRootfs}} {{.HostConfig.NanoCpus}} {{.HostConfig.Memory}} {{.HostConfig.PidsLimit}} {{json .NetworkSettings.Networks}}'

# 5. Ownership/shared volumes: init создал каталоги, uid 10001
$C exec -T web sh -lc 'stat -c "%u:%g %a %n" /app/runtime /var/ba/zip/uploads /var/ba/zip/artifacts /var/ba/zip/quota'
$C exec -T zip-worker sh -lc 'touch /var/ba/zip/artifacts/.probe && rm /var/ba/zip/artifacts/.probe; ! touch /var/ba/zip/uploads/.probe'

# 6. ZIP worker доступен и обрабатывает очередь
$C exec -T worker sh -lc 'celery -A config inspect active_queues'   # default/celery
$C exec -T zip-worker sh -lc 'celery -A config inspect active_queues'  # zip
$C logs --tail=100 zip-worker

# 7. Backup/restore-check
make backup
make restore-check

# 8. Реальный импорт/публикация (staff UI):
#    CRM → Игры → загрузить ZIP Neon Snake → анализ → публикация
#    проверить: draft/version, runtime hash, public detail/iframe,
#    SDK session/result/leaderboard, повторную версию/rollback.
```

## 4. Критерии PASS / BLOCKED

| Проверка | PASS | BLOCKED |
|---|---|---|
| `.env.staging` | существует, не в Git | отсутствует — все live checks NOT TESTED |
| compose config | exit 0 | ошибка/секрет в Git |
| HTTP/robots/noindex | `verify_staging_final.sh` OK | 401/403/5xx вне allowlist |
| zip-worker isolation | read_only, zipnet, лимиты | сеть/права шире |
| volumes ownership | uid 10001, запись там где нужно | root-owned/403 |
| backup/restore-check | команды успешны | ошибка/потеря данных |
| ZIP import/publish | реальный пакет опубликован | очередь/worker недоступны |

## 5. Ограничения

- В текущей среде `.env.staging` отсутствует; **live staging NOT TESTED**.
- `verify_staging_final.sh` не проверяет ownership/volumes/ZIP worker —
  шаги 4–7 этого runbook обязательны вручную.
- Hard filesystem quota не включена; app-layer quota + min-free — см.
  `docs/runbook/zip_retention.md`.
