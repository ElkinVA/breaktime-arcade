# BA-ZIP-WORKER-001 — отчёт

**Дата:** 2026-11-20
**Статус:** **TECHNICALLY ACCEPTED** (agent, OD-TECH-001);
продуктовая приёмка — владелец
**Исполнитель:** основная сессия / `deepseek-flash[1m]`.
**Review:** `architect`, `code-reviewer`, `security-auditor`
(`deepseek-v4-pro`, text-only) — план и реализация **ACCEPT** после
устранения условий.
**Основание:** BA-PLAT-4.2 §2.14.2/§2.14.7; R-033; R-035;
`docs/tasks/BA-ZIP-WORKER-001_PLAN.md`.
**Драйвер:** отдельный Docker Compose-сервис (решение владельца 2026-11-20).

## 1. Цель и границы

Изолированный Celery-воркер распаковки недоверенного ZIP: очередь `zip`,
лимиты CPU/RAM/time/disk/network, отмена, аудит. Исходный ZIP неизменен,
распаковка вне веб-корня, игровой код не исполняется.

Не входит: upload endpoint, manifest/catalog/locales, SDK injection,
публикация, антивирус, DB-модель аудита, R-035 (fsync/error taxonomy),
retention `zip_uploads`, graceful SIGTERM-cancel.

## 2. Реализация

| Файл | Назначение |
|---|---|
| `apps/pipeline/services/worker.py` | job lifecycle: UUID-каталог, O_NOFOLLOW/fstat/`/proc/self/fd`, COMPLETED/ATTEMPTS/.lock/audit, flock, statvfs, cancel, cleanup |
| `apps/pipeline/tasks.py` | `extract_zip_task`, `cleanup_zip_staging`, `enqueue_extraction(queue="zip")` |
| `apps/pipeline/services/unpack.py` | аддитивный `cancel_check` (default `None`), `X_CANCELLED` |
| `config/settings/base.py` | изолированные очереди/exchange, routes, annotations (acks_late/reject_on_worker_lost/55/60), beat cleanup, `ZIP_*` |
| `compose.yml` | сервис `zip-worker`, сеть `zipnet`, тома, hardening, resource limits |
| `compose.dev-lite.yml` / `compose.staging.yml` | dev-зеркало (`/app:ro`) и staging env |
| `Dockerfile` | `mkdir/chown /var/ba/zip/{uploads,artifacts}` до `USER app` |
| `infra/scripts/entrypoint-zip-worker.sh` | ожидание только `redis-broker` |
| `apps/core/logging.py` | JSON-поля аудита |
| `tests/unit/test_zip_worker.py`, `test_zip_worker_compose.py`, `test_zip_extract.py` | 22 новых теста |

### Изоляция

- `zip-worker` только в `zipnet` (`internal: true`) вместе с `redis-broker`;
  db, redis-cache и внешний DNS недоступны.
- `read_only` rootfs, `cap_drop: ALL`, `no-new-privileges`, default seccomp,
  user 10001, `pids_limit=64`, `mem_limit=512m`, `cpus=1.0`,
  `/tmp` tmpfs 64m, `stop_grace_period=30s`.
- `zip_uploads` (web rw / worker ro) — source + CANCEL; `zip_artifacts`
  (worker rw / web ro) — result + маркеры.
- Очереди: `default/default`, `celery/celery`, `zip/zip`; обычный worker
  запускается `-Q default,celery`, zip-worker — `-Q zip`.

### Жизненный цикл

`received` → проверка UUID → lock → ATTEMPTS≥2 → quarantine → source
(O_NOFOLLOW + `O_NONBLOCK` + fstat + `/proc/self/fd`, `(deleted)` fail-closed)
→ COMPLETED reuse/conflict (SHA-256, corrupt marker → redo) → statvfs reserve
150 МБ → CANCEL → ATTEMPTS++ → `extract_zip` (deadline 50 с, cancel каждые
64 КиБ) → post-extract ≤120 МБ → COMPLETED.json (fsync+replace) → `complete`.
Ошибки `ExtractionError` → rejected/timeout/cancelled с audit; hard-kill
оставляет ATTEMPTS и обрабатывается cleaner.

## 3. Фактические проверки

```text
pytest tests/unit/test_zip_worker.py ...        -> 49 passed (ZIP subset)
pytest (full)                                   -> 330 passed, 2 skipped, 1 warning
ruff check apps config tests                    -> All checks passed
ruff format --check                             -> 348 files already formatted
mypy                                            -> Success: no issues found in 321 source files
docker compose config --quiet                   -> OK
./verify_stack.sh                               -> СТЕК ЗДОРОВ
zip-worker healthcheck (prefork)                 -> healthy
```

