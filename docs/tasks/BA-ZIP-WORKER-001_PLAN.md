# BA-ZIP-WORKER-001 — Изоляция extraction worker (отдельный Compose-сервис)

- **ID:** BA-ZIP-WORKER-001
- **Статус:** **TECHNICALLY ACCEPTED** (agent, OD-TECH-001); продуктовая приёмка — владелец. Независимый Pro-review плана и реализации — **ACCEPT** (остатки — R-033/R-035/R-036/R-037)
- **Приоритет:** Critical
- **Зависимость:** BA-ZIP-EXTRACT-001 (`apps/pipeline/services/unpack.py`, accepted/IMPLEMENTED)
- **Драйвер (решение владельца 2026-11-20):** отдельный Docker-сервис в Compose. Не cgroup/systemd-run, не nsjail.
- **Цель:** изолированный Celery-воркер распаковки ZIP с лимитами CPU/RAM/time/disk/network, очередью `zip`, отменой и аудитом; исходный ZIP неизменен, распаковка вне веб-корня, игровой код не исполняется, при распаковке нет сети и исполнения.

**Автор плана:** `architect` (`deepseek-v4-pro`, text-only). Flash — исполнитель.

## 0. Решения владельца (2026-11-20)

Владелец подтвердил развилки §12:

1. **Сеть:** вариант **A** — отдельная `internal`-сеть `zipnet` только с `redis-broker`; без edge/internet/db/redis-cache. Остаточный риск TCP-до-брокера принят; вариант B — follow-up при ужесточении.
2. **Диск:** **named volume `zip_artifacts` + app-layer квота** (byte caps unpack.py + post-extract guard); жёсткая ФС-квота не требуется.
3. **Отмена:** **аддитивный `cancel_check`** в `unpack.py` разрешён (default `None`, новый код `X_CANCELLED`, обязательные regression-тесты EXTRACT-001).

Пункты §12, вытекающие из этих решений, принимаются как план-дефолты: таймауты 50/55/60; аудит — structured JSON-логи без DB; общий `redis-broker`; R-035 остаётся отсроченным (non-blocking, отдельный срез); `noexec` — bind-mount в dev/staging, app-layer strip в prod (остаточный риск).

### 0.1. Ревизия 2 — условия независимого Pro-review

`code-reviewer` и `security-auditor` (deepseek-v4-pro, text-only) вернули **ACCEPT WITH CONDITIONS**, блокеров нет. Условия закрываются так (эта секция имеет приоритет над текстом разделов 3–8):

