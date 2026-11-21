# R-036 — глобальный `CELERY_TASK_ACKS_LATE=True`: анализ

**Дата:** 2026-11-21
**Статус:** **ANALYSIS COMPLETED / AWAITING OWNER DECISION**; поведение
не изменялось.
**Автор:** `architect` (`deepseek-v4-pro`, text-only); факты сверены Flash.
**Область:** `config/settings/base.py`; задачи `crm.*`, `accounts.*`,
`catalog.*`, `pipeline.*`.

## 1. Проверенные факты

- `CELERY_TASK_ACKS_LATE=True` — pre-existing baseline `86cc56b`; не введён
  ZIP-задачей.
- `CELERY_TASK_REJECT_ON_WORKER_LOST` не задан → `None` (эффективно `False`).
- `CELERY_TASK_ACKS_ON_FAILURE_OR_TIMEOUT=True` (Celery 5.7.0 дефолт;
  подтверждено `app.conf`).
- `broker_transport_options={}` → Redis `visibility_timeout` дефолт 3600 с.
- Обычный worker: base/staging — prefork (celery default); dev-lite — solo.
  `backup_full`/`restore_check` идут в обычном worker; ZIP — отдельный
  prefork `zip-worker`.
- `crm.backup_status_alert` — только логи (без писем/уведомлений).
- `backup_full` не имеет id вызова/идемпотентного ключа: каждый запуск
  создаёт новый `BackupRun` и файл; ротация.
- `restore_check` делает DROP/CREATE `ba_restore_check`, затем pg_restore;
  повторный/параллельный запуск не безопасен.
- `anonymize_due_accounts` выбирает `UserProfile.deleted_at IS NULL`; после
  `anonymize_user` профиль удаляется, поэтому повторный проход по тем же
  данным — no-op; `cleanup_expired_account_records` идемпотентен по
  expired-предикатам.
- `catalog.refresh_catalog_search_vectors` — идемпотентный UPDATE;
  pipeline tasks защищены lock/ATTEMPTS/reuse.

## 2. Семантика доставки (Celery 5.7 + Redis)

- `acks_late=True` → at-least-once: ack после завершения; падение до ack
  может дать повторную доставку.
- `reject_on_worker_lost=False` (текущее) при убитом child (OOM/SIGKILL/
  hard limit), родитель жив → **ack, тихая потеря**. `True` → reject+requeue,
  возможен дубль.
- Падение всего worker/контейнера → unacked → redelivery через
  `visibility_timeout` (~3600 с) независимо от `reject_on_worker_lost`.
- `acks_on_failure_or_timeout=True` → обычные исключения и soft timeout
  подтверждаются, бесконечной редрставки из-за детерминированных ошибок
  нет.
- Exactly-once на транспорте нет; дубли гасятся идемпотентностью.

### Матрица сценариев (текущая конфигурация)

| Сценарий | Обычные задачи | ZIP |
|---|---|---|
| Успех | ack | ack |
| Исключение | ack | ack |
| Soft timeout | ack | ack |
| Child kill (OOM/SIGKILL/hard) | **ack → потеря** | reject+requeue |
| Падение всего worker | redelivery ~3600 с | redelivery ~3600 с |
| `self.retry()` | retry | retry |

## 3. Матрица задач

| Задача | Идемпотентна | Эффект дубля | Риск |
|---|---|---|---|
| `crm.backup_full` | **Нет** | второй `BackupRun`/dump, ротация | Высокий |
| `crm.restore_check` | **Нет** | повторный/параллельный DROP/CREATE | Высокий |
| `crm.backup_status_alert` | Да (логи) | лишние логи | Низкий |
| `accounts.anonymize_due_accounts` | Условно да (профиль удаляется) | повторный проход no-op | Средний |
| `accounts.cleanup_expired_account_records` | Да (expired) | no-op | Низкий |
| `catalog.refresh_catalog_search_vectors` | Да | лишний CPU | Низкий |
| `pipeline.extract_zip_task` | Да (lock/ATTEMPTS/idempotent reuse) | защищён | Низкий |
| `pipeline.cleanup_zip_staging` | Да | no-op | Низкий |

Одновременно есть оба риска для backup/restore: тихая потеря при child-kill
и дубль при падении всего worker.

## 4. Варианты

- **A. Оставить как есть** — 0 изменений; тихая потеря критичных задач при
  child-kill; дубль backup/restore при падении worker; непоследовательная
  семантика с ZIP.