Изоляция и права (факт):

```text
docker inspect zip-worker: readonly=true pids=64 mem=536870912
  nanocpus=1000000000 capdrop=[ALL] sec=[no-new-privileges:true]
  networks=breaktime-arcade_zipnet
volumes: /var/ba/zip/artifacts rw, /var/ba/zip/uploads ro
probe from zip-worker: redis-broker 0; db/cache/api.deepseek.com -> gaierror
artifacts write OK; uploads write -> Read-only file system
owning user: uid=10001(app) gid=10001(app)
```

Очередь и E2E:

```text
worker queues: default exchange=default key=default; celery exchange=celery key=celery
zip-worker queues: zip exchange=zip key=zip
E2E: web -> uploads/<uuid>/source.zip -> enqueue_extraction() ->
     zip-worker -> artifacts/<uuid>/COMPLETED.json
audit: received(attempts=0) -> extract(attempts=1, limits deadline_s=50,
       max_zip_bytes=26214400) -> complete(attempts=1)
regular worker: no receipt for the job
```

## 4. Review

- План: `code-reviewer`/`security-auditor` — **ACCEPT WITH CONDITIONS**;
  условия C-1…C-6/S-1…S-6/M-1…M-6 закрыты до кода (prefork, явные
  exchange/route, топология томов, Dockerfile chown, TOCTOU, statvfs,
  retention, overlay). Повторно — **ACCEPT**.
- Реализация: **ACCEPT WITH CONDITIONS**. Исправлено: `acks_late` в
  annotation подтверждён тестом; ATTEMPTS переносится до `extract_zip`
  (hard-kill не зацикливает redelivery); `O_NONBLOCK` против FIFO;
  `(deleted)` fail-closed; corrupt COMPLETED → redo; тест «source не
  переоткрывается»; staging overlay не ослабляет изоляцию.
- Финально: security — **ACCEPT**; code — **ACCEPT** с остатком R-036
  (pre-existing глобальный `CELERY_TASK_ACKS_LATE`, вне диффа задачи).

## 5. Остаточные риски

- **R-033** — worker isolation реализован; нет жёсткой ФС-квоты (app-layer
  + statvfs), общий брокер допускает инъекцию задач (вариант A).
- **R-035** — fsync родительского каталога/audit, method allowlist,
  раздельные коды чтения/записи — отсрочено.
- **R-036** — pre-existing глобальный `CELERY_TASK_ACKS_LATE=True` влияет на
  все задачи; решение владельца/отдельный аудит идемпотентности.
- **R-037** — retention `zip_uploads` (source/CANCEL) вне scope; volume может
  расти до очистки web/beat.
- Healthcheck под занятым child не стресс-тестирован; SIGTERM graceful-cancel
  не реализован (cleanup — cleaner).

## 6. Артефакты

```text
52f1b4b5c16f6b39506bbc12c50d2953036717bd0b5a5269b0547f3c37312ba7  apps/pipeline/services/worker.py
dcfa5a6f4ca589ee7643fb23cd8a0b918b8e49ac8649812b0928f6b9de5b2b81  apps/pipeline/tasks.py
452220036ef3c93419d27ee7e64717e67be0835aaf2c8eacc852e00f5dc394fc  apps/pipeline/services/unpack.py
4a8139148d3b90f660a7fdcb0b983f3e0ede929fe384d3efd3b31f9f44e23d82  config/settings/base.py
7e4d44d094977ee895d6983fc57b14257aa7b1adb8083e2c69355190b9a82870  compose.yml
1d1d682d418f9d32ecd72b0b3d34dd958281c3c7ccd076a762ea97edc929ed78  Dockerfile
8cf4492e4642858f0ac2c0fb5e60ba5907eff8357246257a8616c3b4445b4b74  infra/scripts/entrypoint-zip-worker.sh
3b2482a35cdb2dc90519fd6155260774305fbd66f34eb71f49d69c3a2272deb5  tests/unit/test_zip_worker.py
7d8cbf1a744602ee396024de929dec2866c568effe9ca452dd74b09526592f47  tests/unit/test_zip_worker_compose.py
```

## 7. Модели

- Основная сессия/исполнитель: `deepseek-flash[1m]` (факт — транскрипт).
- План/review: `architect`, `code-reviewer`, `security-auditor` —
  `deepseek-v4-pro`, text-only (0 tool calls).

## 8. Следующий шаг

Приёмка владельцем. Затем — R-035 hardening/publish-срез (fsync каталога,
method allowlist, раздельные коды) и решение по R-036; manifest/catalog/
locales — после выбора BA-GAME-2.2. Независимый от ZIP READY-пакет —
`BA-QUALITY-002` (dev-only).