| # | Находка | Решение ревизии 2 |
|---|---|---|
| C-1 | Обычный worker без `-Q` потребляет и очередь `zip` | Обычный worker запускается строго `-Q default,celery`; в `CELERY_TASK_QUEUES` объявлена `zip`; точные `CELERY_TASK_ROUTES`; тест «обычный worker не исполняет zip-задачу». |
| C-2 | `--pool=solo` не поддерживает time limits | zip-worker: `--pool=prefork --concurrency=1` (time limits работают, main-процесс отвечает на control). Cooperative deadline 50 с; soft 55; hard 60. Совместимость с `read_only` проверить фактически. |
| C-3 | Топология томов не покрывает результат и отмену | `zip_uploads`: web **rw**, zip-worker **ro** — `<job_id>/source.zip` + `<job_id>/CANCEL`. `zip_artifacts`: zip-worker **rw**, web **ro** — `<job_id>/{COMPLETED.json,ATTEMPTS,.lock,audit.jsonl,result/}`. Web узнаёт о завершении по `COMPLETED.json`; отмена — только через `CANCEL` в uploads. |
| C-4 | Redelivery без `reject_on_worker_lost` | `acks_late=True` + `task_reject_on_worker_lost=True` + `prefetch=1`; per-job `fcntl.flock` на `artifacts/<job_id>/.lock`; ATTEMPTS ≥2 → карантин. |
| C-5 | Named volume root-owned, user 10001 не пишет | В Dockerfile (runtime, до `USER app`): `mkdir -p /var/ba/zip/uploads /var/ba/zip/artifacts && chown -R app:app /var/ba/zip`. Образ пересобирается — причина обоснована. |
| C-6 | `inspect ping` флапает, пока solo занят | Prefork main отвечает на control во время работы child; healthcheck `interval=30s, timeout=15s, retries=3, start_period=30s`; проверить под нагрузкой. |
| S-1 | TOCTOU/symlink на source | Открывать source через `os.open(O_RDONLY|O_NOFOLLOW)`, `fstat` → `S_ISREG`, сверять `/proc/self/fd/<fd>` с разрешённым корнем; запрет FIFO/device/symlink; читать только из fd. |
| S-2 | Нет жёсткой ФС-квоты | Перед job: `statvfs` reserve ≥150 МБ; после extract: проверка размера job ≤120 МБ; cleaner TTL; остаток (общий раздел) — в RISK_REGISTER. |
| S-3 | Cleaner без rw к artifacts | Cleaner — Celery-задача в очереди `zip`, исполняется zip-worker (rw artifacts); beat только ставит задачу. |
| S-4 | Инъекция задач в общий брокер | Остаток варианта A принят владельцем; `job_id` генерирует только web; path/job валидируются; отдельный брокер/ACL — follow-up. |
| S-5 | Права 10001 на тома | См. C-5; каталоги 0700, файлы 0600; web читает artifacts ro. |
| S-6 | 25 МБ не гарантированы на web | Worker сам проверяет `len(zip) <= MAX_ZIP_BYTES` до распаковки (preflight уже enforce); nginx/upload limit — вне scope (нет upload endpoint), зафиксировать. |
| M-1 | Нет retention завершённых job | Cleaner: incomplete >1 ч и completed >24 ч (конфигурируемо) удаляются; audit — docker json-file 10m×3. |
| M-2 | Хрупкие тесты гонок/таймингов | Детерминированные monkeypatch-тесты; compose-инварианты — отдельный `verify`-скрипт + pytest на `docker compose config`. |
| M-3 | R-035 fsync | Остаётся отсроченным; потеря COMPLETED/audit при сбое питания — residual, cleaner восстанавливает. |
| M-4 | Overlay staging/prod | zip-worker добавлен в `compose.staging.yml` с `.env.staging`; сети/тома не расширяются; `docker compose config` проверяется. |
| M-5 | `read_only` + запись Python | `PYTHONDONTWRITEBYTECODE=1` уже в образе; `/tmp` — tmpfs 64m; проверить импорт/старт. |
| M-6 | Hard-kill не выполняет finally | Cleanup при SIGKILL делегируется cleaner; partial `.ba-extract-*` в artifacts удаляются; зафиксировать в отчёте. |

---



## 1. Ссылки на требования и acceptance criteria

- [FACT] BA-PLAT-4.2 §2.14.2: ZIP ≤25 МБ, распакованный ≤100 МБ, ratio ≤100:1, ≤2000 файлов, ≤20 МБ/файл; «распаковка — в изолированном временном каталоге с квотой, вне веб-корня, без прав на исполнение».
- [FACT] BA-PLAT-4.2 §2.14.7: отчёт построчный.
- [FACT] Анализ ZIP ≤25 МБ — ≤60 с, Celery, прогресс в CRM.
- [FACT] R-033 (RISK_REGISTER): container/cgroup/seccomp, дисковая квота, timeout, отмена, аудит; web-layer лимит тела.
- [FACT] R-035 (открыт, minor): fsync перед rename, method allowlist, раздельные коды OSError (bzip2-read vs write) — закрывается в worker/publish слое.
- [FACT] Инварианты CLAUDE.md: исходный ZIP неизменен; распаковка вне веб-корня; игровой код не исполняется в Django; никакой сети/исполнения при распаковке; падение одной игры не ломает портал; ZIP — единственный канал импорта.

Acceptance criteria (AC) — см. раздел 8.

---

## 2. Факты текущего состояния

