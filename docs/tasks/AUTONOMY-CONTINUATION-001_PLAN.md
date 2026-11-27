# AUTONOMY-CONTINUATION-001 — минимальное продолжение после сессии

**Дата:** 2026-11-23  
**Статус:** **PARTIAL — owner approved WSL heartbeat 2026-11-26;
auth verified, sandbox checks fixed, timer OFF.**
**Основание:** фактическая проверка AI Headquarters 2026-11-23; owner
разрешил 30-минутный systemd user timer для существующего
`autonomy.orchestrator` (Pro architect/reviewer + Flash developer/QA,
текущие лимиты). Units установлены/связаны, timer **не включён**:
bounded-run авторизовался (`deepseek-v4-pro` / `deepseek-flash[1m]`),
задача `ARCADE-EMAIL-RESET-RACE-001` завершена технически после
исправления sandbox-конфигурации и test setup, но чистый end-to-end
bounded-run и проверка gate ещё не выполнены. Не создавать параллельный
оркестратор; включение timer — только после успешного bounded-run и
owner review.

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

## 7. WSL installation evidence (2026-11-26)

- Owner decision: 30-минутный systemd user timer, Pro architect/reviewer +
  Flash developer/QA, текущие лимиты (`--max-tasks 1`,
  `BA_MAX_RUN_SECONDS=3600`).
- Добавлены `autonomy/vps/wsl/ba-autonomy-orchestrator.service` и
  `.timer`; unit-файлы связаны в `~/.config/systemd/user/` через
  `systemctl --user link`, `daemon-reload` выполнен.
- Timer **не включён**: bounded-run подтвердил авторизацию
  (`deepseek-v4-pro` architect, `deepseek-flash[1m]` developer) и
  `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic`. Sandbox
  `ruff.toml`/`mypy.ini` исправлены (`71177d2`); задача
  `ARCADE-EMAIL-RESET-RACE-001` технически завершена после test-setup
  fix (`401df05`+`11ea832`), но повторный bounded-run для чистого
  end-to-end результата и проверки gate ещё нужен. Timer-запусков не
  было. Историческая journal-запись с секретом относится к старому
  `export`-файлу; в Git секрет не попал.
- **2026-11-27 clean run:** `ARCADE-RATINGS-OFFSET-001` completed by the
  orchestrator (`cef14b5`; QA pass, reviewer ACCEPT); service
  `Result=success`, task `status=completed`. `ARCADE-SUBMIT-RESTART-
  CLEANUP-001` blocked on protected `sdk/` scope, not bypassed.
- `OWNER_ACTION_REQUIRED` verified: a gated run returned `paused` without
  claiming a task. Main suite **1363 passed / 17 skipped**, ruff/mypy clean;
  main pushed (`dcc6070`).
- **Timer OFF:** `systemctl --user enable --now ba-autonomy-orchestrator.timer`
  was blocked by the auto-mode permission harness; owner must run it
  manually. After enabling, the timer will launch the existing bounded run
  every 30 minutes.
- WSL должен быть запущен; после завершения WSL/Windows timer не
  работает без отдельного Windows/WSL autostart (не настраивался).
