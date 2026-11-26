# Live Room LR-3 recovery evidence

**Дата:** 2026-11-26. **Среда:** dev-lite, PostgreSQL 18, Python 3.14,
Django 5.2. **Статус:** техническое evidence; product acceptance owner.

## Автоматические проверки

`tests/integration/test_live_room_recovery.py` — **3 passed**:

- повторный `expire_rooms_task` идемпотентен: первый вызов истекает
  комнату и удаляет истёкшую idempotency-запись, второй — 0/0;
- failed command (`start` при недостатке игроков) не меняет
  `Room.version`/`state` и не оставляет `RoomCommand`;
- после `connections.close_all()` состояние комнаты, роли и слова
  сохраняются; повторное чтение возвращает тот же room/version/role.

`tests/integration/test_live_room_races.py` — **12 passed**:
параллельные join/ready/start/vote/tie/host claim/sweep/expiry/cleanup;
итоговое состояние проверяется в БД (один host, нет переполнения,
голоса не теряются).

## Реальный restart dev-стека

1. Создана активная комната через сервис: `code=RUY8Q7`,
   `version=8`, `phase=reveal`, 4 участника.
2. Выполнен `make restart` — контейнеры `web` и `worker` перезапущены.
3. После restart `read_room(host)` вернул ту же комнату, `version=8`,
   `phase=reveal`, роль `civilian`; состояние и приватная роль не
   потеряны.
4. Дважды вызван `expire_rooms_task`: первый результат
   `{'expired': 30, 'cleaned': 0}`, второй `{'expired': 0,
   'cleaned': 0}`. 30 истёкших комнат — накопленные dev/load-комнаты,
   не пользовательские production-данные; повторный вызов безопасен.
5. Celery worker был перезапущен вместе с web; задача вручную
   выполнялась после restart. Отдельный broker/worker crash не
   эмулировался; рекомендуется LR-3 follow-up при появлении staging.

## Ограничения

- Реальный restart выполнялся только на dev-lite/WSL2, не на staging
  или production.
- Не проверялся SIGKILL посреди транзакции, падение Redis broker,
  двойная доставка Celery task под нагрузкой.
- `expire_rooms` по-прежнему берёт пачку комнат в одной транзакции;
  на 46 dev-rooms это 119 ms, на production-объёме нужен отдельный
  batch/soak тест.