- [FACT] `apps/pipeline/services/unpack.py` (311 строк, accepted): `extract_zip(data, destination, *, max_file_bytes, max_total_bytes, max_files, deadline) -> ExtractionResult`; повторный `preflight_zip`; streaming 64 КиБ; независимый byte count; CRC; канонические пути; `O_EXCL|O_NOFOLLOW`; staging `tempfile.mkdtemp(prefix=".ba-extract-", dir=destination.parent)`; атомарный `rename`; cleanup при ошибке; `deadline` — абсолютный `time.monotonic`.
- [FACT] Коды ошибок: `X_PREFLIGHT_REJECTED`, `X_DESTINATION_EXISTS`, `X_LIMIT_FILE/TOTAL/FILES`, `X_PATH_UNSAFE`, `X_PREFIX_CONFLICT`, `X_CRC_MISMATCH`, `X_SIZE_MISMATCH`, `X_ARCHIVE_BAD`, `X_TIMEOUT`, `X_IO`.
- [FACT] `ExtractionResult(root, package_hash, files, total_bytes, preflight)`.
- [FACT] `apps/pipeline/tasks.py` пустой (0 байт); `apps/pipeline/services/intake.py`, `artifacts.py`, `models/*` пустые; GameImportDraft/GameVersion не реализованы.
- [FACT] Celery `config/celery.py`: `Celery("breaktime")`, `config_from_object("django.conf:settings", namespace="CELERY")`, autodiscover; broker `redis://redis-broker:6379/2`, result backend None, `ACKS_LATE=True`, `prefetch=1`, retry on startup; `CELERY_TASK_ROUTES` отсутствует.
- [FACT] `compose.yml`: web/worker/beat на `internal`+`edge`; db/redis на `internal`; nginx `edge`+`internal`; сети `internal:{internal:true}`, `edge:{}`; `x-app`: user 10001, `no-new-privileges`, `cap_drop: ALL`, volumes static/media/app_var, deploy limits; worker healthcheck `celery -A config inspect ping -d celery@$HOSTNAME`.
- [FACT] `compose.dev-lite.yml`: worker `--pool=solo --concurrency=1`, db/redis limits, nginx 8443.
- [FACT] nginx dev: `client_max_body_size 30m` глобально.
- [FACT] Dockerfile `ENTRYPOINT /app/infra/scripts/entrypoint.sh` всегда ждёт db:5432, redis-cache:6379, redis-broker:6379, затем migrate/collectstatic по env.
- [FACT] Стек фиксирован: Python 3.14, Django 5.2, Celery 5.7, PostgreSQL 18, Redis 8; новых зависимостей нет без согласования.

[ASSUMPTION] `deploy.resources` в `x-app` при обычном `docker compose up` (не swarm) не применяется; для zip-worker нужно использовать не-swarm-директивы `cpus`/`mem_limit`/`pids_limit`/`ulimits`. Требует подтверждения по факту при реализации.

---

## 3. Архитектурные решения (ответы на 8 вопросов)

### 3.1 Сеть (вопрос 1) — рекомендация: вариант A

**Вариант A — dedicated internal network только с redis-broker.**
Отдельная сеть `zipnet: {internal: true}`. К ней подключены только `zip-worker` и `redis-broker`. Zip-worker НЕ имеет `edge`, НЕ видит db/redis-cache/internet. Брокер по TCP `redis://redis-broker:6379/2`.
- Плюсы: минимальный диф; без изменений образа/конфига Redis; стек Celery сохраняется; entrypoint zip-worker ждёт только redis-broker (новый скрипт, раздел 4).
- Минусы/остаток: TCP-канал до брокера есть (неизбежно для Celery); разделяемая очередь даёт теоретическую инъекцию задач в брокер.
- Снижение остатка: `read_only` rootfs, `cap_drop: ALL`, `no-new-privileges`, default seccomp; опционально (на будущее) отдельный инстанс брокера или Redis ACL. Отметить владельцу.

**Вариант B — Unix-socket брокер + `network_mode: none`.**
Redis `unixsocket` на shared volume + `port 0`; Celery `redis+socket://...`; zip-worker полностью без сети.
- Плюсы: строго «нет сети» на уровне namespace.
- Минусы: конфиг Redis-образа, права unix-socket (uid 10001 в обоих контейнерах), совместимость синтаксиса `redis+socket://` в Celery 5.7 — [ASSUMPTION]/не проверено; усложнение healthcheck; риск «усилил с одной стороны — сломал с другой» в рамках 2 итераций.
- Вывод: не сейчас, как follow-up при ужесточении.

**Вариант C — file-spool без Celery.** Отвергается: нарушает фиксированный стек (Celery 5.7).

**Рекомендация:** A. Это минимально достаточная изоляция для R-033 и инварианта «нет сети при распаковке» (нет edge/internet/db/cache). Полный «нет TCP» (B) — только если владелец сочтёт TCP-до-брокера критичным.

**Entrypoint без ослабления сети:** новый `infra/scripts/entrypoint-zip-worker.sh` (общий entrypoint.sh НЕ трогаем): ждёт только redis-broker:6379 (с таймаутом), НЕ ждёт db/redis-cache, НЕ делает migrate/collectstatic, затем `exec celery -A config worker -Q zip -n zip@%h --pool=solo --concurrency=1 --prefetch-multiplier=1`. Это убирает необходимость давать zip-worker сеть до db/cache.

### 3.2 Staging/результат (вопрос 2) — рекомендация: dedicated named volume, не tmpfs