- **B. Убрать глобальный acks_late, per-task** — at-most-once по умолчанию;
  хуже для бэкапов (потеря при любом падении после приёма).
- **C. At-most-once для side-effect + acks_late для идемпотентных** —
  исключает дубли DROP/анонимизации, но жертвует надёжностью бэкапа.
- **D. Идемпотентность/дедупликация для всех side-effect + acks_late** —
  самая корректная модель; наибольший объём.
- **E. Отдельные очереди/worker** — изоляция ресурсов; ack-политика
  per-task, не per-queue; не решает идемпотентность.
- **F. Гибрид (рекомендация)** — оставить глобальный `acks_late=True`;
  глобальный `reject_on_worker_lost` не включать; `acks_on_failure_or_timeout`
  оставить True; идемпотентные/read-only задачи — точечно
  `reject_on_worker_lost=True`; backup/restore/anonymize — сначала guard,
  затем reject; ZIP оставить.

## 5. Рекомендация

**F, поэтапно.**

### Фаза 1 — без изменения поведения (можно выполнить сейчас)
- Зафиксировать `visibility_timeout` (сейчас дефолт 3600) и семантику в
  docstrings/реестрах.
- Наблюдаемость: `worker_lost`, `redelivered`, structured call id, алерт на
  свежесть `BackupRun`.
- Контрактные тесты конфигурации задач и идемпотентности сервисов; реальный
  redelivery-тест с отдельным Redis и укороченным `visibility_timeout`
  (5–10 с), без eager.

### Фаза 2 — требует решения владельца (изменение семантики доставки)
- `backup_full`: idempotency key (beat schedule/run id), unique constraint,
  повторная доставка не создаёт второй run и не трогает ротацию.
- `restore_check`: advisory lock/маркер, один DROP/CREATE, конечное
  состояние.
- `anonymize_due_accounts`: атомарный маркер/no-op.
- После guard-ов — точечно `reject_on_worker_lost=True`; оценить задержку
  redelivery ~3600 с и `visibility_timeout` > максимальной длительности
  pg_dump/pg_restore.

### Фаза 3 — опционально
- Отдельный worker/очередь для backup/restore, concurrency=1 для
  `restore_check`.

## 6. Тест-план (если реализовывать)

1. Контракт конфигурации: `task.acks_late`, `reject_on_worker_lost`,
   `acks_on_failure_or_timeout` соответствуют матрице.
2. Идемпотентность сервисов: двукратный вызов — одинаковое состояние.
3. Падение всего worker (реальный Redis, короткий visibility) → redelivery,
   побочный эффект не дублируется.
4. Child-kill (SIGKILL) → ack vs reject по задаче.
5. Детерминированное исключение → ack (нет бесконечной редрставки).
6. Конкурентный `restore_check` → один DROP/CREATE, без deadlock.
7. Один `BackupRun` на id вызова, ротация корректна.
8. Обычные pytest/ruff/mypy/migrations-check.

## 7. Acceptance criteria (при переходе к реализации)

- Семантика каждой задачи задокументирована и покрыта контрактным тестом.
- backup/restore/anonymize идемпотентны; дублей `BackupRun`/DROP/анонимизации
  нет.
- Нет тихой потери критичных задач при child-kill.
- Детерминированные ошибки не вызывают бесконечной редрставки.
- Мониторинг redelivery/worker_lost и свежести бэкапа.
- Тесты/линт/типы/миграции зелёные.

## 8. Stop conditions / не входит

- Не включать глобально `reject_on_worker_lost=True` до guard-ов.
- Не задавать `acks_on_failure_or_timeout=False`.
- Не уменьшать prod `visibility_timeout` ниже max длительности задач.
- Не менять стек/брокер; не трогать ZIP; не менять защищённые файлы;
  никаких destructive DB-операций.

## 9. Решения владельца

1. Разрешить перевод `backup_full`/`restore_check`/`anonymize_due_accounts`
   на at-least-once с идемпотентностью (Фаза 2)?
2. Приемлема ли задержка redelivery до ~3600 с для бэкапа; менять ли
   `visibility_timeout`?
3. Нужен ли отдельный worker/очередь для backup/restore (Фаза 3)?

До решения поведение не меняется; Фаза 1 (наблюдаемость/документация/тесты)
может быть выполнена без изменения семантики.
