# R-036 Phase 1 — delivery observability, docstrings and contract tests

**Дата:** 2026-11-21
**Статус:** **TECHNICALLY ACCEPTED** (agent; code-reviewer и
security-auditor — **ACCEPT**); Phase 2 — **AWAITING OWNER DECISION**.
Поведение доставки не изменялось.
**Реализация:** Flash (`deepseek-flash[1m]`); анализ R-036 — `architect`
(`deepseek-v4-pro`, text-only); независимый review — `code-reviewer`/
`security-auditor` (`deepseek-v4-pro`, text-only).
**Связанный анализ:** `docs/foundation/R-036_ACKS_LATE_ANALYSIS.md`.

## 1. Цель и границы

Фаза 1 по рекомендации F: сделать at-least-once-семантику видимой и
зафиксированной, не меняя `acks_late`, `reject_on_worker_lost`,
`acks_on_failure_or_timeout`, `visibility_timeout`, очереди, маршруты и
идемпотентность задач.

Вне scope: idempotency guards для `backup_full`/`restore_check`/
`anonymize_due_accounts`, включение `reject_on_worker_lost` для обычных
задач, изменение `visibility_timeout`, отдельный backup-worker. Это Phase 2
и требует решения владельца.

## 2. Изменённые файлы

- `apps/core/celery_observability.py` — новые обработчики сигналов
  `task_received`, `task_failure`, `task_retry`, `worker_process_shutdown`,
  `worker_shutdown`.
- `config/celery.py` — импорт модуля наблюдаемости.
- `apps/core/logging.py` — `JsonFormatter` пропускает поля `task_name`,
  `redelivered`, `retries`, `exception_type`, `worker`, `worker_pid`,
  `exitcode`.
- `apps/crm/tasks.py`, `apps/accounts/tasks.py`, `apps/catalog/tasks.py`,
  `apps/pipeline/tasks.py` — docstrings с R-036-контрактом (acks
  at-least-once, идемпотентность/её отсутствие).
- `tests/unit/test_celery_delivery_contract.py` — 5 тестов: матрица
  конфигурации, поля событий, fallback `task_name`, формат JSON, отсутствие
  task args/kwargs в логах.

Настройки Celery, миграции, БД, API, permissions, ZIP pipeline и compose не
менялись.

## 3. Что логируется

Только: `event`, `task_id`, `task_name` (только `str`), `queue`,
`redelivered`, `retries`, тип исключения (`exception_type`), hostname
worker, pid, exit code. Аргументы задачи, kwargs, результат, текст
исключения и traceback не логируются. Тест `test_handlers_do_not_log_task_arguments`
подтверждает отсутствие `secret-token`/`password` в вызове логгера.

## 4. Фактическая проверка на живом worker

После отправки `crm.backup_status_alert` в очередь `celery` worker
(dev-lite, solo) записал:

```json
{"ts": "2026-11-21T06:09:23.120536+00:00", "level": "INFO",
 "logger": "apps.core.celery", "message": "celery.task.received",
 "request_id": "-", "event": "celery.task.received",
 "task_id": "06ce21e4-f5b0-49e9-8987-d87582982ff7", "queue": "celery",
 "task_name": "crm.backup_status_alert", "redelivered": false, "retries": 0}
```

`backup.start`/`backup.end` для реального `crm.backup_full` также
наблюдались в worker; очередь `celery` после запуска worker пуста.

## 5. Найденные и исправленные дефекты наблюдаемости

Живая проверка выявила два дефекта, невидимых unit-тестам:

1. Celery передаёт в `task_received` `sender=Consumer`, у которого
   `.name` — объект текущей задачи, а не строка. Старый `_task_name`
   возвращал этот объект; `JsonFormatter` падал с
   `TypeError: Object of type backup_status_alert is not JSON serializable`,
   и событие терялось. Исправление: предпочитать `request.task`/
   `request.name`, принимать только непустые `str`. Добавлен regression-тест.
2. Django `dictConfig` очищает handler, добавленный на уровне модуля, а
   Celery в worker подменяет `sys.stderr`; запись из consumer-потока через
   унаследованный `apps`-handler терялась. Исправление: ленивый
   `_FdStderrHandler`, пишущий JSON в fd 2 через `os.write`; handler
   переустанавливается перед каждым событием.

Оба дефекта затрагивали только наблюдаемость; обработка задач и ack-политика
не менялись.

## 6. Проверки

```text
pytest (full)      -> 402 passed, 3 skipped, 1 warning
ruff check         -> All checks passed
ruff format --check-> 371 files already formatted
mypy               -> Success: no issues found in 338 source files
```

Контрактная матрица в тестах фиксирует: обычные задачи —
`acks_late=True`, `reject_on_worker_lost` None/False,
`acks_on_failure_or_timeout=True`; ZIP — reject True; глобальный
`visibility_timeout` — 3600.

## 7. Независимый review

- **code-reviewer** (`deepseek-v4-pro`, text-only): **ACCEPT**. Замечания
  minor: scope `propagate=False` (задокументирован как выделенный канал),
  частичная запись fd (добавлен цикл `memoryview`), `worker` в
  `worker_process_shutdown` (sender — строка hostname; теперь логируется
  и строка, и объект).
- **security-auditor** (`deepseek-v4-pro`, text-only): **ACCEPT**.
  Подтверждены allowlist полей, отсутствие args/kwargs/текста исключения,
  JSON-экранирование, deny-safe поведение при исключении receiver.
  Замечания minor: race при attach handler (добавлен `threading.Lock`),
  отсутствие throttling у fd-2 канала (принято как residual).
- Повторный full gate после правок: **402 passed, 3 skipped**;
  ruff/format/mypy clean.

## 8. Остатки

- Live redelivery после падения worker и child-kill не форсировались;
  поведение redelivery/carve-out остаётся предметом Phase 2.
- `task_failure`/`task_retry` проверены unit-тестами, не отдельным live
  отказом.
- fd-2 канал observability не имеет rate-limit/throttling; объём
  пропорционален потоку задач (security review, residual).
- Phase 2 (идемпотентность backup/restore/anonymize, точечный reject,
  visibility timeout, отдельный worker) не начиналась.

## 9. Следующий шаг

Решение владельца по вопросам 1–3 из
`docs/foundation/R-036_ACKS_LATE_ANALYSIS.md` §9. До решения
`acks_late`/`reject_on_worker_lost`/`visibility_timeout` не меняются.