- **Результат и staging — на одном dedicated named volume `zip_artifacts`** (монтируется в `/var/ba/zip/artifacts`). Причина: unpack.py делает `mkdtemp(dir=destination.parent)` и атомарный `rename` — оба должны быть на одной ФС, иначе EXDEV и повторное открытие EXTRACT-001. Результат должен переживать рестарт (для последующих publish-срезов), поэтому tmpfs как финальное хранилище не годится (RAM, теряется при рестарте).
- **Квота = два слоя:** (1) существующие in-process лимиты unpack.py (100 МБ total / 20 МБ файл / 2000 файлов / ratio 100:1) — основной; (2) post-rename guard: `os.statvfs`/du по каталогу job с hard cap (например, 120 МБ) + проверка, что нет исполняемых битов (chmod 0644 в unpack или post-check). Жёсткая ФС-квота в Compose на WSL2 без backing-device/XFS project quota недостижима — [OPEN], принять «app-layer quota + мониторинг».
- **Пережить рестарт/redelivery:** детерминированный каталог job `<job_id>/`; маркер `COMPLETED.json` (package_hash, files, total_bytes, ts). ACKS_LATE + prefetch 1 → при рестарте/краше задача redeliverится; перед распаковкой: если `COMPLETED.json` совпадает с package_hash источника — вернуть кэш (idempotent, аудит `reused`); если есть частичное `.ba-extract-*`/`result` без маркера — удалить и распаковать заново. Счётчик `ATTEMPTS` в job-каталоге: при ≥2 неудачных попытках — карантин + аудит, не re-extract (защита от redelivery-цикла).
- **Orphan staging cleanup:** Beat-задача `cleanup_zip_staging` (маршрутизируется в очередь `zip`, исполняется zip-worker, имеющим rw к `zip_artifacts`) удаляет `.ba-extract-*`, незавершённые job-каталоги старше 1 ч, завершённые `COMPLETED.json` старше 24 ч и пустые каталоги. `zip_uploads` в zip-worker смонтирован `:ro`; источник и `CANCEL`-маркер пишет только web. **Ревизия 2:** retention завершённых job обязателен, иначе volume растёт бесконечно.

### 3.3 Timeout (вопрос 3) — значения ≤60 с

- In-task cooperative deadline: `deadline = time.monotonic() + 50` → unpack.py штатно поднимает `X_TIMEOUT`.
- Celery `task_soft_time_limit = 55` (SoftTimeLimitExceeded → cleanup + маппинг в `X_TIMEOUT`, аудит timeout).
- Celery `task_time_limit = 60` (SIGKILL fallback; ACKS_LATE гарантирует redelivery без молчаливой потери).
- Запас 5 с между soft и hard — на cleanup staging. Соответствует §2.14 (≤60 с).
- **Ревизия 2:** `--pool=solo` не поддерживает time limits; используется `--pool=prefork --concurrency=1`. Main-процесс prefork отвечает на `inspect ping` во время работы child.

### 3.4 Отмена (вопрос 4) — двухуровневая, cleanup гарантирован

- Уровень 1 (без изменения unpack.py): `celery revoke <task_id>` (без terminate) для ещё не стартовавших задач + файл-маркер `zip_uploads/<job_id>/CANCEL` (пишет web, читает zip-worker), проверяемый задачей перед началом и в `cancel_check`. Для уже запущенной задачи верхняя граница отмены — soft/hard timeout 55/60 с.
- Уровень 2 (рекомендуемое аддитивное изменение unpack.py): необязательный параметр `cancel_check: Callable[[], bool] | None = None`, проверяемый в streaming-цикле (каждые N КиБ) → новый код `X_CANCELLED`. Изменение **аддитивное, default None = текущее поведение**, не открывает повторно приёмку EXTRACT-001. [ASSUMPTION] владелец/security одобрят такой точечный апгрейд; иначе — остаётся только Уровень 1 + 60-секундная граница.
- **Cleanup:** try/finally в задаче удаляет job-каталог при не-success; Beat cleaner — backstop. unpack.py уже чистит свой `.ba-extract-*` при ошибке; rename только при успехе → частичное дерево не остаётся.

### 3.5 Аудит (вопрос 5) — structured JSON logs, не DB-модель

