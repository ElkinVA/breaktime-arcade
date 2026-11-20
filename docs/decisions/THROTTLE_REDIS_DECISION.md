# THROTTLE_REDIS_DECISION — предсказуемое поведение throttle при вытеснении ключей

**Дата:** 2026-11-20  
**Статус:** **DECIDED (technical) / IMPLEMENTATION PENDING**  
**Основание:** OD-REDIS-001; security-review APPF-SESSION-001 (F-6);
BA-PLAT-4.2 §2.5 (Redis cache allkeys-lru, broker noeviction отдельно),
Приложение E (rate limits).

## 1. Проблема

DRF throttle хранит счётчики в Django cache. Сейчас единственный кэш —
`redis-cache` с `maxmemory-policy allkeys-lru`. Под давлением памяти Redis
может вытеснить ключи throttle → лимиты молча ослабнут, причём
неравномерно (какие ключи вытеснятся — недетерминировано). Для публичного
API это неприемлемо: лимит должен быть предсказуемым, а не зависеть от
загрузки кэша.

## 2. Варианты

| Вариант | Предсказуемость | Изоляция | Стоимость/эксплуатация | Вердикт |
|---|---|---|---|---|
| A. Отдельный инстанс `redis-throttle` (noeviction, без AOF) | Высокая: вытеснения нет; при переполнении Redis отвечает ошибкой записи | Полная: не влияет на cache/broker и наоборот | +1 контейнер, 64 МБ dev / 256 МБ prod, healthcheck, без бэкапа | **Рекомендуется** |
| B. Отдельная логическая БД на `redis-cache` | Низкая: политика вытеснения задаётся инстансом, не БД | Нет | 0 | Отклонено |
| C. Использовать `redis-broker` (noeviction) | Средняя: вытеснения нет, но память делится с Celery | Частичная; throttle-нагрузка и очередь Celery мешают друг другу | 0 дополнительных контейнеров | Отклонено: смешение ответственности, AOF не нужен для счётчиков |
| D. Счётчики в PostgreSQL | Высокая | Полная | +нагрузка на БД на каждый запрос, транзакции/блокировки | Отклонено: дорого и медленно |
| E. Локальная память процесса | Нет: у Gunicorn несколько воркеров | Нет | 0 | Отклонено |

## 3. Рекомендуемая архитектура (A)

- Новый сервис `redis-throttle`: образ `redis:8-alpine` (digest как у
  cache/broker), `--maxmemory 64mb` (dev) / `256mb` (prod),
  `--maxmemory-policy noeviction`, `--save ""`, `--appendonly no`,
  `healthcheck: redis-cli ping`, внутренняя сеть, без публикации портов.
- `REDIS_THROTTLE_URL=redis://redis-throttle:6379/0`; Django cache alias
  `throttle` (django_redis, KEY_PREFIX `ba-throttle`, TIMEOUT 300).
- DRF throttle-классы используют `cache = caches["throttle"]`; остальные
  кэши остаются на `default`.
- Отказ throttle-бэкенда: **fail-open с ERROR-логом и алертом**. Причина:
  падение throttle не должно ломать публичные игры; защита от abuse
  дублируется CSRF, лимитом ≤3 активных сессий, TTL билета и проверками
  состояния. Для чувствительных операций (вход/регистрация) остаются
  отдельные механизмы; их перевод на новый alias — отдельная задача.
- Перезапуск `redis-throttle` обнуляет счётчики — допустимо (кратковременное
  ослабление, не потеря данных).
- IPv6: ключ IP агрегируется по /64 (Приложение E) — реализуется в throttle
  key, не в Redis.

## 4. Стоимость и эксплуатационные последствия

- RAM: ~5–10 МБ на пустой инстанс; лимит 64 МБ dev / 256 МБ prod; ключи
  throttle маленькие и с TTL, фактическое потребление — единицы МБ.
- CPU: минимальный (GET/SET счётчиков).
- Контейнеры: +1 сервис в dev-lite, staging, production compose; healthcheck
  и `depends_on: service_healthy`; отдельный лог.
- Секреты: URL без пароля во внутренней сети; при внешнем Redis — пароль/TLS
  в `.env*`, как для cache/broker.
- Бэкап: не требуется (счётчики эфемерны).
- Мониторинг: healthcheck + алерт на ERROR `throttle.cache_failed`; метрика
  used_memory.
- Влияние на приёмку: §2.5 требует раздельные cache/broker; отдельный
  throttle-инстанс не противоречит ТЗ и усиливает предсказуемость лимитов.

## 5. План реализации (после приёмки APPF-SESSION-001)

1. `config/settings/base.py`: `REDIS_THROTTLE_URL`, alias `throttle`.
2. `apps/gameplay/api/throttling.py` и будущие throttle: `cache = caches["throttle"]`,
   fail-open wrapper с логом.
3. `compose.dev-lite.yml`, `compose.yml`, staging: сервис `redis-throttle`,
   env, healthcheck.
4. Тесты: override `CACHES` alias; отказ backend → запрос не падает;
   счётчики не вытесняются (политика проверяется конфигом, не тестом).
5. Обновить BA-ENV-1.1: `REDIS_THROTTLE_URL` в Приложении A (после
   утверждения документа владельцем).
