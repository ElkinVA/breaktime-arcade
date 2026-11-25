# ARCADE-REDIS-BROKER-ISOLATION-001 — оценка и реализация

**Дата:** 2026-11-25. **Статус:** реализовано, ожидает независимого review и
продуктовой приёмки владельцем.

## Проблема

До изменения `zip-worker` и весь остальной Celery использовали один
`redis-broker` без `requirepass`/ACL. Скомпрометированный worker (парсит
untrusted ZIP) мог подключиться к default-очереди, читать/удалять чужие
задачи или опубликовать задачу, которую исполнит обычный worker с доступом
к БД и секретам. Имя очереди `zip` само по себе границей безопасности не
является.

## Варианты

| Вариант | Плюсы | Минусы/стоимость |
|---|---|---|
| Redis ACL + `requirepass` | Один broker, точечные права | Нужен секрет для всех клиентов и его ротация; Celery использует широкий набор команд/ключей (`BRPOP`, `EVALSHA`, `unacked`), ACL легко ломает доставку; требуется менять `.env`/секреты и healthchecks |
| Отдельный `redis-zip` | Реальная сетевая граница без секретов; zip-worker физически не видит default broker | +1 контейнер (лимит 96 МБ, фактически ~10–20 МБ idle), +1 volume, +healthcheck, publisher-only app и dispatcher очистки |
| Оставить общий broker | Нет изменений | Не закрывает critical-риск; отклонено |

Выбран **отдельный `redis-zip`**: это минимальная надёжная изоляция без
новых секретов и без хрупкого ACL для Celery. Стоимость — один Redis-контейнер
с `maxmemory 64mb`/лимитом 96 МБ, volume `redis_zip_data`, один
дополнительный healthcheck и dispatcher-задача раз в час.

## Реализация

- `compose.yml`: `redis-zip` в сетях `internal` + `zipnet`; `redis-broker`
  убран из `zipnet`; `zip-worker` остаётся только в `zipnet`, его broker
  жёстко `redis://redis-zip:6379/0`, зависимость — `redis-zip`.
- `config/zip_celery.py`: publisher-only Celery app и `send_zip_task()` с
  явным Kombu `Connection`, потому что Celery отдаёт env
  `CELERY_BROKER_URL` приоритет над `broker=`.
- `apps/pipeline/tasks.py`: `enqueue_extraction` и `dispatch_zip_cleanup`
  публикуют только через `send_zip_task`; beat планирует dispatcher в
  default-очереди, а dispatcher отправляет cleanup в `redis-zip`.
- `config/settings/base.py`: `CELERY_ZIP_BROKER_URL` с fail-closed default
  `redis://redis-zip:6379/0` (не откатывается на общий broker).
- Тесты: топология compose, отсутствие `zipnet` у default broker, env
  издателей, explicit connection, dispatcher и маршруты.

## Проверки

- Targeted: 66 passed (zip worker, compose, quality, delivery contract,
  worker integration).
- Live dev: `zip-worker` резолвит `redis-zip`, но не `redis-broker`, `db`,
  `redis-cache`; dispatcher прошёл default broker → cleanup пришёл в
  zip-worker на queue `zip`; `enqueue_extraction` доставил
  `extract_zip_task` в zip-worker (missing job корректно отклонён
  `X_SOURCE_UNSAFE`).
- ruff/format clean, mypy clean (393); полный suite — в этом пакете.
- Staging/production live NOT TESTED (staging остановлен; prod deploy gate).

## Семантика сбоев

`dispatch_zip_cleanup` — часовой backstop без отдельного retry: если
`redis-zip` недоступен в момент dispatch, задача завершится ошибкой/ack-ом,
а следующая попытка придёт по расписанию через час. Дубли cleanup безопасны
(идемпотентная TTL-чистка). Дубли extraction защищены существующей
идемпотентностью job (ATTEMPTS/lock/reuse).

## Остатки

- `redis-zip` без аутентификации: граница — сеть `zipnet`, а не ACL.
  Скомпрометированный zip-worker может управлять только zip-очередью
  (включая её очистку), не default-очередью.
- Publisher-сети web/worker по-прежнему имеют доступ к `redis-zip`; это
  доверенные сервисы, но при их компрометации граница не спасает.
- Live staging/prod и нагрузочный тест не выполнялись.