DB-модель отклоняется: она требует сетевой доступности db у zip-worker, что противоречит изоляции §3.1; иначе — второй hop через web (вне scope). Выбор: **structured JSONL на stdout** (docker log driver) + опциональный файл `<job_id>/audit.jsonl` на volume; формирование через stdlib `logging` + JSON-форматер (без новой зависимости, `structlog` не добавлять).
Минимальный набор полей на событие:
`ts`, `job_id`, `task_id`, `event` (`received|preflight|extract|complete|reused|timeout|cancelled|rejected|cleanup|quarantine`), `package_hash`, `zip_bytes`, `extracted_bytes`, `file_count`, `duration_ms`, `outcome`, `error_code`, `limits` (`max_file_bytes`, `max_total_bytes`, `max_files`, `deadline_s`), `attempts`, `node`, `queue`. Секретов нет.

### 3.6 Очередь и API задачи (вопрос 6) — path, не bytes

- Очередь `zip`, routing key `zip`, отдельный воркер `-Q zip --hostname zip@%h` (healthcheck `celery -A config inspect ping -d zip@$HOSTNAME`).
- `CELERY_TASK_ROUTES = {"apps.pipeline.tasks.extract_zip_task": {"queue": "zip"}, "apps.pipeline.tasks.cleanup_zip_staging": {"queue": "zip"}}`; `CELERY_TASK_QUEUES` объявляет `default`, `celery`, `zip`; обычный worker запускается строго `-Q default,celery` (иначе он потребляет `zip`). `CELERY_TASK_REJECT_ON_WORKER_LOST = True`; per-job `flock` на `zip_artifacts/<job_id>/.lock` против двойной обработки.
- **API задачи — по пути, не по bytes:** web пишет загруженный ZIP в shared volume `zip_uploads/<job_id>/source.zip`, ставит задачу `extract_zip_task(path, job_id)`. Bytes в брокер отвергаем: 25 МБ на сообщение раздувает Redis `noeviction` и дублирует память. Путь стабилен при redelivery → идемпотентность.
- Валидация в задаче: `job_id` строго UUID (`^[0-9a-fA-F-]{36}$`); `path` после `resolve()` обязан лежать внутри `zip_uploads` root (запрет `..`, абсолютных путей, symlink-выхода). `zip_uploads` в zip-worker смонтирован `:ro`.

### 3.7 Seccomp/rootfs/pids/ulimits (вопрос 7) — минимальный рабочий набор на WSL2

- `security_opt: [no-new-privileges:true]` (уже есть), `cap_drop: [ALL]` (уже есть).
- **Seccomp:** оставить default Docker-профиль (НЕ ставить `seccomp=unconfined`). Кастомный профиль блокировки `socket/connect` эквивалентен варианту B — не сейчас.
- `read_only: true` (rootfs) + `tmpfs: ["/tmp:rw,size=64m,mode=1777"]` (Python/Celery пишут во временные файлы). Изоляция результатов через rw `zip_artifacts`, вход rw только у web.
- `pids_limit: 64`, `ulimits: {nofile: {soft: 1024, hard: 1024}}`.
- `cpus: "1.0"`, `mem_limit: 512m` (256m — минимум; бюджет: Python ~100 МБ + streaming 64 КиБ + tmpfs 64m). Не `deploy.resources` (см. [ASSUMPTION]).
- `--pool=prefork --concurrency=1` (time limits работают; main-процесс отвечает на control; совместимость с read_only rootfs проверить).
- В Dockerfile (runtime, до `USER app`): `mkdir -p /var/ba/zip/uploads /var/ba/zip/artifacts && chown -R app:app /var/ba/zip` — иначе named volume создаётся root-owned и user 10001 не пишет (проверено фактически).
- `stop_grace_period: 30s` (время на cleanup при остановке).
- Всё выше — поддерживается Compose на WSL2 (cgroup v2).

### 3.8 R-035 (вопрос 8) — рекомендация: отложить

fsync/method allowlist/раздельные коды — это внутренности extraction-слоя; unpack.py уже принят. Включение их в этот срез смешивает две задачи и повторно открывает приёмку EXTRACT-001. В BA-ZIP-WORKER-001 из unpack.py трогаем только аддитивный `cancel_check` (§3.4). R-035 — отдельным малым follow-up (publish/hardening-срез), либо немедленно после, если владелец настоит. Решение — владельцу.

---

## 4. Минимальный список файлов (без миграций)

Создать:
- `apps/pipeline/tasks.py` — `extract_zip_task(path, job_id)` + `cleanup_zip_staging()`.
- `apps/pipeline/services/worker.py` — layout job-каталога, валидация путей (O_NOFOLLOW/fstat/S_ISREG), маркеры COMPLETED/ATTEMPTS/CANCEL, per-job lock, cleanup, JSON-аудит, statvfs-guard и post-extract size check.
- `infra/scripts/entrypoint-zip-worker.sh` — wait redis-broker only, без migrate/collectstatic, exec `celery -A config worker -Q zip -n zip@%h --pool=prefork --concurrency=1 --prefetch-multiplier=1 --without-gossip --without-mingle`.
- `apps/pipeline/tests/test_zip_worker.py` + `tests/test_compose_zip_worker.py` (или verify-скрипт для compose).

