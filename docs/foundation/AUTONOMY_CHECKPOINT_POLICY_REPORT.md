# AI Headquarters — OWNER CHECKPOINT & NOTIFICATION POLICY

**Дата:** 2026-11-26. **Статус:** IMPLEMENTED; code-review ACCEPT после
must-fix M1/M2; security review ACCEPT после minor fixes; остаточный
QA-boundary check исправлен после отчёта. Полный gate **1355 passed, 17
skipped**; exact-commit CI **#163 SUCCESS**. **Timer остаётся
выключенным.** Продуктовая/операционная приёмка владельца не заявлена.

## Что реализовано

- **Owner-action gate** `.autonomy/OWNER_ACTION_REQUIRED` — отдельный от
  аварийного `STOP` JSON-файл с reason/kind/milestone/action/recommendation.
  Проверяется до `recover_running`, `claim_next`, `propose` и перед каждым
  model-call (developer/QA/reviewer/architect) и merge. Malformed/non-regular
  gate fail-closed. `STOP` имеет приоритет.
- **CLI** `autonomy pause`, `autonomy checkpoint --milestone`, `autonomy
  resume`, `autonomy status`. Gate не меняет task state; при появлении gate
  после claim задача возвращается в READY, worktree удаляется.
- **Статусы** `RUNNING`, `WAITING_FOR_NEXT_RUN`, `PAUSED_FOR_OWNER`,
  `MILESTONE_COMPLETED`, `BLOCKED`, `STOPPED_ERROR` + additive `STOPPED`.
  `status` показывает последний run/задачу/агента/модель, heartbeat,
  результат, reason, systemd service/timer, следующий timer и пути логов.
  `RUNNING` — только при подтверждённом flock+PID (не zombie).
- **Уведомления:** Windows toast для pause/milestone/critical; persistent
  sanitized `0600` `.autonomy/reports/last_run_report.json`; существующий
  Telegram-канал получает paused/milestone один раз. `notified_at`
  выставляется только после успешной доставки хотя бы одним каналом;
  иначе повтор на следующем heartbeat. PowerShell получает минимальное
  окружение без `ANTHROPIC_*`; XML/quote escaping.
- **Совместимость:** state schema не менялась, миграций нет; `RUN_LOCK`,
  STOP, budget, model routing не ослаблены; timer/unit не менялись.

## Проверки

- Focused tests **28 passed** (gate, status, Windows notify).
- Existing autonomy/control suite (autonomy/devcontrol/VPS) — pass.
- ruff/format clean; mypy **412 files** clean.
- Code-review: сначала REJECT (M1 gate TOCTOU, M2 unreachable
  `STOPPED_ERROR`); оба исправлены, delta **ACCEPT**. Security review:
  **ACCEPT** после minor fixes (STOP precedence, gate lock races,
  notification retry, fail-closed stat, PID/recover, toast encoding/env);
  последний QA-boundary check исправлен после отчёта.
- Реальный smoke: `pause → status → resume`; PAUSED_FOR_OWNER и
  MILESTONE_COMPLETED корректны; реальный Windows toast вернул `sent`
  (и повторён после минимального child env); timer disabled.
- Полный regression gate: **1355 passed, 17 skipped, exit 0**
  (840.31 s) на свежей test DB.
- Exact-commit CI **#163** на `9adfa09` — success (quality, e2e,
  frontend, image, django-next):
  https://github.com/ElkinVA/breaktime-arcade/actions/runs/45872239680

## Остатки

- `enqueue`/`recover` — ручные owner-команды обслуживания; gate их не
  блокирует (модели не вызываются); документировано.
- Windows toast best-effort: OS может подавить уведомление; `sent` означает
  только успешный exit PowerShell.
- WSL должен быть запущен; после WSL/Windows shutdown timer не работает
  без autostart.
- Gate, установленный во время уже идущего model-call, останавливает
  следующий boundary; текущий вызов завершается/отбрасывается.
- Heartbeat authorization подтверждена: architect `deepseek-v4-pro`,
  developer `deepseek-flash[1m]`; последний bounded-run завершил задачу
  `ARCADE-EMAIL-RESET-RACE-001` в BLOCKED после двух ruff/mypy failures.
  Timer не включается до успешного bounded-run и owner review.
