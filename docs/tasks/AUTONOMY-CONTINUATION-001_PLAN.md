# AUTONOMY-CONTINUATION-001 — минимальное продолжение после сессии

**Дата:** 2026-11-23  
**Статус:** **BLOCKED — AWAITING OWNER DECISION** (AI HQ architecture).  
**Основание:** фактическая проверка AI Headquarters 2026-11-23; не создавать
параллельный оркестратор и не менять архитектуру без согласования.

## 1. Факты проверки

| Уровень | Факт | Статус |
|---|---|---|
| A. Переход между задачами | `autonomy/orchestrator.py::run` умеет выполнять несколько задач в одном bounded-запуске; VPS unit запускает `--max-tasks 1` | **PASS (код) / NOT TESTED live** |
| B. Продолжение после сессии | нет автоматического запуска следующей сессии; devcontrol `/continue` — ручной; hooks только уведомляют | **FAIL** |
| C. Фоновая работа | systemd user units `ba-autonomy-orchestrator.service`/`ba-devcontrol.service` не установлены; timers нет; `.autonomy` отсутствует | **FAIL** |
| D. Восстановление | `StateStore.recover_running`, `RUN_LOCK`, worktree cleanup, retry limits; unit tests 94 passed/1 skipped | **PASS (код) / NOT TESTED live** |
| E. Telegram | `api.telegram.org:443` timeout; process/service отсутствует; state dir отсутствует | **FAIL/NOT TESTED** |

Текущий interactive Claude-сеанс — единственный активный; background-сессий
нет. `zip-worker` также не запущен, но это не AI HQ.

## 2. Минимальное решение

Не создавать новый orchestrator. Добавить только штатный **systemd user
timer**, который периодически запускает существующий bounded-запуск:

```text
ba-autonomy-orchestrator.timer
  -> ba-autonomy-orchestrator.service
       ExecStart=python3 -m autonomy.orchestrator run --max-tasks 1
```

- `OnUnitActiveSec`/`OnBootSec` с интервалом, согласованным владельцем.
- `RUN_LOCK` уже не даёт двум запускам работать одновременно.
- `.autonomy/STOP` остаётся аварийным стопом между задачами.
- `Type=oneshot` не меняется; timer только повторяет bounded-запуск.
- Сервис/таймер **не включать автоматически**; установка и `enable` — только
  владелец.
- Уведомления/Dev Control не менять; при недоступном Telegram события
  остаются в `.autonomy/events.jsonl`.

## 3. Альтернативы

1. **Timer (рекомендуется):** минимально, использует существующий
   оркестратор, не требует нового supervisor.
2. **devcontrol auto-continue:** расширить бот, чтобы после `SessionEnd`
   автоматически вызывать `/continue`; сложнее, зависит от Telegram и
   permissions, не работает при недоступном API.
3. **Постоянный long-running orchestrator:** потребует переписать unit и
   lifecycle; больше риска, не минимально.

## 4. Вопросы владельцу

1. Разрешить установку/enable user timer для `autonomy.orchestrator`?
2. Интервал запуска (например, 15/30/60 минут) и окно работы?
3. Нужен ли отдельный VPS/пользователь; принимается ли model process под
   пользователем (R-040)?
4. Включать ли Telegram/Dev Control только после прокси/VPN (R-038)?

## 5. Критерии приёмки

- После завершения bounded-запуска timer запускает следующий только при
  наличии READY-задач; STOP/PAUSE соблюдаются.
- Нет двух одновременных orchestrator-процессов (`RUN_LOCK`).
- После reboot состояние читается, `recover_running` не дублирует
  завершённые задачи; worktree очищается.
- Ошибки/блокировки видны в `.autonomy/events.jsonl`; Telegram — если
  настроен.
- Тесты/линт/типы; live-проверка на VPS; без production deploy и секретов.

## 6. Stop conditions

- Нет owner approval на AI HQ architecture.
- Нет VPS/пользователя/исходящего 443 к провайдеру.
- Требуется изменить Celery/БД/контракты или обойти hooks — остановиться.