Изменить:
- `compose.yml` — сервис `zip-worker`; сеть `zipnet`; `redis-broker` в `zipnet`; volumes `zip_uploads`, `zip_artifacts`; healthcheck; не-swarm лимиты `cpus`/`mem_limit`/`pids_limit`/`ulimits`.
- `compose.dev-lite.yml` — зеркало zip-worker (prefork/concurrency 1, dev-лимиты).
- `compose.staging.yml` — zip-worker с `.env.staging`, без расширения сетей.
- `config/settings/base.py` — `CELERY_TASK_ROUTES`, `CELERY_TASK_QUEUES`, `CELERY_TASK_SOFT_TIME_LIMIT`/`TIME_LIMIT`, `CELERY_TASK_REJECT_ON_WORKER_LOST`, `CELERY_BEAT_SCHEDULE` для cleanup, `ZIP_WORKER` (корни, `deadline_s=50`, TTL, лимиты).
- `compose.yml` worker command — строго `-Q default,celery`.
- `Dockerfile` — mkdir/chown `/var/ba/zip/{uploads,artifacts}` до `USER app`; образ пересобирается.
- `apps/pipeline/services/unpack.py` — ТОЛЬКО опциональный аддитивный `cancel_check` + `X_CANCELLED`.

Docs (пост-реализация, стандартный workflow): `NOW.md`, `PROJECT_STATUS.md`, `BACKLOG.md`, шесть реестров, указать модели.

Без: миграций, новых зависимостей, изменений Redis-конфига, изменений общего `entrypoint.sh`. Пересборка образа — только из-за mkdir/chown.

---

## 5. Схема сетей/томов

Сети:
- `internal` (сущ.), `edge` (сущ.) — без изменений.
- `zipnet: {internal: true}` — только `zip-worker` и `redis-broker`.

Доступность zip-worker: redis-broker (TCP 6379) — да; db, redis-cache, edge/internet, nginx — нет.

Тома:
- `zip_uploads` — web rw, zip-worker `:ro` (`/var/ba/zip/uploads`): `<job_id>/source.zip` и `<job_id>/CANCEL`.
- `zip_artifacts` — zip-worker rw, web `:ro` (`/var/ba/zip/artifacts`): `<job_id>/result/`, `COMPLETED.json`, `ATTEMPTS`, `.lock`, `audit.jsonl`. Beat только ставит cleanup-задачу, том ему не нужен.
- rootfs `read_only`, `/tmp` — tmpfs 64m.
- Владелец томов — 10001:10001 (mkdir/chown в образе); каталоги 0700, файлы 0600.

Layout job: `/var/ba/zip/uploads/<job_id>/source.zip`; `/var/ba/zip/artifacts/<job_id>/{result/,COMPLETED.json,ATTEMPTS,.lock,audit.jsonl}`.

---

## 6. Security/backward-compat риски и снижение

1. Инъекция задач в общий redis-broker при компрометации zip-worker — остаточный риск варианта A. Снижение: dedicated net, read_only, cap_drop ALL, no-new-privileges, default seccomp, отдельный `--without-gossip --without-mingle`; жёсткое устранение — отдельный брокер/ACL или вариант B (владелец).
2. Регресс EXTRACT-001 — только аддитивный `cancel_check` (default None); обязательные regression-тесты unpack; при любой неаддитивной необходимости — stop/эскалация.
3. EXDEV при раздельных ФС staging/result — устранено единым volume.
4. read_only rootfs vs временные файлы Python/Celery — tmpfs `/tmp` + `--pool=solo`.
5. `deploy.resources` может не работать в plain compose — использовать `cpus`/`mem_limit`/`pids_limit`/`ulimits` явно.
6. `noexec` на named volume недоступен в Compose — bind-mount `:noexec` в dev/staging; в prod — strip exec-битов (0644) + «не исполняем по дизайну»; паритет dev/prod — [OPEN] владельцу.
7. Redelivery-цикл на «отравленном» ZIP — счётчик ATTEMPTS ≥2 → карантин + аудит.
8. Отсутствие db-доступа у zip-worker при autodiscover — импорт моделей ленив; migrate не нужен (без-DB задача); проверить отсутствие DB-обращений в `ready()`/import при старте воркера.
9. Аудит без секретов; пути/хеши — не секреты; логгер без `DEBUG`-вывода содержимого.

