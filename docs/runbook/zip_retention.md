# ZIP-хранилище: квота и retention

Нормативная основа: BA-PLAT-4.2 §2.14.1–§2.14.2 («распаковка в изолированном
временном каталоге с квотой»), §2.20 («Загрузка контента»), R-033/R-037/R-043.
Задача: `ARCADE-P4-STORAGE-001`.

## 1. Область квоты

Системная квота считает **сумму байт всех общих ZIP-корней**, а не один архив:

| Корень | Назначение | Монтирование |
|---|---|---|
| `ZIP_UPLOADS_ROOT` | транзитные `source.zip` / `CANCEL` | web **rw**, zip-worker **ro** |
| `ZIP_ARTIFACTS_ROOT` | результат распаковки, `STATUS.json`, `COMPLETED.json` | zip-worker **rw**, web **ro** |
| `ZIP_PIPELINE_STORAGE_ROOT` | приватные исходные ZIP (`packages/<hash>.zip`) | web **rw** |

Публичный runtime (`ZIP_PUBLIC_RUNTIME_ROOT`/`runtime_data`) **не входит** в
квоту и никогда не удаляется и не изменяется квотой/cleanup. Опубликованные
`GameVersion`, их `package_hash`/`runtime_hash` и файлы runtime неприкосновенны.

`web` видит все три корня (uploads, artifacts ro, packages) и учитывает их при
допуске. `zip-worker` видит uploads (ro) и artifacts; на время распаковки
`web` удерживает свой резерв, поэтому байты исходного ZIP/пакета уже учтены в
общем reservation-файле.

## 2. Механизм допуска

- Состояние квоты и `flock`-lock лежат в `ZIP_QUOTA_STATE_ROOT`
  (`/var/ba/zip/quota`), отдельном volume, смонтированном rw в `web` и
  `zip-worker`. Это lock/reservation, общий для загрузки и распаковки.
- `web` резервирует размер ZIP **до** записи оригинала/upload и держит резерв
  до конца импорта. `zip-worker` резервирует worst-case размер результата
  (`ZIP_JOB_MAX_BYTES`) до распаковки и освобождает резерв сразу после неё.
- Допуск проверяет: `usage + active_reservations + requested <=
  ZIP_STORAGE_QUOTA_BYTES` и `free - requested >= ZIP_STORAGE_MIN_FREE_BYTES`.
- После записи результата worker дополнительно проверяет фактический usage
  (`assert_within_limit`) и при превышении удаляет только собственный partial
  result.
- Просроченные резервы (старше `ZIP_QUOTA_RESERVATION_TTL_SECONDS`, по
  умолчанию 3600 с) игнорируются при следующем допуске: падение web не
  блокирует квоту навсегда.

Отказы стабильные и недеструктивные (ничего не удаляют, runtime не трогают):

| Код | Значение |
|---|---|
| `X_STORAGE_QUOTA` | превышен `ZIP_STORAGE_QUOTA_BYTES` |
| `X_STORAGE_FREE_SPACE` | свободного места меньше `ZIP_STORAGE_MIN_FREE_BYTES` |
| `X_STORAGE_QUOTA_STATE` | недоступен/небезопасен каталог состояния квоты |

## 3. Политика retention по состояниям задания

TTL — от терминального времени (mtime маркера/каталога). Cleanup выполняется
Beat-задачами; повторный запуск идемпотентен.

| Состояние `ZipExtractionJob` | `source.zip` (uploads) | result/artifacts | Публичный runtime / original ZIP |
|---|---|---|---|
| active: `queued`, `running` | **не удаляется никогда** (id из БД передаётся в cleanup; worker держит `.lock`) | **не удаляется** (активный `flock`/свежий каталог) | не трогается |
| `completed` | удаляется сразу после успешного импорта; остаток — `ZIP_STAGING_TTL_SECONDS` (3600) | `ZIP_COMPLETED_TTL_SECONDS` (86400) от `COMPLETED.json` | не трогается |
| `failed`, `rejected`, `timeout`, `cancelled` | удаляется сразу, если worker уже не нужен; иначе `ZIP_STAGING_TTL_SECONDS` | `ZIP_STAGING_TTL_SECONDS` (нет `COMPLETED.json` → incomplete) | не трогается |
| abandoned (нет процесса/нет терминального маркера) | `ZIP_STAGING_TTL_SECONDS` | `ZIP_STAGING_TTL_SECONDS` | не трогается |
| quarantined (ATTEMPTS ≥ 2) | как abandoned (source нужен для разбора только TTL) | как incomplete | не трогается |

Уточнения:

- `active` определяется по DB-статусам `queued`/`running` для uploads и по
  `flock` на `artifacts/<job_id>/.lock` для artifacts. Cleanup не может
  удалить задание, которое ещё выполняется.
- Каталоги non-UUID и `.quota` не считаются job-каталогами и не удаляются.
- Original ZIP (`packages/`) и опубликованный runtime хранятся, пока на них
  ссылается `GameVersion`/`Game.current_version`; автоматического удаления
  нет. Идемпотентный повторный импорт не создаёт второй экземпляр (`store_immutable`).
- Удаление ограничено двумя корнями (`uploads`, `artifacts`); cleanup не
  принимает `runtime_data`/`ZIP_PUBLIC_RUNTIME_ROOT`.

## 4. Параметры (не секреты)

| Переменная | Dev default | Staging example |
|---|---|---|
| `ZIP_QUOTA_STATE_ROOT` | `/var/ba/zip/quota` | `/var/ba/zip/quota` |
| `ZIP_STORAGE_QUOTA_BYTES` | `2147483648` (2 ГиБ) | `5368709120` (5 ГиБ) |
| `ZIP_STORAGE_MIN_FREE_BYTES` | `157286400` (150 МиБ) | `536870912` (512 МиБ) |
| `ZIP_QUOTA_RESERVATION_TTL_SECONDS` | `3600` | `3600` |
| `ZIP_STAGING_TTL_SECONDS` | `3600` | `7200` |
| `ZIP_COMPLETED_TTL_SECONDS` | `86400` | `86400` |

`ZIP_STORAGE_QUOTA_BYTES` должен превышать `ZIP_JOB_MAX_BYTES` (по умолчанию
120 МиБ), иначе любая распаковка будет отклонена.

## 5. Проверка

```bash
# состояние томов и прав
docker compose ps zip-volume-init web zip-worker

# размеры корней (внутри web)
docker compose exec -T web python manage.py shell -c \
  "from apps.pipeline.services.quota import StorageQuota; q=StorageQuota.from_settings(); print(q.usage_bytes(), q.max_bytes)"

# задачи cleanup (синхронно, с доступом к нужному rw-тому)
docker compose exec -T worker python manage.py shell -c \
  "from apps.pipeline.tasks import cleanup_zip_uploads; print(cleanup_zip_uploads())"
docker compose exec -T zip-worker python manage.py shell -c \
  "from apps.pipeline.tasks import cleanup_zip_staging; print(cleanup_zip_staging())"
```

При `X_STORAGE_QUOTA`/`X_STORAGE_FREE_SPACE` сначала проверяются TTL-задачи и
свободное место; удаление опубликованных runtime/version не является
способом восстановления.