---

## 7. Тестовая матрица

- **Happy path:** валидный ZIP → распаковка, `COMPLETED.json`, аудит `complete`, корректные bytes/files/package_hash.
- **Лимиты:** >100 МБ total, >20 МБ/файл, >2000 файлов, ratio >100:1, вход >25 МБ → `X_LIMIT_*`/`X_PREFLIGHT_REJECTED`, cleanup, аудит `rejected`.
- **Edge:** пустой ZIP, 0 файлов, один максимальный файл, bzip2, unicode-имена, вложенные каталоги, symlink внутри ZIP (`X_PATH_UNSAFE`), Zip Slip.
- **Отказ:** битый архив (`X_ARCHIVE_BAD`/`X_CRC_MISMATCH`/`X_SIZE_MISMATCH`), destination существует (`X_DESTINATION_EXISTS`), OSError чтения/записи.
- **Гонки/redelivery:** kill воркера в середине → redelivery → идемпотентный redo; два конкурентных `job_id` → один побеждает, второй видит COMPLETED/conflict; ATTEMPTS ≥2 → карантин.
- **Timeout:** медленный/зависший ридер (monkeypatch) → `X_TIMEOUT`, cleanup, аудит `timeout`; soft 55 < hard 60.
- **Cancel:** revoke до старта (не выполняется); `CANCEL`-маркер mid-run (если `cancel_check`) → `X_CANCELLED`, cleanup, аудит `cancelled`.
- **Cleanup:** orphan `.ba-extract-*`/job-каталоги без маркера старше TTL удаляются Beat-задачей; пустые каталоги удаляются.
- **Compose-инварианты:** `docker compose config` для base/dev-lite/staging — zip-worker только в `zipnet`; нет edge/internal/db/cache сетей; `read_only: true`; tmpfs `/tmp`; `pids_limit`/`mem_limit`/`cpus`; `cap_drop: ALL`; `no-new-privileges`; healthcheck; volumes принадлежат 10001.
- **Изоляция очереди:** обычный worker с `-Q default,celery` не исполняет `extract_zip_task`; задача остаётся в `zip`.
- **TOCTOU:** source подменён на symlink/FIFO/device между проверкой и открытием → отказ без чтения; `O_NOFOLLOW`+`fstat`+`/proc/self/fd`.
- **Statvfs/retention:** при нехватке reserve — отказ до записи; cleaner удаляет incomplete >1 ч и completed >24 ч.
- **Healthcheck под нагрузкой:** `inspect ping` отвечает, пока prefork-child занят длинной задачей.
- **Регресс EXTRACT-001:** полный набор тестов unpack зелёный.

---

## 8. Acceptance criteria

1. Zip-worker — отдельный Compose-сервис; распаковка вне веб-корня, без прав на исполнение (app-layer + bind noexec в dev/staging); user 10001; no-new-privileges; cap_drop ALL; default seccomp; нет edge/internet/db/redis-cache (вариант A); named volumes принадлежат 10001 (mkdir/chown в образе).
2. Дисковая квота: unpack.py 100/20/2000/ratio + statvfs-guard (≥150 МБ reserve) + post-extract size check (≤120 МБ); staging и результат на одном volume → атомарный rename сохранён; retention cleaner.
3. Timeout ≤60 с: prefork, cooperative 50 → `X_TIMEOUT`; soft 55; hard 60; `reject_on_worker_lost`; redelivery без потерь.
4. Отмена: revoke + `CANCEL` в `zip_uploads/<job_id>/` + аддитивный `cancel_check`; cleanup гарантирован (finally + cleaner при hard-kill).
5. Аудит: одна structured JSON-запись на событие с полным набором полей (§3.5); без сырых имён файлов; cleanup аудируется.
6. Очередь `zip` только zip-worker (`-Q zip`), обычный worker — строго `-Q default,celery`; web ставит задачу по path; брокер не раздут bytes; тест изоляции очереди.
7. Идемпотентность/redelivery: per-job flock; COMPLETED → reuse; частичное → redo; ATTEMPTS-карантин; TOCTOU-защита source (O_NOFOLLOW/fstat/S_ISREG).
8. Без миграций и новых зависимостей; unpack.py только аддитивный `cancel_check`; `make check`/pytest зелёный; `docker compose config` валиден для base/dev-lite/staging; healthcheck zip-worker проходит под нагрузкой.

---

## 9. План review

Pkg 0 (выполнено): `code-reviewer` и `security-auditor` (text-only) — **ACCEPT WITH CONDITIONS**, блокеров нет; условия C-1…C-6/S-1…S-6/M-1…M-6 закрыты в ревизии 2 (§0.1). Повторный review плана — **ACCEPT**.

Pkg 4 (выполнено): реализация проверена теми же Pro — **ACCEPT**. Закрыты: `acks_late` в annotation, ATTEMPTS до `extract_zip`, TOCTOU source (extract получает уже провалидированные bytes; тест), FIFO (`O_NONBLOCK`), `(deleted)` fail-closed, corrupt COMPLETED → redo, staging overlay не ослабляет изоляцию. Остатки: R-033 (нет жёсткой ФС-квоты, общий брокер), R-035 (fsync/error taxonomy), R-036 (pre-existing глобальный `CELERY_TASK_ACKS_LATE`), R-037 (retention `zip_uploads`), healthcheck под нагрузкой не стресс-тестирован, SIGTERM-cancel не реализован.

Критерии accept: AC 1–8; отсутствие регресса EXTRACT-001; отсутствие network-escape; аудит и cleanup полные; timeout/cancel рабочие. Reject: нарушение изоляции сети, отсутствие аудита, утечка orphan staging, неаддитивное изменение unpack.py, новая зависимость/миграция без согласования.

---

## 10. Stop conditions / лимит итераций

- Максимум **2 итерации исправлений** после каждого ревью-гейта.
- Stop + эскалация владельцу с письменным списком рисков, если после 2 итераций остаётся Critical-находка.
- Stop, если изоляция сети достижима только ценой ослабления общего entrypoint/ожидания db — тогда переход к варианту B.
- Stop, если unpack.py требует неаддитивного изменения (повторное открытие EXTRACT-001).
- Stop, если понадобится миграция/новая зависимость/новый образ — только после явного согласования владельца.

---

## 11. Не входит

Upload endpoint, manifest/catalog/locales, SDK injection, публикация, антивирус, исполнение игрового runtime, App F, DB-модель аудита (deferred), R-035 (deferred), кастомный seccomp-профиль / `network_mode: none` (если не выбран B), cgroup/systemd-run/nsjail, preview/autotest.

---

## 12. Решения, требующие владельца

1. **Уровень сетевой изоляции:** A (dedicated internal net только до redis-broker, рекомендация) или B (`network_mode: none` + unix-socket broker). Остаточный риск A — TCP до брокера и теоретическая инъекция задач в общую очередь.
2. **Дисковая квота:** принять app-layer квоту (unpack.py + post-guard + мониторинг) без жёсткой ФС-квоты под Compose/WSL2 — или требовать backing-device/XFS/tmpfs (противоречит персистентности и атомарному rename).
3. **R-035:** подтвердить отсрочку на следующий срез.
4. **Аддитивный `cancel_check` в unpack.py** (default None): разрешить для полноценной отмены, либо ограничиться revoke + 60-с границей.
5. **Значения таймаутов** 50/55/60 — подтвердить.
6. **Аудит только JSON-логи (без DB)** — подтвердить (DB-модель конфликтует с изоляцией сети).
7. **Общий redis-broker** сейчас или отдельный инстанс/Redis ACL для zip-очереди.
8. **Паритет `noexec`** dev/staging (bind-mount) vs prod (app-layer strip).

---

## 13. Разбиение на пакеты

- **Pkg 0 — Plan gate:** этот план + текстовый ревью code-reviewer/security-auditor до кода.
- **Pkg 1 — Compose-изоляция:** сервис zip-worker, сеть `zipnet`, volumes, `entrypoint-zip-worker.sh`, ресурсные директивы, healthcheck, `CELERY_TASK_ROUTES`/timeout/beat settings, `docker compose config` + non-functional compose-тест.
- **Pkg 2 — Задача:** `tasks.py` + `services/worker.py` (path-валидация, layout, deadline, аудит, cleanup, идемпотентность, ATTEMPTS), опциональный `cancel_check`.
- **Pkg 3 — Отмена + cleanup:** `CANCEL`-маркер/revoke, Beat orphan cleaner, финализация JSON-аудита.
- **Pkg 4 — Тесты + docs + приёмка:** полная тестовая матрица, обновление NOW/PROJECT_STATUS/BACKLOG/шести реестров, Pro-ревью, приёмка владельцем.

После каждого пакета — update NOW/реестров/статуса (стандартный workflow) и указание моделей/сервисов.
